const { _android: android } = require('playwright-core');
const { PKG, CARD_PREFIX, TEST_PATH, OTHER_PATH, OVERLAY_CAMERA, pickDevice } = require('/lab/tools/playwright/lab-config');
(async () => {
  const t = Date.now();
  const device = await pickDevice(android);
  console.log('device', device.serial(), device.model());
  const webview = await device.webView({ pkg: PKG }, { timeout: 15000 });
  console.log('webview pid', webview.pid());
  const page = await webview.page();
  console.log('url', page.url().replace(/^https?:\/\/[^/]+/, ''));
  console.log('eval', await page.evaluate(() => JSON.stringify({ ce: !!customElements.get('advanced-camera-card'), vw: innerWidth, vh: innerHeight, vis: document.visibilityState })));
  await device.screenshot({ path: '/out/pw-smoke.png' });
  console.log('took', Date.now() - t, 'ms');
  await device.close();
})().catch((e) => { console.error('ERR', e.message.split('\n').slice(0, 4).join(' | ')); process.exit(1); });
