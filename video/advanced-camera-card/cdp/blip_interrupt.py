"""blip_interrupt.py <label> <rounds>: does an interrupted fullscreen request leave the card blind
to later hidden spells? Run through blip-interrupt.sh (it presses Home and brings the app back).

Per round, on the test dashboard card (the card Home Assistant serves):
  A  request fullscreen through the card's fullscreen manager (user gesture), and at once ask the
     host to press Home (so the app leaves during the fullscreen transition); 3 s later bring the
     app back; 6 s later read the log.
  B  a real hidden spell: Home for 6 s, back, 6 s later read the log. With `lazy_unload: [hidden]`
     a working card unloads and reloads the stream here (a new video element or MediaStream).
Results in $OUT_DIR/blip-interrupt-<label>.json and a summary on stdout.
"""
import asyncio, json, os, sys

sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, "/lab/tools/cdp")
from blip import LOG, summarise  # noqa: E402
from lablib import Cdp, TEST_PATH, connect, save_result  # noqa: E402

LOG = LOG.replace("__FRAMES__", "false")

# Seconds from scheduling Home to pressing it (the device-side start of `cmd input` adds to it).
DELAYS = [float(x) for x in os.environ.get("HOME_DELAYS", "0.05,0.2,0.4").split(",")]


async def host(action, token):
    """Ask the host (blip-interrupt.sh) for `action`, wait for its confirmation."""
    try:
        os.remove("/out/host-done")
    except FileNotFoundError:
        pass
    print(f"HOSTACT {action} {token}", flush=True)
    for _ in range(150):
        try:
            if open("/out/host-done").read().strip() == token:
                return
        except FileNotFoundError:
            pass
        await asyncio.sleep(0.05)
    raise SystemExit(f"the host did not confirm '{action}' within 7.5 s")


async def main(label, rounds):
    async with await connect() as ws:
        cdp = Cdp(ws)
        ev = cdp.ev
        await cdp.goto(TEST_PATH)
        playing = await cdp.wait_playing()
        print(label, "playing:", playing, flush=True)
        await asyncio.sleep(3)
        read = "JSON.stringify({events: window.__blip.events, frames: window.__blip.frames, end: Math.round(performance.now() - window.__blip.t0), fs: !!document.fullscreenElement})"
        runs = []
        for i in range(rounds):
            tok = f"{label}-{i}-{os.getpid()}"
            await ev(LOG)
            # Home is scheduled on the device first (no adb start-up in between), the request
            # follows at once; the delay varies per round so Home lands at different moments.
            delay = DELAYS[i % len(DELAYS)]
            await host(f"homein {delay}", tok + "-a1")
            await ev("(() => { window.__blip.card._controller.getFullscreenManager().setFullscreen(true); return 1; })()", gesture=True)
            await asyncio.sleep(1)
            await asyncio.sleep(3)
            await host("front", tok + "-a2")
            await asyncio.sleep(6)
            a = json.loads(await ev(read))
            if a["fs"]:
                await ev("document.exitFullscreen().then(() => 1, () => 0)")
                await asyncio.sleep(2)
            await ev(LOG)
            await host("home", tok + "-b1")
            await asyncio.sleep(6)
            await host("front", tok + "-b2")
            await asyncio.sleep(6)
            b = json.loads(await ev(read))
            runs.append({"interrupted": a, "real_hide": b})
            await asyncio.sleep(2)
        await ev("(() => { cancelAnimationFrame(window.__blip.raf); return 1; })()")
        save_result(f"blip-interrupt-{label}", runs)
        print("Home delays per round (s):", DELAYS)
        print("round phase | fullscreen after | events (ms) | new video | muted/paused flips | no-video ms")
        for i, r in enumerate(runs):
            for phase in ("interrupted", "real_hide"):
                s = summarise(r[phase])
                print(f"{label} {i + 1} {phase} | {r[phase]['fs']} | {s['order']} | {s['new_video'] or '-'} | {s['flips'] or '-'} | {s['no_video_ms']}")


asyncio.run(main(sys.argv[1], int(sys.argv[2])))
