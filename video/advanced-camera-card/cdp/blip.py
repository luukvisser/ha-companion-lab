"""blip.py <label> <rounds>: what entering and leaving fullscreen does to the dashboard card's live
media, in the Companion app's WebView, over plain CDP (so visibility events stay real).

Uses the card Home Assistant serves on the test dashboard (TEST_PATH); run it through blip.sh, which
installs the build and starts the app fresh. Per round: enter fullscreen through the card's own fullscreen manager
(Runtime.evaluate with a user gesture), wait, leave with document.exitFullscreen(), wait.

Logged page-side, per round and phase: document events (visibilitychange, fullscreenchange,
resize) and, per animation frame, every <video> inside the card: a stable element id, its source
(webrtc = MediaStream, media = HLS/MSE), muted, paused, has data. Results in
$OUT_DIR/blip-<label>.json and a summary on stdout:
  hidden ms         time between visibilitychange hidden and visible
  order             the order of hidden, visible and fullscreenchange
  new video         a <video> element (or MediaStream) appeared that was not there before
  muted/paused      flips of the playing video's muted or paused state
  no-video ms       time without a visible playing video inside the card
"""
import asyncio, json, os, sys

sys.path.insert(0, "/lab/tools/cdp")
from lablib import Cdp, TEST_PATH, connect, save_result  # noqa: E402


LOG = r"""
(() => {
  const deep = (root, sel, out = []) => { for (const el of root.querySelectorAll('*')) { if (el.matches(sel)) out.push(el); if (el.shadowRoot) deep(el.shadowRoot, sel, out); } return out; };
  const card = deep(document, 'advanced-camera-card')[0];
  if (!card) return 'no card';
  if (window.__blip) { cancelAnimationFrame(window.__blip.raf); for (const [ev, f] of window.__blip.listeners) document.removeEventListener(ev, f, true); }
  const b = (window.__blip = { t0: performance.now(), events: [], frames: [], vf: [], card, listeners: [], nextId: 1, streams: new WeakMap() });
  const t = () => Math.round(performance.now() - b.t0);
  for (const ev of ['visibilitychange', 'fullscreenchange']) {
    const f = () => b.events.push([t(), ev, document.visibilityState, document.fullscreenElement ? 1 : 0]);
    document.addEventListener(ev, f, true); b.listeners.push([ev, f]);
  }
  let last = '';
  // BLIP_FRAMES: per presented frame of a visible video, requestVideoFrameCallback's own counter
  // (presentedFrames; free), and at most once a second the `sync` stream's frame number (a 16-bit code
  // in the top band, bit i a white box in the 64 px cell i). Reading pixels costs about 89 ms per read
  // in the emulator (software rendering; 10-11-2026), so it anchors, it does not count.
  const FRAMES = __FRAMES__;
  if (FRAMES && !b.cv) { b.cv = document.createElement('canvas'); b.cv.width = 256; b.cv.height = 15; b.cx = b.cv.getContext('2d', { willReadFrequently: true }); }
  const watch = (v) => {
    if (!FRAMES || v.__rvfc || !v.requestVideoFrameCallback) return;
    v.__rvfc = 1;
    const cb = (now, md) => {
      const B = window.__blip;
      const vis = v.getBoundingClientRect().height > 20 && (v.checkVisibility ? v.checkVisibility({ checkOpacity: true, checkVisibilityCSS: true }) : true);
      if (B && vis) {
        const t = Math.round(performance.now() - B.t0);
        let code = null;
        if (B.cx && v.videoWidth >= 1024 && (B.lastRead === undefined || t - B.lastRead >= 1000)) {
          B.lastRead = t;
          B.cx.drawImage(v, 0, 0, 1024, 60, 0, 0, 256, 15);
          const px = B.cx.getImageData(0, 7, 256, 1).data;
          code = 0;
          for (let i = 0; i < 16; i++) if (px[(8 + 16 * i) * 4] > 128) code |= 1 << i;
        }
        B.vf.push([t, v.__bid, md.presentedFrames, code]);
      }
      v.requestVideoFrameCallback(cb);
    };
    v.requestVideoFrameCallback(cb);
  };
  const step = () => {
    const vids = deep(card.shadowRoot, 'video');
    vids.forEach((v) => { if (!v.__bid) v.__bid = b.nextId++; watch(v); });
    const st = vids.map((v) => {
      if (!v.__bid) v.__bid = b.nextId++;
      let src = 'media';
      if (v.srcObject) { if (!b.streams.has(v.srcObject)) b.streams.set(v.srcObject, b.nextId++); src = 'rtc' + b.streams.get(v.srcObject); }
      const vis = v.getBoundingClientRect().height > 20 && (v.checkVisibility ? v.checkVisibility({ checkOpacity: true, checkVisibilityCSS: true }) : true);
      return [v.__bid, src, v.muted ? 'M' : 'u', v.paused ? 'P' : 'p', v.readyState >= 2 && v.videoWidth > 0 ? 'D' : 'd', vis ? 'V' : 'v'];
    });
    const key = JSON.stringify(st);
    if (key !== last) { b.frames.push([t(), st]); last = key; }
    b.raf = requestAnimationFrame(step);
  };
  b.raf = requestAnimationFrame(step);
  return 'ok';
})()
"""


