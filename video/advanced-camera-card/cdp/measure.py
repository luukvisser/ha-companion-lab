"""Measure the fullscreen jump in the Companion app's WebView, per card build.

Runs in the cdp-py container with --network host. The card's JavaScript is
served from /builds/<variant>/ by intercepting its requests in this WebView
only; nothing changes in Home Assistant. The variant `deployed` leaves the
requests to Home Assistant (the card it serves).
"""
import asyncio, base64, json, os, subprocess, sys, urllib.request
import websockets  # noqa: F401 (lablib uses it)

sys.path.insert(0, "/lab/tools/cdp")
from lablib import connect, save_result  # noqa: E402

PORT = int(os.environ.get("CDP_PORT", "9333"))
BUILDS = "/builds"
OUT = "/out"
PREFIX = os.environ.get("CARD_PREFIX", "/local/community/advanced-camera-card/")
# An image camera: a hand-placed card does not start Home Assistant live video.
CAMERA = os.environ.get("OVERLAY_CAMERA", "camera.test_pattern")

# The card overlay, shared with the Playwright scripts (playwright/install.js).
INSTALL = open(os.path.join(os.path.dirname(__file__), "..", "playwright", "install.js")).read()


async def main(variants, rounds, leave_mode, expanded):
    async with await connect() as ws:
        n = 0
        pending = {}
        current = {"variant": None}

        async def reader():
            async for raw in ws:
                msg = json.loads(raw)
                if "id" in msg and msg["id"] in pending:
                    pending.pop(msg["id"]).set_result(msg)
                elif msg.get("method") == "Fetch.requestPaused":
                    asyncio.create_task(serve(msg["params"]))

        async def call(method, **params):
            nonlocal n
            n += 1
            fut = asyncio.get_running_loop().create_future()
            pending[n] = fut
            await ws.send(json.dumps({"id": n, "method": method, "params": params}))
            return await asyncio.wait_for(fut, 60)

        async def serve(p):
            if current["variant"] == "deployed":
                await call("Fetch.continueRequest", requestId=p["requestId"])
                return
            url = p["request"]["url"]
            path = url.split(PREFIX, 1)[1].split("?", 1)[0]
            f = os.path.join(BUILDS, current["variant"], path)
            if os.path.isfile(f):
                body = base64.b64encode(open(f, "rb").read()).decode()
                await call("Fetch.fulfillRequest", requestId=p["requestId"], responseCode=200,
                           responseHeaders=[{"name": "Content-Type", "value": "application/javascript"},
                                            {"name": "Cache-Control", "value": "no-store"}], body=body)
            else:
                await call("Fetch.fulfillRequest", requestId=p["requestId"], responseCode=404, body="")

        async def ev(js):
            r = await call("Runtime.evaluate", expression=js, awaitPromise=True, returnByValue=True)
            res = r.get("result", {})
            if "exceptionDetails" in res:
                raise RuntimeError(json.dumps(res["exceptionDetails"])[:600])
            return res.get("result", {}).get("value")

        async def tap_button():
            rect = await ev("(() => { const r = document.querySelector('#acc-measure button').getBoundingClientRect(); return [r.left + r.width/2, r.top + r.height/2]; })()")
            x, y = rect
            await call("Input.dispatchTouchEvent", type="touchStart", touchPoints=[{"x": x, "y": y}])
            await call("Input.dispatchTouchEvent", type="touchEnd", touchPoints=[])

        asyncio.create_task(reader())
        await call("Network.enable")
        await call("Network.setCacheDisabled", cacheDisabled=True)
        await call("Network.setBypassServiceWorker", bypass=True)
        await call("Fetch.enable", patterns=[{"urlPattern": "*" + PREFIX + "*"}])

        results = {}
        for v in variants:
            current["variant"] = v
            await call("Page.reload", ignoreCache=True)
            for _ in range(60):
                await asyncio.sleep(1)
                try:
                    if await ev("!!customElements.get('advanced-camera-card') && !!document.querySelector('home-assistant')?.hass"):
                        break
                except Exception:
                    pass
            await asyncio.sleep(3)
            print(v, await ev(INSTALL.replace('__CAMERA__', CAMERA)), flush=True)
            for _ in range(30):
                await asyncio.sleep(1)
                cap = await ev("(() => { const c = window.__acc.deep(window.__acc.card.shadowRoot, 'advanced-camera-card-live-carousel'); return c ? c.style.maxHeight : null; })()")
                if cap:
                    break
            print(v, "cap", cap, flush=True)
            if expanded:
                print(v, "expand", await ev("(() => { window.__acc.card._controller.getExpandManager().setExpanded(true); return 1; })()"), flush=True)
                await asyncio.sleep(3)
                print(v, "dialog", await ev("!!window.__acc.deep(window.__acc.card.shadowRoot, 'web-dialog')"), flush=True)
            await asyncio.sleep(2)
            runs = []
            for i in range(rounds):
                await ev("(() => { window.__acc.frames = []; window.__acc.events = []; return 1; })()")
                if expanded:
                    r = await call("Runtime.evaluate", userGesture=True, awaitPromise=False, returnByValue=True,
                                   expression="(() => { window.__acc.t0 = performance.now(); window.__acc.events.push([0, 'gesture-eval']); window.__acc.card.requestFullscreen().catch((e) => window.__acc.events.push([0, 'request-error ' + e.message])); return 1; })()")
                else:
                    await tap_button()
                await asyncio.sleep(2.5)
                enter = await ev("JSON.stringify({events: window.__acc.events, frames: window.__acc.frames})")
                await ev("(() => { window.__acc.t0 = performance.now(); window.__acc.frames = []; window.__acc.events = []; return 1; })()")
                how = leave_mode
                if how != "api":
                    # Sent from the host (fullscreen-measure.sh): the back key or an edge swipe.
                    # The host writes this round's token into back-done once it is sent, so a
                    # late or stale file from an earlier round is never taken for this one.
                    token = f"{v}-{i}-{os.getpid()}"
                    try:
                        os.remove(f"{OUT}/back-done")
                    except FileNotFoundError:
                        pass
                    print(f"HOSTACT {how} {token}", flush=True)
                    for _ in range(100):
                        try:
                            if open(f"{OUT}/back-done").read().strip() == token:
                                break
                        except FileNotFoundError:
                            pass
                        await asyncio.sleep(0.1)
                    else:
                        raise SystemExit(f"the host did not confirm '{how}' for round {i} within 10 s")
                else:
                    await ev("document.exitFullscreen().then(() => 'ok', (e) => 'err ' + e.message)")
                await asyncio.sleep(2.5)
                leave = await ev("JSON.stringify({events: window.__acc.events, frames: window.__acc.frames})")
                runs.append({"enter": json.loads(enter), "leave": json.loads(leave), "leave_by": how})
                await asyncio.sleep(1.5)
            results[v] = runs
            if expanded:
                await ev("(() => { window.__acc.card._controller.getExpandManager().setExpanded(false); return 1; })()")
            await ev("document.getElementById('acc-measure')?.remove(), 1")
        save_result("result", results)
        print("DONE", flush=True)


asyncio.run(main(sys.argv[1].split(","), int(sys.argv[2]), sys.argv[3], sys.argv[4] == "1"))
