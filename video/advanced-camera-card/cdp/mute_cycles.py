"""mute_cycles.py <label> <cycles> <toggle|back|swipe|bg|switcher|off>: does the card stay unmuted through repeated
fullscreen enters and leaves? Opens TEST_PATH, waits for video, unmutes the live view with the card's
`unmute` action (a user gesture), then <cycles> times: enter fullscreen through the card's fullscreen
manager, 3 s, leave (`toggle`: the fullscreen manager again; `back`: the Android back key; `swipe`:
two edge swipes, the gesture-navigation way out; both sent by the host: HOSTACT, see card.sh), 3 s.
`bg`, `switcher`, `off`: from fullscreen out of the app for $BG_SECONDS (5) by Home, the app
switcher or the screen off, back, a state step, then leave with the toggle (in fullscreen only
`switcher` and `off` hide the page). After each step: the visible video's `muted`, whether it is the
same element as before, and the page's visibility events since the last step.
"""
import asyncio, json, os, sys

sys.path.insert(0, "/lab/tools/cdp")
from lablib import Cdp, TEST_PATH, card_js, connect, save_result  # noqa: E402

STATE = r"""
(() => {
  const w = (r, o = []) => { for (const el of r.querySelectorAll('*')) { if (el.tagName === 'VIDEO') o.push(el); if (el.shadowRoot) w(el.shadowRoot, o); } return o; };
  const v = w(document).filter((x) => x.getBoundingClientRect().height > 20 && !x.paused);
  window.__mc = window.__mc || { next: 1, ev: [] };
  const out = v.map((x) => { if (!x.__mcid) x.__mcid = window.__mc.next++; return { id: x.__mcid, muted: x.muted, hasAudio: !!(x.srcObject ? x.srcObject.getAudioTracks().length : x.mozHasAudio ?? x.webkitAudioDecodedByteCount > 0) }; });
  const ev = window.__mc.ev.splice(0);
  return JSON.stringify({ videos: out, events: ev, fs: !!document.fullscreenElement });
})()
"""
WATCH = r"""
(() => {
  if (window.__mcw) return 'already';
  window.__mcw = 1; window.__mc = window.__mc || { next: 1, ev: [] };
  for (const e of ['visibilitychange', 'fullscreenchange']) document.addEventListener(e, () => window.__mc.ev.push(e === 'visibilitychange' ? document.visibilityState : (document.fullscreenElement ? 'fs-on' : 'fs-off')), true);
  return 'ok';
})()
"""


async def host(action, token):
    try:
        os.remove("/out/host-done")
    except FileNotFoundError:
        pass
    print(f"HOSTACT {action} {token}", flush=True)
    for _ in range(200):
        try:
            if open("/out/host-done").read().strip() == token:
                return
        except FileNotFoundError:
            pass
        await asyncio.sleep(0.05)
    raise SystemExit(f"the host did not confirm {action}")


async def main(label, cycles, leave):
    async with await connect() as ws:
        cdp = Cdp(ws)
        await cdp.goto(TEST_PATH)
        print(label, "playing:", await cdp.wait_playing(), flush=True)
        await cdp.ev(WATCH)
        act = "card._controller.getActionsManager().executeActions({ actions: { action: 'fire-dom-event', advanced_camera_card_action: '%s' } }); return 1;"
        await cdp.ev(card_js(act % "unmute"), gesture=True, wait=False)
        await asyncio.sleep(2)
        rows = [["start (unmuted)", json.loads(await cdp.ev(STATE))]]
        for i in range(1, cycles + 1):
            await cdp.ev(card_js("card._controller.getFullscreenManager().setFullscreen(true); return 1;"), gesture=True, wait=False)
            await asyncio.sleep(3)
            rows.append([f"{i} enter", json.loads(await cdp.ev(STATE))])
            if leave in ("bg", "switcher", "off"):
                # From fullscreen out of the app for BG_SECONDS and back: Home (bg), the app
                # switcher, or the screen off; the host does it (lib.sh leave_app/return_app).
                way = "home" if leave == "bg" else leave
                await host(f"leave-{way}", f"{label}-{i}-l-{os.getpid()}")
                await asyncio.sleep(float(os.environ.get("BG_SECONDS", "5")))
                await host(f"return-{way}", f"{label}-{i}-r-{os.getpid()}")
                await asyncio.sleep(4)
                rows.append([f"{i} back from the background", json.loads(await cdp.ev(STATE))])
                await cdp.ev(card_js("card._controller.getFullscreenManager().setFullscreen(false); return 1;"), gesture=True, wait=False)
            elif leave in ("back", "swipe"):
                await host(leave, f"{label}-{i}-{os.getpid()}")
            else:
                await cdp.ev(card_js("card._controller.getFullscreenManager().setFullscreen(false); return 1;"), gesture=True, wait=False)
            await asyncio.sleep(3)
            rows.append([f"{i} leave", json.loads(await cdp.ev(STATE))])
        save_result(f"mute-cycles-{label}-{leave}", rows)
        print("step | fullscreen | videos (id, muted) | visibility/fullscreen events since the last step")
        for name, st in rows:
            vids = " ".join(f"{v['id']}:{'MUTED' if v['muted'] else 'unmuted'}" for v in st["videos"]) or "no video"
            print(f"{label} {name} | {st['fs']} | {vids} | {' '.join(st['events']) or '-'}")


if __name__ == "__main__":
    asyncio.run(main(sys.argv[1], int(sys.argv[2]), sys.argv[3]))
