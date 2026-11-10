const { _android: android } = require('playwright-core');
const { PKG, CARD_PREFIX, TEST_PATH, OTHER_PATH, OVERLAY_CAMERA, pickDevice } = require('/lab/tools/playwright/lab-config');
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
(async () => {
  const device = await pickDevice(android);
  const page = await (await device.webView({ pkg: PKG })).page();
  const cdp = await page.context().newCDPSession(page);
  await cdp.send('Emulation.setFocusEmulationEnabled', { enabled: false });
  await page.evaluate(() => { window.__vis = []; document.addEventListener('visibilitychange', () => window.__vis.push(document.visibilityState)); });
  await device.shell('input keyevent 3'); await sleep(3000);
  await device.shell(`monkey -p ${PKG} -c android.intent.category.LAUNCHER 1`); await sleep(4000);
  console.log('playwright attached:', await page.evaluate(() => JSON.stringify(window.__vis)));
  await device.close();
})().catch((e) => { console.error('ERR', e.message.split('\n')[0]); process.exit(1); });
