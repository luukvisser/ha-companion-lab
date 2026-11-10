// dashlive.js [path]: opens a dashboard path in the app and reports the card's <video> state.
const { _android: android } = require('playwright-core');
const { PKG, CARD_PREFIX, TEST_PATH, OTHER_PATH, OVERLAY_CAMERA, pickDevice } = require('/lab/tools/playwright/lab-config');
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
(async () => {
  const device = await pickDevice(android);
  const page = await (await device.webView({ pkg: PKG })).page();
  const msgs = [];
  page.on('pageerror', (e) => msgs.push('pageerror ' + e.message));
  await page.evaluate(() => { clearInterval(window.__accHass); document.getElementById('acc-live')?.remove(); });
  const path = process.argv[2] || TEST_PATH;
  await page.evaluate((p) => { history.pushState(null, '', p); window.dispatchEvent(new CustomEvent('location-changed', { detail: { replace: false } })); }, path);
  for (let i = 0; i < 10; i++) {
    await sleep(2500);
    // Per <video>: [player, time, width, height, paused, muted, visible]. The player is "webrtc"
    // for a video fed by a MediaStream, else "media" (HLS/MSE): a playing video alone does not
    // say WebRTC works, the card keeps an HLS player beside it (10-11-2026).
    const s = await page.evaluate(() => { const out = []; const walk = (r) => { out.push(...r.querySelectorAll('video')); for (const el of r.querySelectorAll('*')) if (el.shadowRoot) walk(el.shadowRoot); }; walk(document); return out.map((v) => [v.srcObject ? 'webrtc' : 'media', +v.currentTime.toFixed(1), v.videoWidth, v.videoHeight, v.paused, v.muted, v.getBoundingClientRect().width > 0]); });
    console.log(`${(i + 1) * 2.5}s ${JSON.stringify(s)}`);
    if (s.some((x) => x[1] > 3)) break;
  }
  console.log(msgs.join('\n') || 'no page errors');
  await device.screenshot({ path: '/out/dash.png' });
  await device.close();
})().catch((e) => { console.error('ERR', e.message.split('\n')[0]); process.exit(1); });
