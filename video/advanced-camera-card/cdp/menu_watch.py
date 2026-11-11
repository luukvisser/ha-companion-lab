"""menu_watch.py <label> <rounds> <nav|bg>: how the card's menu changes while the card (re)loads.
A page-side recorder logs, on every animation frame, the menu's buttons (label, inert) and whether a
video plays, keeping only the frames where that changes. Per round: `nav` leaves the test dashboard
for OTHER_PATH and comes back (a new card element: its first load); `bg` sends the app home for
BG_SECONDS and back (the host does it: HOSTACT). Then 10 s of recording. Prints each change with ms
since the return, and the number of distinct button layouts (labels in order, inert ignored)."""
import asyncio, json, os, sys

sys.path.insert(0, "/lab/tools/cdp")
from lablib import Cdp, TEST_PATH, connect, save_result  # noqa: E402

OTHER = os.environ.get("OTHER_PATH", "/profile/general")

REC = r"""
(() => {
  window.__mw = { t0: performance.now(), log: [], last: '' };
  const deep = (r, t, o = []) => { for (const el of r.querySelectorAll('*')) { if (el.tagName.toLowerCase() === t) o.push(el); if (el.shadowRoot) deep(el.shadowRoot, t, o); } return o; };
  const tick = () => {
    if (!window.__mw) return;
    const menu = deep(document, 'advanced-camera-card-menu')[0];
    let buttons = [];
    if (menu && menu.shadowRoot) {
      buttons = [...menu.shadowRoot.querySelectorAll('ha-icon-button, advanced-camera-card-submenu-button, advanced-camera-card-submenu-select-button')]
        .map((b) => (b.label || b.submenu?.title || b.tagName.toLowerCase()) + (b.disabled ? '*' : ''));
    }
    const playing = deep(document, 'video').some((v) => !v.paused && v.readyState >= 3 && v.getBoundingClientRect().height > 20);
    const sig = JSON.stringify([buttons, playing]);
    if (sig !== window.__mw.last) {
      window.__mw.last = sig;
      window.__mw.log.push({ ms: Math.round(performance.now() - window.__mw.t0), buttons, playing });
    }
    requestAnimationFrame(tick);
  };
  requestAnimationFrame(tick);
  return 1;
})()
"""
READ = "(() => { const m = window.__mw; window.__mw = null; return JSON.stringify(m ? m.log : []); })()"


async def host(action, token):
    try:
        os.remove("/out/host-done")
    except FileNotFoundError:
        pass
    print(f"HOSTACT {action} {token}", flush=True)
    for _ in range(400):
        try:
            if open("/out/host-done").read().strip() == token:
                return
        except FileNotFoundError:
            pass
        await asyncio.sleep(0.05)
    raise SystemExit(f"the host did not confirm {action}")


async def main(label, rounds, way):
    async with await connect() as ws:
        cdp = Cdp(ws)
        await cdp.goto(TEST_PATH)
        print(label, "playing:", await cdp.wait_playing(), flush=True)
        results = []
        for i in range(1, rounds + 1):
            if way == "nav":
                await cdp.goto(OTHER)
                await asyncio.sleep(3)
                await cdp.ev(REC)
                await cdp.goto(TEST_PATH)
            else:
                await host("leave-home", f"{label}-{i}-l-{os.getpid()}")
                await asyncio.sleep(float(os.environ.get("BG_SECONDS", "5")))
                # The recorder starts when the page runs again: right after the return.
                await host("return-home", f"{label}-{i}-r-{os.getpid()}")
                await cdp.ev(REC)
            await asyncio.sleep(10)
            log = json.loads(await cdp.ev(READ))
            layouts = []
            for e in log:
                lay = [b.rstrip("*") for b in e["buttons"]]
                if lay not in layouts:
                    layouts.append(lay)
            results.append({"round": i, "log": log, "layouts": len(layouts)})
            print(f"--- {label} {way} round {i}: {len(layouts)} distinct layout(s)")
            for e in log:
                print(f"  {e['ms']:>6} ms  {'PLAY' if e['playing'] else '----'}  {' | '.join(e['buttons']) or '(no menu)'}")
        save_result(f"menu-watch-{label}-{way}", results)


if __name__ == "__main__":
    asyncio.run(main(sys.argv[1], int(sys.argv[2]), sys.argv[3]))
