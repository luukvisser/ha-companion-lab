// page-clock.js: run in the app's page over plain CDP (tools/cdp.sh). Draws the device's own clock
// (Date.now() modulo 2^21 ms, 21 black/white blocks) in a fixed bar at the bottom of the page,
// redrawn every animation frame, so every screen-recorded frame carries the device time it was
// drawn at. Returns where that bar and the playing video's picture are on screen (device pixels).
(() => {
  const BITS = 21;
  let bar = document.getElementById('lab-clock');
  if (!bar) {
    bar = document.createElement('div');
    bar.id = 'lab-clock';
    bar.style.cssText =
      'position:fixed;left:0;bottom:0;height:24px;width:' + BITS * 19 + 'px;background:#000;' +
      'z-index:2147483647;pointer-events:none;display:flex;';
    for (let k = 0; k < BITS; k++) {
      const b = document.createElement('div');
      b.style.cssText = 'width:15px;height:18px;margin:3px 2px;background:#000;';
      bar.append(b);
    }
    document.body.append(bar);
    // A magenta strip right above the bar: a colour nothing else on screen uses, so the analysis
    // finds the page on the screen recording (status and navigation bars, insets) by this alone.
    const mark = document.createElement('div');
    mark.id = 'lab-clock-mark';
    mark.style.cssText = 'position:fixed;left:0;bottom:24px;height:6px;width:' + BITS * 19 + 'px;' +
      'background:#ff00ff;z-index:2147483647;pointer-events:none;';
    document.body.append(mark);
    const draw = () => {
      const v = Date.now() % (1 << BITS);
      for (let k = 0; k < BITS; k++) bar.children[k].style.background = (v >> k) & 1 ? '#fff' : '#000';
      requestAnimationFrame(draw);
    };
    requestAnimationFrame(draw);
  }
  // The playing video, searched through shadow roots; its picture inside the element (contain).
  const vids = [];
  const walk = (r) => {
    for (const el of r.querySelectorAll('*')) {
      if (el.tagName === 'VIDEO') vids.push(el);
      if (el.shadowRoot) walk(el.shadowRoot);
    }
  };
  walk(document);
  const v = vids.filter((x) => x.videoWidth > 0 && !x.paused).sort((a, b) => b.clientWidth - a.clientWidth)[0];
  const dpr = devicePixelRatio;
  const out = { dpr, bits: BITS };
  const br = bar.getBoundingClientRect();
  out.clock = { x: br.left * dpr, y: br.top * dpr, w: br.width * dpr, h: br.height * dpr };
  const mr = document.getElementById('lab-clock-mark').getBoundingClientRect();
  out.mark = { x: mr.left * dpr, y: mr.top * dpr, w: mr.width * dpr, h: mr.height * dpr };
  if (v) {
    const r = v.getBoundingClientRect();
    const s = Math.min(r.width / v.videoWidth, r.height / v.videoHeight);
    const w = v.videoWidth * s, h = v.videoHeight * s;
    out.video = { x: (r.left + (r.width - w) / 2) * dpr, y: (r.top + (r.height - h) / 2) * dpr, w: w * dpr, h: h * dpr, vw: v.videoWidth, vh: v.videoHeight };
  }
  return JSON.stringify(out);
})()
