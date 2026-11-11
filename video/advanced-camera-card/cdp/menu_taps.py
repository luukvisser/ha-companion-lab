"""menu_taps.py <label> <rounds> [loading|playing] [targets] : does a menu button work while the
media loads? Per target (menu button labels, |-separated; default Fullscreen|Live view|Play / Pause)
and round: leave the test dashboard, come back, and once the menu has the target, TAP_AFTER seconds
have passed (default 0.7: the menu settles in about 0.4 s) and no video plays yet (`loading`), or
once a video plays (`playing`, the control), tap the button's centre with a real touch (CDP
Input.dispatchTouchEvent; its position is read again right before the tap, as the menu may move).

Traced per tap, in the page: what the tap reached (the element under the point, through the shadow
roots), the action the menu ran for it (handleAction: the button's title and tap_action), whether
the card executed it, and for fullscreen, the card's toggle and every requestFullscreen call with its
outcome. Then 4 s of the state: a video playing, document.fullscreenElement, the fullscreen button's
icon, the target inert or not. Reaches into the card's internals (`_controller`): a lab trace, not
an interface, so a card refactor may need it adapted.

In the emulator a CDP touch is often followed by the mouse events the WebView derives from it, so
one tap can run the button's action twice (a toggle then undoes itself): the trace shows it. A tap
read too early can land on another button while the menu still grows: the `reached` element and
the traced title show which."""
import asyncio, json, os, sys, time

sys.path.insert(0, "/lab/tools/cdp")
from lablib import Cdp, OTHER_PATH, TEST_PATH, connect, save_result  # noqa: E402

WHEN = sys.argv[3] if len(sys.argv) > 3 else "loading"
TARGETS = (sys.argv[4] if len(sys.argv) > 4 and sys.argv[4] else "Fullscreen|Live view|Play / Pause").split("|")
TAP_AFTER = float(os.environ.get("TAP_AFTER", "0.7"))

DEEP = ("const deep = (r, t, o = []) => { for (const el of r.querySelectorAll('*')) { "
        "if (el.tagName.toLowerCase() === t) o.push(el); if (el.shadowRoot) deep(el.shadowRoot, t, o); } return o; };")

# Every requestFullscreen call (element) and how it ended.
FSWRAP = r"""(() => {
  window.__fs = [];
  if (!Element.prototype.__labRFS) Element.prototype.__labRFS = Element.prototype.requestFullscreen;
  Element.prototype.requestFullscreen = function (...a) {
    const e = { el: this.tagName.toLowerCase() }; window.__fs.push(e);
    const p = Element.prototype.__labRFS.apply(this, a);
    p.then(() => { e.result = 'ok'; }, (err) => { e.result = String(err).slice(0, 160); });
    return p;
  };
  return 1;
})()"""

# Traces from now on: the menu's handleAction, the card's executeActions and fullscreen toggle.
TRACE = "(() => { " + DEEP + r"""
  window.__tr = []; const t0 = performance.now(); const at = () => Math.round(performance.now() - t0);
  const menu = deep(document, 'advanced-camera-card-menu')[0];
  const card = deep(document, 'advanced-camera-card')[0];
  const wrap = (o, name, info) => { if (!o || o['__lab_' + name]) return; const orig = o[name]; o['__lab_' + name] = 1;
    o[name] = function (...a) { window.__tr && window.__tr.push(`${name}@${at()} ${info(a)}`); return orig.apply(this, a); }; };
  wrap(menu && menu._controller, 'handleAction', (a) => `${a[0].detail.action} on "${a[1]?.title}" tap_action=${JSON.stringify(a[1]?.tap_action ?? null)}`);
  const c = card && card._controller;
  wrap(c && c.getActionsManager(), 'executeActions', (a) => JSON.stringify(a[0]?.actions).slice(0, 120));
  wrap(c && c.getFullscreenManager(), 'toggleFullscreen', () => '');
  return 1;
})()"""