def summarise(phase):
    ev, fr = phase["events"], phase["frames"]
    hid = [e[0] for e in ev if e[1] == "visibilitychange" and e[2] == "hidden"]
    vis = [e[0] for e in ev if e[1] == "visibilitychange" and e[2] == "visible"]
    hidden_ms = (vis[0] - hid[0]) if hid and vis else None
    order = " ".join(f"{'hidden' if e[1] == 'visibilitychange' and e[2] == 'hidden' else 'visible' if e[1] == 'visibilitychange' else 'fschange'}@{e[0]}" for e in ev)
    playing = lambda st: [v for v in st if v[3] == "p" and v[4] == "D" and v[5] == "V"]
    first = playing(fr[0][1]) if fr else []
    base_ids = {(v[0], v[1]) for v in first}
    new = sorted({f"{v[0]}/{v[1]}" for _, st in fr for v in playing(st) if (v[0], v[1]) not in base_ids})
    flips = []
    prev = {v[0]: v for v in first}
    for t, st in fr:
        for v in st:
            p = prev.get(v[0])
            if p and (p[2] != v[2] or p[3] != v[3]):
                flips.append(f"{v[0]}:{p[2]}{p[3]}>{v[2]}{v[3]}@{t}")
            prev[v[0]] = v
    gap = 0
    for i, (t, st) in enumerate(fr):
        end = fr[i + 1][0] if i + 1 < len(fr) else phase["end"]
        if not playing(st):
            gap += end - t
    out = {"hidden_ms": hidden_ms, "order": order, "new_video": new, "flips": flips, "no_video_ms": gap}
    vf = phase.get("vf") or []
    if vf:
        # Presented frames (the sum of each element's presentedFrames increase), the longest time
        # without a presented frame, and the source frames never presented: between the first and the
        # last frame-number read of the same element, the source advanced (code difference) while
        # the element presented fewer frames.
        by = {}
        for t, el, pf, code in vf:
            by.setdefault(el, []).append((t, pf, code))
        presented = sum(max(x[1] for x in rows) - min(x[1] for x in rows) for rows in by.values())
        missed = []
        for rows in by.values():
            reads = [r for r in rows if r[2] is not None]
            if len(reads) >= 2:
                missed.append((reads[-1][2] - reads[0][2]) - (reads[-1][1] - reads[0][1]))
        out["frames"] = {"presented": presented,
                         "max_still_ms": max((b[0] - a[0] for a, b in zip(vf, vf[1:])), default=0),
                         "source_not_presented": sum(missed) if missed else None,
                         "elements": len(by)}
    return out


async def main(label, rounds):
    async with await connect() as ws:
        cdp = Cdp(ws)
        call, ev = cdp.call, cdp.ev
        # In-app navigation, not a page load (lablib.Cdp.goto).
        await cdp.goto(TEST_PATH)
        playing = await cdp.wait_playing()
        print(label, "playing:", playing, "card files:", " ".join(await cdp.card_files()), flush=True)
        await asyncio.sleep(3)
        global LOG
        LOG = LOG.replace("__FRAMES__", "true" if os.environ.get("BLIP_FRAMES") else "false")
        runs = []
        for i in range(rounds):
            out = {}
            for phase in ("enter", "leave"):
                print(label, i + 1, phase, await ev(LOG), flush=True)
                if phase == "enter":
                    await ev("(() => { window.__blip.events.push([0, 'request']); window.__blip.card._controller.getFullscreenManager().setFullscreen(true); return 1; })()", gesture=True)
                else:
                    await ev("document.exitFullscreen().then(() => 1, () => 0)")
                await asyncio.sleep(5)
                out[phase] = json.loads(await ev("JSON.stringify({events: window.__blip.events.filter((e) => e[1] !== 'request'), frames: window.__blip.frames, vf: window.__blip.vf, end: Math.round(performance.now() - window.__blip.t0)})"))
            runs.append(out)
            await asyncio.sleep(2)
        await ev("(() => { cancelAnimationFrame(window.__blip.raf); return 1; })()")
        save_result(f"blip-{label}", runs)
        print("round phase | hidden ms | order (ms) | new video | muted/paused flips | no-video ms")
        for i, r in enumerate(runs):
            for phase in ("enter", "leave"):
                s = summarise(r[phase])
                print(f"{label} {i + 1} {phase} | {s['hidden_ms']} | {s['order']} | {s['new_video'] or '-'} | {s['flips'] or '-'} | {s['no_video_ms']}" + (f" | {s['frames']}" if "frames" in s else ""))


if __name__ == "__main__":
    asyncio.run(main(sys.argv[1], int(sys.argv[2])))
