// doubletap.js [gaps ms, comma-separated] [rounds]: does a double tap on the live view return a
// zoomed-in camera to its default zoom (PR #2866, double-tap-zoom-reset)? Per gap and round: a real
// two-finger pinch-out (CDP touch input), then two taps at the centre with the given gap between
// them (each tap 50 ms down), then the zoomer's scale. A single tap is the control (gap "single").
// The PR counts two taps as a double tap within 300 ms (DOUBLE_TAP_MAX_MS), so gaps above that
// should leave the zoom. Visibility events are not involved, so Playwright is fine here.
const { _android: android } = require('playwright-core');
const { PKG, pickDevice } = require('/lab/tools/playwright/lab-config');
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const gaps = (process.argv[2] || 'single,100,200,280,400').split(',');
const rounds = +(process.argv[3] || 3);

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
  console.log('gap | round | scale after pinch | scale 1.5 s after the taps | reset');
  for (const gap of gaps) {
    for (let r = 1; r <= rounds; r++) {
      // The first pinch after a page load sometimes leaves the zoom at 1 (10-11-2026): retry.
      let zoomed = 1;
      for (let t = 0; t < 3 && !(zoomed > 1.05); t++) { await pinch(); await sleep(1500); zoomed = await scale(); }
      // Measured on the page clock: the gap between the two touchStarts as the page saw them.
      await page.evaluate(() => { window.__dt = []; window.__dtf = (e) => window.__dt.push(e.timeStamp); document.addEventListener('pointerdown', window.__dtf, true); });
      await tap();
      if (gap !== 'single') { await sleep(Math.max(0, +gap - 50)); await tap(); }
      await sleep(1500);
      const after = await scale();
      const seen = await page.evaluate(() => { document.removeEventListener('pointerdown', window.__dtf, true); const t = window.__dt; return t.length > 1 ? Math.round(t[1] - t[0]) : null; });
      const reset = zoomed > 1.05 && after !== null && after < 1.05;
      console.log(`${gap}${seen !== null ? ` (page ${seen} ms)` : ''} | ${r} | ${zoomed?.toFixed(2)} | ${after?.toFixed(2)} | ${zoomed > 1.05 ? (reset ? 'yes' : 'no') : 'not zoomed'}`);
      // Back to the default zoom for the next round, whatever happened.
      if (after > 1.05) { await tap(); await sleep(120); await tap(); await sleep(1500); }
    }
  }
  await device.close();
})().catch((e) => { console.error('ERR', e.message.split('\n')[0]); process.exit(1); });
