// lf-nav.js: on the test dashboard (already loaded by lf-setup.js), go to another dashboard and back,
// and sample what the card shows as image and video during the first seconds back.
const { _android: android } = require('playwright-core');
const { PKG, CARD_PREFIX, TEST_PATH, OTHER_PATH, OVERLAY_CAMERA, pickDevice } = require('/lab/tools/playwright/lab-config');
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const go = (p) => { history.pushState(null, '', p); window.dispatchEvent(new CustomEvent('location-changed', { detail: { replace: false } })); };
const SAMPLE = () => {
  const imgs = []; const labels = []; const videos = [];
  const walk = (r) => { for (const el of r.querySelectorAll('*')) { const t = el.tagName.toLowerCase(); if (t === 'img' && el.src && el.offsetParent !== null) imgs.push(el.src.startsWith('data:') ? `frame ${el.naturalWidth}x${el.naturalHeight}` : el.src.replace(/^https?:\/\/[^/]+/, '').slice(0, 40)); if (t.includes('last-frame-time')) labels.push((el.shadowRoot ? el.shadowRoot.textContent : el.textContent).trim()); if (t === 'video') videos.push(+el.currentTime.toFixed(1)); if (t === 'canvas' && el.classList.contains('drawn-frame') && el.offsetParent !== null) imgs.push(`canvas ${el.width}x${el.height}`); if (el.shadowRoot) walk(el.shadowRoot); } };
  walk(document);
  return { imgs, labels, videos };
};
(async () => {
  const device = await pickDevice(android);
  const page = await (await device.webView({ pkg: PKG })).page();
  const before = await page.evaluate(() => (window.__lf.caps || []).length);
  await page.evaluate(go, OTHER_PATH);
  await sleep(3000);
  const after = await page.evaluate(() => (window.__lf.caps || []).length);
  console.log('captures before leaving', before, '| after leaving', after);
  await page.evaluate(go, TEST_PATH);
  const t0 = Date.now();
  for (let i = 0; i < 12; i++) {
    const s = await page.evaluate(SAMPLE);
    console.log(`${Date.now() - t0} ms`, JSON.stringify(s));
    if (process.argv[2] === 'series' && i < 8) { const ts = Date.now() - t0; await device.screenshot({ path: `/out/series-${i}.png` }); console.log(`  screenshot ${i} at ${ts}-${Date.now() - t0} ms`); }
    else if (s.imgs.some((x) => x.startsWith('frame')) && !globalThis.__shot) { globalThis.__shot = 1; await device.screenshot({ path: '/out/lf-back.png' }); console.log('screenshot taken'); }
    if (process.argv[2] !== 'series') await sleep(500);
  }
  await device.close();
})().catch((e) => { console.error('ERR', e.message.split('\n')[0]); process.exit(1); });
