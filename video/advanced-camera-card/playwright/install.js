
(() => {
  const deep = (root, sel) => {
    const found = root.querySelector(sel);
    if (found) return found;
    for (const el of root.querySelectorAll('*')) {
      if (el.shadowRoot) { const f = deep(el.shadowRoot, sel); if (f) return f; }
    }
    return null;
  };
  document.getElementById('acc-measure')?.remove();
  const wrap = document.createElement('div');
  wrap.id = 'acc-measure';
  wrap.style.cssText = 'position:fixed;top:0;left:0;right:0;z-index:99999;background:#fff;padding:8px;';
  const btn = document.createElement('button');
  btn.textContent = 'FS';
  btn.style.cssText = 'display:block;width:100%;height:60px;font-size:24px;';
  const card = document.createElement('advanced-camera-card');
  card.setConfig({ type: 'custom:advanced-camera-card', cameras: [{ camera_entity: '__CAMERA__' }] });
  card.hass = document.querySelector('home-assistant').hass;
  btn.addEventListener('click', () => {
    window.__acc.t0 = performance.now();
    window.__acc.events.push([0, 'click']);
    card.requestFullscreen().catch((e) => window.__acc.events.push([0, 'request-error ' + e.message]));
  });
  wrap.append(btn, card);
  document.body.append(wrap);
  const acc = (window.__acc = { t0: performance.now(), events: [], frames: [], card, deep });
  const t = () => Math.round(performance.now() - acc.t0);
  const fsName = () => (document.fullscreenElement ? document.fullscreenElement.tagName.toLowerCase() : '-');
  for (const ev of ['visibilitychange', 'fullscreenchange', 'freeze', 'resume', 'pagehide', 'pageshow']) {
    document.addEventListener(ev, () => acc.events.push([t(), ev, document.visibilityState, fsName()]), true);
  }
  window.addEventListener('resize', () => acc.events.push([t(), 'resize', innerWidth + 'x' + innerHeight]));
  const step = () => {
    const c = deep(card.shadowRoot || card, 'advanced-camera-card-live-carousel');
    if (c) {
      const r = c.getBoundingClientRect();
      acc.frames.push([t(), document.visibilityState[0], fsName() !== '-' ? 1 : 0,
        Math.round(r.top), Math.round(r.height), innerHeight, getComputedStyle(c).maxHeight, deep(card.shadowRoot, 'web-dialog') ? 1 : 0]);
    }
    requestAnimationFrame(step);
  };
  requestAnimationFrame(step);
  return 'installed';
})()
