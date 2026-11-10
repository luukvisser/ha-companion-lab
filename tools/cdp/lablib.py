"""Shared helpers for the lab's plain-CDP scripts (tools/cdp/*.py, video/**/cdp/*.py).

    from lablib import Cdp, connect, save_result
    async with await connect() as ws:
        cdp = Cdp(ws)
        await cdp.goto(TEST_PATH)                 # in-app navigation (no page load)
        await cdp.wait_playing()
        value = await cdp.ev("1 + 1")             # evaluate, awaiting promises, by value
        await cdp.ev("...", gesture=True)         # with a user gesture (fullscreen, audio)
    save_result("blip-main", data)                # $OUT_DIR/<name>.json + <name>.meta.json

The scripts run in the lab's Python container (lib.sh lab_py: /lab is the repository, /out the
results folder, /builds the card builds; DevTools on localhost:$CDP_PORT).
"""
import asyncio, datetime, json, os, urllib.request

import websockets

PORT = int(os.environ.get("CDP_PORT", "9333"))
OUT = os.environ.get("LAB_OUT", "/out")
TEST_PATH = os.environ.get("TEST_PATH", "/test-dashboard/test")
OTHER_PATH = os.environ.get("OTHER_PATH", "/profile/general")
CARD_PREFIX = os.environ.get("CARD_PREFIX", "/local/community/advanced-camera-card/")

# Finds the first element with a tag anywhere in the page, shadow trees included.
DEEP = "(t) => { const w = (r) => { for (const el of r.querySelectorAll('*')) { if (el.tagName.toLowerCase() === t) return el; if (el.shadowRoot) { const f = w(el.shadowRoot); if (f) return f; } } return null; }; return w(document); }"
PLAYING = "(() => { const o = []; const w = (r) => { for (const el of r.querySelectorAll('*')) { if (el.tagName === 'VIDEO') o.push(el); if (el.shadowRoot) w(el.shadowRoot); } }; w(document); return o.some((v) => !v.paused && v.currentTime > 2); })()"


async def connect(retries=20):
    """A websocket to the first page of the app's WebView. Right after an app start the DevTools
    socket can drop the first requests, so it retries once a second."""
    for _ in range(retries):
        try:
            pages = json.load(urllib.request.urlopen(f"http://localhost:{PORT}/json", timeout=5))
            pages = [p for p in pages if p["type"] == "page"]
            if pages:
                return await websockets.connect(pages[0]["webSocketDebuggerUrl"], max_size=None)
        except Exception:
            pass
        await asyncio.sleep(1)
    raise SystemExit("no page on DevTools")


class Cdp:
    """Requests and events on one DevTools websocket. Events that arrive while waiting for a reply
    are kept in `events`, for wait_event()."""

    def __init__(self, ws, timeout=120):
        self.ws, self.n, self.events, self.timeout = ws, 0, [], timeout

    async def call(self, method, **params):
        self.n += 1
        my = self.n
        await self.ws.send(json.dumps({"id": my, "method": method, "params": params}))
        while True:
            r = json.loads(await asyncio.wait_for(self.ws.recv(), self.timeout))
            if r.get("id") == my:
                if "error" in r:
                    raise RuntimeError(f"{method}: {r['error']}")
                return r.get("result", {})
            if "method" in r:
                self.events.append(r)

    async def wait_event(self, name, timeout=60):
        for i, e in enumerate(self.events):
            if e["method"] == name:
                return self.events.pop(i)
        while True:
            r = json.loads(await asyncio.wait_for(self.ws.recv(), timeout))
            if r.get("method") == name:
                return r
            if "method" in r:
                self.events.append(r)

    async def ev(self, js, gesture=False, wait=True):
        """Evaluate JavaScript in the page; the value comes back by value. `wait=False` does not
        await a returned promise (an action that should start, not finish)."""
        r = await self.call("Runtime.evaluate", expression=js, awaitPromise=wait, returnByValue=True, userGesture=gesture)
        if "exceptionDetails" in r:
            raise RuntimeError(json.dumps(r["exceptionDetails"])[:600])
        return r.get("result", {}).get("value")

    async def goto(self, path):
        """In-app navigation (Home Assistant's router), not a page load: a reload in the same app
        process can leave video decoding broken in the emulator."""
        await self.ev("(() => { history.pushState(null, '', %s); window.dispatchEvent(new CustomEvent('location-changed', { detail: { replace: false } })); return 1; })()" % json.dumps(path))

    async def wait_playing(self, seconds=60):
        """True once a video in the page has played for more than 2 s."""
        for _ in range(seconds):
            await asyncio.sleep(1)
            try:
                if await self.ev(PLAYING):
                    return True
            except Exception:
                pass
        return False

    async def card_files(self):
        """The card's JavaScript files this page loaded (their names carry the build's hashes)."""
        return await self.ev("[...new Set(performance.getEntriesByType('resource').map((e) => e.name).filter((u) => u.includes(%s)).map((u) => new URL(u).pathname.split('/').pop()))]" % json.dumps(CARD_PREFIX))


def card_js(expr):
    """JavaScript that runs `expr` with `card` bound to the first advanced-camera-card element."""
    return "((card) => { %s })((%s)('advanced-camera-card'))" % (expr, DEEP)


def save_result(name, data, extra_meta=None):
    """Write $OUT_DIR/<name>.json and, next to it, <name>.meta.json: the run's setup as the shell
    wrapper recorded it (LAB_META_FILE, see lib.sh write_meta) plus the time and anything extra."""
    os.makedirs(OUT, exist_ok=True)
    json.dump(data, open(f"{OUT}/{name}.json", "w"))
    meta = {}
    src = os.environ.get("LAB_META_FILE")
    if src and os.path.exists(src):
        meta = json.load(open(src))
    meta["saved"] = datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")
    meta.update(extra_meta or {})
    json.dump(meta, open(f"{OUT}/{name}.meta.json", "w"), indent=1)
    return f"{name}.json"
