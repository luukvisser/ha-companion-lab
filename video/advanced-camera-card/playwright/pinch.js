// pinch.js: a real two-finger pinch-out (CDP touch input) on the live view; prints the zoomer transform.
// pinch.js: a two-finger pinch-out on the card's live view (real touch input via CDP), then reports
// the zoomer's transform and what remember_zoom stored.
const { _android: android } = require('playwright-core');
const { PKG, pickDevice } = require('/lab/tools/playwright/lab-config');
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
(async () => {
  const device = await pickDevice(android);
  const page = await (await device.webView({ pkg: PKG })).page();
  const box = await page.evaluate(() => {
    const zs = []; const walk = (r) => { for (const el of r.querySelectorAll('*')) { if (el.tagName.toLowerCase() === 'advanced-camera-card-live-provider') zs.push(el); if (el.shadowRoot) walk(el.shadowRoot); } };
    walk(document); const r = zs[0].getBoundingClientRect(); return { x: r.left + r.width / 2, y: r.top + r.height / 2 };
  });
  const cdp = await page.context().newCDPSession(page);
  const pts = (d) => [{ x: box.x - d, y: box.y, id: 0 }, { x: box.x + d, y: box.y, id: 1 }];
  await cdp.send('Input.dispatchTouchEvent', { type: 'touchStart', touchPoints: pts(30) });
  for (let d = 30; d <= 120; d += 6) { await cdp.send('Input.dispatchTouchEvent', { type: 'touchMove', touchPoints: pts(d) }); await sleep(16); }
  await cdp.send('Input.dispatchTouchEvent', { type: 'touchEnd', touchPoints: [] });
  await sleep(1500);
  console.log(await page.evaluate(() => {
    const zs = []; const walk = (r) => { for (const el of r.querySelectorAll('*')) { if (el.tagName.toLowerCase() === 'advanced-camera-card-zoomer') zs.push(el); if (el.shadowRoot) walk(el.shadowRoot); } };
    walk(document);
    const keys = Object.keys(localStorage).filter((k) => /zoom/i.test(k));
    return JSON.stringify({ transforms: zs.map((z) => getComputedStyle(z).transform), stored: keys.map((k) => [k, localStorage.getItem(k).slice(0, 120)]) });
  }));
  await device.close();
})().catch((e) => { console.error('ERR', e.message.split('\n')[0]); process.exit(1); });
