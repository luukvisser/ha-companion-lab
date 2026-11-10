// lf-setup.js <variant>: loads the test dashboard (TEST_PATH) with card build <variant> (from
// /builds, or `deployed` for the card Home Assistant serves), instruments the page and detaches, so
// visibility events behave normally afterwards (Playwright suppresses them while attached).
// The page log (window.__lf): frame captures (canvas size, drawImage and encode times, JPEG bytes),
// long tasks, visibility changes, a per-second video sample, and per animation frame what the card
// shows (`show`: visible playing videos, visible loaded data: images, canvases), when each data:
// image was decoded (`dec`), and gaps between animation frames over 100 ms (`gaps`).
// Caution: `show` counts an <img> as shown once it is loaded, also while it is still blank on screen
// (not yet decoded); only a screen recording (bg-video.sh) shows what was really on screen.
// Read the log with lf-read.js.
const fs = require('fs');
const path = require('path');
const { _android: android } = require('playwright-core');
const { PKG, CARD_PREFIX, TEST_PATH, OTHER_PATH, OVERLAY_CAMERA, pickDevice } = require('/lab/tools/playwright/lab-config');
const { serveVariant, INSTRUMENT } = require('./card-lab');
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const [variant, seconds] = [process.argv[2], +(process.argv[3] || 60)];


(async () => {
  const device = await pickDevice(android);
  const page = await (await device.webView({ pkg: PKG })).page();
  await serveVariant(page, variant);
  await page.addInitScript(INSTRUMENT);
  const origin = new URL(page.url()).origin;
  await page.goto(origin + TEST_PATH + '?external_auth=1');
  // Wait until the live video plays.
  const t0 = Date.now();
  let playing = false;
  while (Date.now() - t0 < 60000 && !playing) {
    await sleep(1000);
    playing = await page.evaluate(() => { const out = []; const walk = (r) => { out.push(...r.querySelectorAll('video')); for (const el of r.querySelectorAll('*')) if (el.shadowRoot) walk(el.shadowRoot); }; walk(document); return out.some((v) => v.currentTime > 1 && !v.paused); });
  }
  console.log(variant, 'playing after', Math.round((Date.now() - t0) / 1000), 's:', playing);
  await page.evaluate(() => { window.__lf.t0 = performance.now(); window.__lf.caps = []; window.__lf.draws = []; window.__lf.longtasks = []; window.__lf.vis = []; window.__lf.samples = []; window.__lf.show = []; (() => { let last = ''; const step = () => { const vids = []; const imgs = []; const cans = []; const walk = (r) => { for (const el of r.querySelectorAll('*')) { const t = el.tagName.toLowerCase(); if (t === 'video') vids.push(el); else if (t === 'img' && el.src && el.src.startsWith('data:')) imgs.push(el); else if (t === 'canvas') cans.push(el); if (el.shadowRoot) walk(el.shadowRoot); } }; walk(document); const vis = (el) => (el.checkVisibility ? el.checkVisibility({ checkOpacity: true, checkVisibilityCSS: true }) : el.offsetParent !== null) && el.getBoundingClientRect().height > 20; const v = vids.filter((x) => vis(x) && x.readyState >= 2 && x.videoWidth > 0).length; const i = imgs.filter((x) => vis(x) && x.complete && x.naturalWidth > 0).length; window.__lf.seen = window.__lf.seen || new WeakSet(); window.__lf.dec = window.__lf.dec || []; for (const im of imgs) { if (!window.__lf.seen.has(im) || im.__src !== im.src) { window.__lf.seen.add(im); im.__src = im.src; const ts = performance.now(); im.decode().then(() => window.__lf.dec.push([Math.round(ts - window.__lf.t0), Math.round(performance.now() - ts), 'ok']), (e) => window.__lf.dec.push([Math.round(ts - window.__lf.t0), Math.round(performance.now() - ts), 'err'])); } } const now = performance.now(); if (window.__lf.lastRaf && now - window.__lf.lastRaf > 100) { (window.__lf.gaps = window.__lf.gaps || []).push([Math.round(window.__lf.lastRaf - window.__lf.t0), Math.round(now - window.__lf.lastRaf)]); } window.__lf.lastRaf = now; window.__lf.ctx = window.__lf.ctx || []; for (const x of cans) { if (!x.__ctxWatch) { x.__ctxWatch = 1; ['contextlost', 'contextrestored'].forEach((ev) => x.addEventListener(ev, () => window.__lf.ctx.push([Math.round(performance.now() - window.__lf.t0), ev, x.width]))); } } const c = cans.filter((x) => vis(x) && x.width > 0).length; const cr = cans.filter((x) => x.width > 0).map((x) => { const r = x.getBoundingClientRect(); const zz = x.closest ? x.closest('advanced-camera-card-zoomer') : null; return `${Math.round(r.left)},${Math.round(r.top)} ${Math.round(r.width)}x${Math.round(r.height)} op${getComputedStyle(x).opacity} z${zz ? getComputedStyle(zz).transform.replace(/matrix\(([^,]+),.*/, '$1') : '-'}`; }).join(';'); const key = `v${v} i${i} c${c} ${document.visibilityState[0]} [${cr}]`; if (key !== last) { window.__lf.show.push([Math.round(performance.now() - window.__lf.t0), key]); last = key; } requestAnimationFrame(step); }; requestAnimationFrame(step); })(); setInterval(() => { const out = []; const walk = (r) => { out.push(...r.querySelectorAll('video')); for (const el of r.querySelectorAll('*')) if (el.shadowRoot) walk(el.shadowRoot); }; walk(document); window.__lf.samples.push([Math.round(performance.now() - window.__lf.t0), out.map((v) => [+v.currentTime.toFixed(1), v.paused ? 'P' : '', v.readyState].join(':')).join(' ')]); }, 1000); document.addEventListener('visibilitychange', () => window.__lf.vis.push([Math.round(performance.now() - window.__lf.t0), document.visibilityState])); });
  await page.unrouteAll({ behavior: 'ignoreErrors' });
  await device.close();
})().catch((e) => { console.error('ERR', e.message.split('\n').slice(0, 3).join(' | ')); process.exit(1); });
