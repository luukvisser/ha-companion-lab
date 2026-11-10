// lf-reload.js <variant>: reloads the test dashboard with build <variant> and samples what the card shows first.
const fs = require('fs'); const path = require('path');
const { _android: android } = require('playwright-core');
const { PKG, CARD_PREFIX, TEST_PATH, OTHER_PATH, OVERLAY_CAMERA, pickDevice } = require('/lab/tools/playwright/lab-config');
const { serveVariant } = require('./card-lab');
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
(async () => {
  const device = await pickDevice(android);
  const page = await (await device.webView({ pkg: PKG })).page();
  await serveVariant(page, process.argv[2]);
  await page.reload();
  const t0 = Date.now();
  for (let i = 0; i < 16; i++) {
    const s = await page.evaluate(() => { const imgs = []; const labels = []; const videos = []; const walk = (r) => { for (const el of r.querySelectorAll('*')) { const t = el.tagName.toLowerCase(); if (t === 'img' && el.src && el.offsetParent !== null) imgs.push(el.src.startsWith('data:') ? `frame ${el.naturalWidth}x${el.naturalHeight}` : el.src.replace(/^https?:\/\/[^/]+/, '').slice(0, 40)); if (t.includes('last-frame-time')) labels.push((el.shadowRoot ? el.shadowRoot.textContent : el.textContent).trim()); if (t === 'video') videos.push(+el.currentTime.toFixed(1)); if (el.shadowRoot) walk(el.shadowRoot); } }; walk(document); return { imgs, labels, videos }; }).catch(() => 'loading');
    console.log(`${Date.now() - t0} ms`, JSON.stringify(s));
    if (s.videos && s.videos.some((v) => v > 1)) break;
    await sleep(500);
  }
  await device.close();
})().catch((e) => { console.error('ERR', e.message.split('\n')[0]); process.exit(1); });
