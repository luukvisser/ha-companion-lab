// measure.js <variants> <rounds> <api|back|swipe>: the fullscreen measurement of measure.py, on
// Playwright's _android API. Card builds come from /builds/<variant>/ through page.route.
const fs = require('fs');
const path = require('path');
const { _android: android } = require('playwright-core');
const { PKG, CARD_PREFIX, TEST_PATH, OTHER_PATH, OVERLAY_CAMERA, pickDevice } = require('/lab/tools/playwright/lab-config');
const { serveVariant } = require('./card-lab');
const [variants, rounds, leave] = [process.argv[2].split(','), +process.argv[3], process.argv[4]];
const INSTALL = fs.readFileSync(path.join(__dirname, 'install.js'), 'utf8').replace('__CAMERA__', OVERLAY_CAMERA);
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
(async () => {
  const device = await pickDevice(android);
  const webview = await device.webView({ pkg: PKG });
  const page = await webview.page();
  let variant = null;
  await serveVariant(page, () => variant);
  const results = {};
  for (const v of variants) {
    variant = v;
    await page.reload();
    await page.waitForFunction(() => !!customElements.get('advanced-camera-card') && !!document.querySelector('home-assistant')?.hass, null, { timeout: 60000 });
    await sleep(3000);
    console.log(v, await page.evaluate(INSTALL));
    const cap = await page.waitForFunction(() => {
      const c = window.__acc.deep(window.__acc.card.shadowRoot, 'advanced-camera-card-live-carousel');
      return c && c.style.maxHeight;
    }, null, { timeout: 30000 });
    console.log(v, 'cap', await cap.jsonValue());
    await sleep(2000);
    const runs = [];
    for (let i = 0; i < rounds; i++) {
      await page.evaluate(() => { window.__acc.frames = []; window.__acc.events = []; });
      await page.click('#acc-measure button');
      await sleep(2500);
      const enter = await page.evaluate(() => JSON.stringify({ events: window.__acc.events, frames: window.__acc.frames }));
      await page.evaluate(() => { window.__acc.t0 = performance.now(); window.__acc.frames = []; window.__acc.events = []; });
      if (leave === 'back') await device.shell('input keyevent 4');
      else if (leave === 'swipe') { for (let k = 0; k < 2; k++) { await device.shell('input touchscreen swipe 1 1200 450 1200 200'); await sleep(1500); } }
      else await page.evaluate(() => document.exitFullscreen());
      await sleep(2500);
      const left = await page.evaluate(() => JSON.stringify({ events: window.__acc.events, frames: window.__acc.frames }));
      runs.push({ enter: JSON.parse(enter), leave: JSON.parse(left), leave_by: leave });
      await sleep(1500);
    }
    results[v] = runs;
    await page.evaluate(() => document.getElementById('acc-measure')?.remove());
  }
  fs.writeFileSync('/out/result-pw.json', JSON.stringify(results));
  console.log('DONE');
  await device.close();
})().catch((e) => { console.error('ERR', e.message.split('\n').slice(0, 6).join(' | ')); process.exit(1); });
