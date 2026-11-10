// zoom-after-reset.js [waits ms, comma-separated] [rounds]: can the live view still be zoomed after a
// double tap returned it to the default zoom (PR #2866)? Per round: pinch until zoomed, a double tap
// (120 ms gap), then for each wait a pinch after that wait, with the zoomer's scale after each.
const { _android: android } = require('playwright-core');
const { PKG, pickDevice } = require('/lab/tools/playwright/lab-config');
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const waits = (process.argv[2] || '2000,5000,10000').split(',').map(Number);
const rounds = +(process.argv[3] || 2);
const FIND = (tag) => `(() => { const out = []; const walk = (r) => { for (const el of r.querySelectorAll('*')) { if (el.tagName.toLowerCase() === '${tag}') out.push(el); if (el.shadowRoot) walk(el.shadowRoot); } }; walk(document); return out; })()`;

(async () => {
  const device = await pickDevice(android);
  const page = await (await device.webView({ pkg: PKG })).page();
  const cdp = await page.context().newCDPSession(page);
  const centre = await page.evaluate(`(() => { const r = ${FIND('advanced-camera-card-live-provider')}[0].getBoundingClientRect(); return { x: r.left + r.width / 2, y: r.top + r.height / 2 }; })()`);
  const scale = () => page.evaluate(`(() => { const z = ${FIND('advanced-camera-card-zoomer')}.find((e) => e.getBoundingClientRect().height > 20); if (!z) return null; const t = getComputedStyle(z).transform; return t === 'none' ? 1 : +t.replace(/matrix\\(([^,]+),.*/, '$1'); })()`);
  const pinch = async () => {
    const pts = (d) => [{ x: centre.x - d, y: centre.y, id: 0 }, { x: centre.x + d, y: centre.y, id: 1 }];
    await cdp.send('Input.dispatchTouchEvent', { type: 'touchStart', touchPoints: pts(30) });
    for (let d = 30; d <= 120; d += 6) { await cdp.send('Input.dispatchTouchEvent', { type: 'touchMove', touchPoints: pts(d) }); await sleep(16); }
    await cdp.send('Input.dispatchTouchEvent', { type: 'touchEnd', touchPoints: [] });
  };
  const tap = async () => {
    await cdp.send('Input.dispatchTouchEvent', { type: 'touchStart', touchPoints: [{ x: centre.x, y: centre.y, id: 0 }] });
    await sleep(50);
    await cdp.send('Input.dispatchTouchEvent', { type: 'touchEnd', touchPoints: [] });
  };
  for (let r = 1; r <= rounds; r++) {
    let z = 1;
    for (let t = 0; t < 6 && !(z > 1.05); t++) { await pinch(); await sleep(1500); z = await scale(); }
    await tap(); await sleep(70); await tap(); await sleep(1500);
    const afterReset = await scale();
    const row = [`round ${r}: zoomed ${z.toFixed(2)}, after the double tap ${afterReset?.toFixed(2)}`];
    for (const w of waits) {
      await sleep(w);
      const before = await scale();
      await pinch(); await sleep(1500);
      const after = await scale();
      row.push(`pinch after ${w} ms: ${before?.toFixed(2)} -> ${after?.toFixed(2)}`);
      if (after > 1.05) { await tap(); await sleep(70); await tap(); await sleep(1500); }
    }
    console.log(row.join(' | '));
  }
  await device.close();
})().catch((e) => { console.error('ERR', e.message.split('\n')[0]); process.exit(1); });
