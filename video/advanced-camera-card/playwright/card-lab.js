// card-lab.js: shared by the card layer's Playwright scripts.
//
// - serveVariant(page, variant): serve card build <variant> from /builds/<variant>/ to this page by
//   intercepting CARD_PREFIX; `deployed` (or a function returning it) leaves the requests to Home
//   Assistant. Interception lasts only while Playwright is attached: a script that detaches (e.g.
//   lf-setup.js before background rounds) leaves later card requests to Home Assistant, so check the
//   run with verifyVariant, or install the build in a stack the lab controls instead
//   (stack/stack.sh card <build>), which needs no interception.
// - verifyVariant(page, variant): which card files the page loaded, and whether all of them belong
//   to that build (the chunk file names carry a content hash, so a chunk from another build shows up
//   as foreign). Needs INSTRUMENT (it enlarges the resource timing buffer).
// - INSTRUMENT: the page log of frame captures and long tasks (window.__lf), as an init script.
const fs = require('fs');
const path = require('path');
const { CARD_PREFIX } = require('/lab/tools/playwright/lab-config');

const variantOf = (variant) => (typeof variant === 'function' ? variant() : variant);

async function serveVariant(page, variant) {
  if (variant === 'deployed') return;
  await page.route('**' + CARD_PREFIX + '**', (route) => {
    const v = variantOf(variant);
    if (v === 'deployed') return route.continue();
    const file = path.join('/builds', v, new URL(route.request().url()).pathname.split(CARD_PREFIX)[1]);
    return fs.existsSync(file)
      ? route.fulfill({ status: 200, contentType: 'application/javascript', headers: { 'Cache-Control': 'no-store' }, body: fs.readFileSync(file) })
      : route.fulfill({ status: 404, body: '' });
  });
}

async function verifyVariant(page, variant) {
  const loaded = await page.evaluate((prefix) => [...new Set(performance.getEntriesByType('resource')
    .map((e) => new URL(e.name).pathname).filter((p) => p.includes(prefix))
    .map((p) => p.split(prefix)[1]))], CARD_PREFIX);
  if (!variant || variant === 'deployed') return { variant: variant || null, loaded, ok: null };
  const dir = path.join('/builds', variant);
  const own = fs.existsSync(dir) ? new Set(fs.readdirSync(dir)) : new Set();
  const foreign = loaded.filter((f) => !own.has(f));
  return { variant, loaded, foreign, ok: loaded.length > 0 && foreign.length === 0 };
}

const INSTRUMENT = () => {
  // Keep every resource entry: verifyVariant reads which card files were loaded.
  try { performance.setResourceTimingBufferSize(5000); } catch (e) { /* older engines */ }
  const acc = (window.__lf = { t0: performance.now(), caps: [], draws: [], longtasks: [] });
  const t = () => Math.round(performance.now() - acc.t0);
  const draw = CanvasRenderingContext2D.prototype.drawImage;
  CanvasRenderingContext2D.prototype.drawImage = function (src, ...rest) {
    const s = performance.now();
    const r = draw.call(this, src, ...rest);
    if (src instanceof HTMLVideoElement) acc.draws.push([t(), this.canvas.width, this.canvas.height, +(performance.now() - s).toFixed(1)]);
    return r;
  };
  const toBlob = HTMLCanvasElement.prototype.toBlob;
  HTMLCanvasElement.prototype.toBlob = function (cb, type, q) {
    const s = performance.now(); const w = this.width; const h = this.height;
    return toBlob.call(this, (blob) => { acc.caps.push(['toBlob', t(), w, h, Math.round(performance.now() - s), blob ? blob.size : 0, q]); cb(blob); }, type, q);
  };
  const toDataURL = HTMLCanvasElement.prototype.toDataURL;
  HTMLCanvasElement.prototype.toDataURL = function (type, q) {
    const s = performance.now();
    const r = toDataURL.call(this, type, q);
    acc.caps.push(['toDataURL', t(), this.width, this.height, +(performance.now() - s).toFixed(1), Math.round((r.length - 23) * 0.75), q]);
    return r;
  };
  try {
    new PerformanceObserver((l) => l.getEntries().forEach((e) => acc.longtasks.push([Math.round(e.startTime - acc.t0), Math.round(e.duration)]))).observe({ type: 'longtask', buffered: false });
  } catch (e) { acc.longtasks.push(['unsupported']); }
};

module.exports = { serveVariant, verifyVariant, INSTRUMENT };
