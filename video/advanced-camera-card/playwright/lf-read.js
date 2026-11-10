// lf-read.js [variant]: prints the page log of lf-setup.js (window.__lf) plus what the card shows now
// (images, the last-frame time label, videos), as JSON; with a variant also `variant_check`: whether
// every card file the page loaded belongs to that build (card-lab.js verifyVariant).
const { _android: android } = require('playwright-core');
const { PKG, pickDevice } = require('/lab/tools/playwright/lab-config');
const { verifyVariant } = require('./card-lab');
(async () => {
  const device = await pickDevice(android);
  const page = await (await device.webView({ pkg: PKG })).page();
  const check = await verifyVariant(page, process.argv[2]);
  const log = JSON.parse(await page.evaluate(() => {
    const d = window.__lf || {};
    const imgs = []; const labels = []; const videos = [];
    const walk = (r) => { for (const el of r.querySelectorAll('*')) { const t = el.tagName.toLowerCase(); if (t === 'img' && el.src) imgs.push(el.src.startsWith('data:') ? `data:${Math.round(el.src.length * 0.75 / 1024)}kB ${el.naturalWidth}x${el.naturalHeight} visible=${el.offsetParent !== null}` : el.src.replace(/^https?:\/\/[^/]+/, '').slice(0, 60)); if (t.includes('last-frame-time')) labels.push((el.shadowRoot ? el.shadowRoot.textContent : el.textContent).trim()); if (t === 'video') videos.push([+el.currentTime.toFixed(1), el.paused]); if (el.shadowRoot) walk(el.shadowRoot); } };
    walk(document);
    return JSON.stringify({ now: d.t0 !== undefined ? Math.round(performance.now() - d.t0) : null, ctx: d.ctx, dec: d.dec, gaps: d.gaps, show: d.show, samples: d.samples, vis: d.vis, caps: (d.caps || []).map((c) => c.slice(0, 6)), draws: (d.draws || []).map((x) => x.slice(0, 3)), imgs, labels, videos }, null, 1);
  }));
  log.variant_check = check;
  console.log(JSON.stringify(log, null, 1));
  await device.close();
})().catch((e) => { console.error('ERR', e.message.split('\n')[0]); process.exit(1); });
