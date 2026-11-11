"""doubletap.py <label> [doubles]: does a double tap on a zoomed live view return it to the default
zoom? Zooms in through the card's own `ptz_digital` action (absolute zoom 3: a scripted pinch often
does not take in the emulator), then taps with Chrome's synthesized gesture
(Input.synthesizeTapGesture, 50 ms per tap). Taps sent as separate touch events do not work here:
each is a round trip to the emulator, so a 50 ms tap reached the page as 200-290 ms (11-11-2026).
The emulator decides the gap between the two synthesized taps; a page-side log records it, from the
first tap's end to the second tap's start, as the card sees it.

Per double tap: the gap, the scale before and after, and whether the card fired `zoom:home` (the
event the double-tap change uses; other builds never do). Then a single tap (control) and, unzoomed,
a double tap (the zoom must stay at 1)."""
import asyncio, json, sys

sys.path.insert(0, "/lab/tools/cdp")
from lablib import Cdp, TEST_PATH, connect, save_result  # noqa: E402

DEEP = ("const deep = (r, t, o = []) => { for (const el of r.querySelectorAll('*')) { "
        "if (el.tagName.toLowerCase() === t) o.push(el); if (el.shadowRoot) deep(el.shadowRoot, t, o); } return o; };")
VISIBLE = "(t) => deep(document, t).find((e) => e.getBoundingClientRect().height > 20)"

# The zoomer's scale and the live view's centre.
STATE = "(() => { " + DEEP + f" const vis = {VISIBLE};" + """
  const z = vis('advanced-camera-card-zoomer'); const lp = vis('advanced-camera-card-live-provider');
  if (!z || !lp) return JSON.stringify(null);
  const t = getComputedStyle(z).transform; const s = t === 'none' ? 1 : +t.replace(/matrix\\(([^,]+),.*/, '$1');
  const r = lp.getBoundingClientRect();
  return JSON.stringify({ scale: Math.round(s * 100) / 100, x: r.left + r.width / 2, y: r.top + r.height / 2 });
})()"""


def ptz_digital(absolute):
    action = {"action": "fire-dom-event", "advanced_camera_card_action": "ptz_digital"}
    if absolute:
        action["absolute"] = absolute
    return ("(() => { " + DEEP + f" const z = ({VISIBLE})('advanced-camera-card-zoomer');" +
            " z.dispatchEvent(new CustomEvent('advanced-camera-card:action:execution-request', "
            "{ bubbles: true, composed: true, detail: { actions: " + json.dumps(action) + " } })); return 1; })()")


# The touch and zoom:home events as the page sees them (window, capture phase).
HOOK = """(() => { window.__dt = []; if (!window.__dtHooked) { for (const n of ['touchstart', 'touchend', 'advanced-camera-card:zoom:home']) {
  window.addEventListener(n, (e) => window.__dt.push([n.replace('advanced-camera-card:', ''), e.timeStamp]), true); } window.__dtHooked = 1; } return 1; })()"""


def summarize(events):
    starts = [t for n, t in events if n == "touchstart"]
    ends = [t for n, t in events if n == "touchend"]
    out = {"touches": len(starts), "zoom_home": sum(1 for n, _ in events if n == "zoom:home")}
    if len(starts) > 1 and ends:
        out["gap_ms"] = round(starts[1] - ends[0])
    return out


async def main(label, doubles):
    async with await connect() as ws:
        cdp = Cdp(ws)
        await cdp.goto(TEST_PATH)
        print(label, "playing:", await cdp.wait_playing(), flush=True)
        await asyncio.sleep(1)

        async def state():
            return json.loads(await cdp.ev(STATE))

        async def scale_becomes(target):
            s = await state()
            for _ in range(30):
                if s and s["scale"] == target:
                    break
                await asyncio.sleep(0.1)
                s = await state()
            return s

        async def gesture(s, taps):
            await cdp.ev(HOOK)
            await cdp.call("Input.synthesizeTapGesture", x=s["x"], y=s["y"], duration=50, tapCount=taps,
                           gestureSourceType="touch")
            await asyncio.sleep(1.2)
            return (await state())["scale"], summarize(json.loads(await cdp.ev("JSON.stringify(window.__dt)")))

        async def home():
            await cdp.ev(ptz_digital(None))
            await scale_becomes(1)

        results = []

        def report(row):
            results.append(row)
            print(" | ".join(f"{k} {v}" for k, v in row.items()), flush=True)

        for i in range(1, doubles + 1):
            await cdp.ev(ptz_digital({"zoom": 3, "pan": {"x": 30, "y": 30}}))
            s = await scale_becomes(3)
            after, seen = await gesture(s, 2)
            report({"case": "double tap", "n": i, "gap_ms": seen.get("gap_ms"), "scale": f"{s['scale']} -> {after}",
                    "zoom_home": seen["zoom_home"]})
            await home()

        await cdp.ev(ptz_digital({"zoom": 3, "pan": {"x": 30, "y": 30}}))
        s = await scale_becomes(3)
        after, seen = await gesture(s, 1)
        report({"case": "single tap", "scale": f"{s['scale']} -> {after}", "zoom_home": seen["zoom_home"]})
        await home()

        s = await state()
        after, seen = await gesture(s, 2)
        report({"case": "unzoomed double tap", "touches": seen["touches"], "gap_ms": seen.get("gap_ms"),
                "scale": f"{s['scale']} -> {after}", "zoom_home": seen["zoom_home"]})
        save_result(f"doubletap-{label}", results)


if __name__ == "__main__":
    asyncio.run(main(sys.argv[1], int(sys.argv[2]) if len(sys.argv) > 2 else 8))