STATE = "((target) => { " + DEEP + r"""
  const menu = deep(document, 'advanced-camera-card-menu')[0];
  const btns = menu && menu.shadowRoot ? [...menu.shadowRoot.querySelectorAll('ha-icon-button')] : [];
  const icon = (b) => { const ic = b?.querySelector('advanced-camera-card-icon')?.icon; return ic && typeof ic === 'object' ? (ic.icon ?? null) : (ic ?? null); };
  const hit = (x, y) => { let root = document, el = null; const path = [];
    for (let i = 0; i < 30; i++) { const e = root.elementFromPoint(x, y); if (!e || e === el) break; el = e; path.push(e.tagName.toLowerCase()); if (!e.shadowRoot) break; root = e.shadowRoot; }
    return path.slice(-3).join(' > '); };
  const t = btns.find((b) => b.label === target);
  const r = t ? t.getBoundingClientRect() : null;
  return JSON.stringify({
    playing: deep(document, 'video').some((v) => !v.paused && v.readyState >= 3 && v.getBoundingClientRect().height > 20),
    fullscreen: !!document.fullscreenElement,
    fsIcon: icon(btns.find((b) => b.label === 'Fullscreen')),
    target: t ? { index: btns.indexOf(t), inert: !!t.disabled, x: r.x + r.width / 2, y: r.y + r.height / 2, hit: hit(r.x + r.width / 2, r.y + r.height / 2) } : null,
  });
})"""


async def main(label, rounds):
    async with await connect() as ws:
        cdp = Cdp(ws)
        await cdp.goto(TEST_PATH)
        print(label, "playing:", await cdp.wait_playing(), flush=True)

        async def state(target):
            return json.loads(await cdp.ev(STATE + f"({json.dumps(target)})"))

        async def tap(x, y):
            await cdp.call("Input.dispatchTouchEvent", type="touchStart", touchPoints=[{"x": x, "y": y}])
            await asyncio.sleep(0.05)
            await cdp.call("Input.dispatchTouchEvent", type="touchEnd", touchPoints=[])

        results = []
        for target in TARGETS:
            for i in range(1, rounds + 1):
                await cdp.ev("document.fullscreenElement && document.exitFullscreen()")
                await cdp.goto(OTHER_PATH)
                await asyncio.sleep(3)
                await cdp.ev(FSWRAP)
                await cdp.goto(TEST_PATH)
                t0 = time.monotonic()
                tapped = None
                while time.monotonic() - t0 < 10:
                    s = await state(target)
                    if s["playing"] and WHEN == "loading":
                        break
                    if s["target"] and time.monotonic() - t0 > TAP_AFTER and (WHEN == "loading" or s["playing"]):
                        await cdp.ev(TRACE)
                        s = await state(target)
                        if (s["playing"] and WHEN == "loading") or not s["target"]:
                            break
                        await tap(s["target"]["x"], s["target"]["y"])
                        tapped = {"ms": round((time.monotonic() - t0) * 1000), **s}
                        break
                    await asyncio.sleep(0.03)
                after, last = [], None
                if tapped:
                    t1 = time.monotonic()
                    while time.monotonic() - t1 < 4:
                        s = await state(target)
                        k = (s["playing"], s["fullscreen"], s["fsIcon"], s["target"] and s["target"]["inert"])
                        if k != last:
                            last = k
                            after.append({"ms": round((time.monotonic() - t1) * 1000), "playing": k[0],
                                          "fullscreen": k[1], "fsIcon": k[2], "targetInert": k[3]})
                        await asyncio.sleep(0.05)
                trace = json.loads(await cdp.ev("JSON.stringify(window.__tr || [])"))
                fs = json.loads(await cdp.ev("JSON.stringify(window.__fs || [])"))
                results.append({"target": target, "round": i, "when": WHEN, "tapped": tapped, "trace": trace,
                                "requestFullscreen": fs, "after": after})
                if not tapped:
                    print(f"--- {target} round {i}: not tapped (a video played before the moment came)")
                    continue
                print(f"--- {target} round {i}: tapped {tapped['ms']} ms after the return, playing={tapped['playing']}, "
                      f"inert={tapped['target']['inert']}, menu index {tapped['target']['index']}, reached: {tapped['target']['hit']}")
                for line in trace:
                    print(f"    {line}")
                print(f"    requestFullscreen: {fs}")
                for e in after:
                    print(f"    +{e['ms']:>5} ms  {'PLAY' if e['playing'] else '----'}  fullscreen={e['fullscreen']} "
                          f"fsIcon={e['fsIcon']} targetInert={e['targetInert']}")
        save_result(f"menu-taps-{label}", results)


if __name__ == "__main__":
    asyncio.run(main(sys.argv[1], int(sys.argv[2])))
