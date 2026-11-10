// capture-bench.js [rounds]: on the page already showing the test dashboard with a playing video,
// times each step of capturing a frame, per method, and the long tasks each method causes.
const { _android: android } = require('playwright-core');
const { PKG, CARD_PREFIX, TEST_PATH, OTHER_PATH, OVERLAY_CAMERA, pickDevice } = require('/lab/tools/playwright/lab-config');
const rounds = +(process.argv[2] || 5);

const BENCH = async (rounds) => {
  const all = []; const walk = (r) => { all.push(...r.querySelectorAll('video')); for (const el of r.querySelectorAll('*')) if (el.shadowRoot) walk(el.shadowRoot); }; walk(document);
  const video = all.find((v) => !v.paused && v.videoWidth);
  if (!video) return 'no playing video';
  const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
  const longtasks = [];
  const obs = new PerformanceObserver((l) => l.getEntries().forEach((e) => longtasks.push([e.startTime, e.duration])));
  obs.observe({ type: 'longtask' });
  const blobOf = (canvas, q) => new Promise((res) => canvas.toBlob(res, 'image/jpeg', q));
  const W = video.videoWidth, H = video.videoHeight;
  const methods = {
    'toBlob 2d (current code)': async (w, h) => {
      const c = document.createElement('canvas'); c.width = w; c.height = h; const ctx = c.getContext('2d');
      const t0 = performance.now(); ctx.drawImage(video, 0, 0, w, h); const t1 = performance.now();
      const p = blobOf(c, 0.8); const t2 = performance.now(); const b = await p; const t3 = performance.now();
      return { draw: t1 - t0, toBlobSync: t2 - t1, encodeAsync: t3 - t2, bytes: b.size };
    },
    'getImageData 2d (readback only)': async (w, h) => {
      const c = document.createElement('canvas'); c.width = w; c.height = h; const ctx = c.getContext('2d');
      const t0 = performance.now(); ctx.drawImage(video, 0, 0, w, h); const t1 = performance.now();
      ctx.getImageData(0, 0, w, h); const t2 = performance.now();
      return { draw: t1 - t0, readback: t2 - t1 };
    },
    'toBlob 2d willReadFrequently (CPU canvas)': async (w, h) => {
      const c = document.createElement('canvas'); c.width = w; c.height = h; const ctx = c.getContext('2d', { willReadFrequently: true });
      const t0 = performance.now(); ctx.drawImage(video, 0, 0, w, h); const t1 = performance.now();
      const p = blobOf(c, 0.8); const t2 = performance.now(); const b = await p; const t3 = performance.now();
      return { draw: t1 - t0, toBlobSync: t2 - t1, encodeAsync: t3 - t2, bytes: b.size };
    },
    'createImageBitmap + OffscreenCanvas.convertToBlob': async (w, h) => {
      const t0 = performance.now(); const bmpP = createImageBitmap(video, { resizeWidth: w, resizeHeight: h }); const t1 = performance.now();
      const bmp = await bmpP; const t2 = performance.now();
      const oc = new OffscreenCanvas(w, h); const ctx = oc.getContext('2d'); ctx.drawImage(bmp, 0, 0); const t3 = performance.now();
      const p = oc.convertToBlob({ type: 'image/jpeg', quality: 0.8 }); const t4 = performance.now(); const b = await p; const t5 = performance.now();
      return { bitmapSync: t1 - t0, bitmapAsync: t2 - t1, draw: t3 - t2, convertSync: t4 - t3, encodeAsync: t5 - t4, bytes: b.size };
    },
  };
  const out = {};
  for (const [name, fn] of Object.entries(methods)) {
    for (const [label, w, h] of [[`${W}x${H}`, W, H], ['640x360', 640, Math.round(640 * H / W)]]) {
      const rs = [];
      for (let i = 0; i < rounds; i++) {
        await sleep(1500);
        longtasks.length = 0;
        const start = performance.now();
        const r = await fn(w, h);
        await sleep(600);
        r.longtaskMs = longtasks.filter(([s]) => s >= start - 5).reduce((a, [, d]) => a + d, 0);
        rs.push(r);
      }
      const med = (k) => { const v = rs.map((r) => r[k]).filter((x) => x !== undefined).sort((a, b) => a - b); return v.length ? Math.round(v[Math.floor(v.length / 2)]) : undefined; };
      const keys = Object.keys(rs[0]);
      out[`${name} @${label}`] = Object.fromEntries(keys.map((k) => [k, med(k)]));
    }
  }
  obs.disconnect();
  return out;
};

(async () => {
  const device = await pickDevice(android);
  const page = await (await device.webView({ pkg: PKG })).page();
  const r = await page.evaluate(BENCH, rounds);
  if (typeof r === 'string') { console.log(r); } else {
    console.log('median of', rounds, 'rounds, ms (bytes for the JPEG); longtaskMs = main-thread long tasks during the capture');
    for (const [k, v] of Object.entries(r)) console.log(k.padEnd(62), JSON.stringify(v));
  }
  await device.close();
})().catch((e) => { console.error('ERR', e.message.split('\n')[0]); process.exit(1); });
