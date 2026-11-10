// lf-capture.js <variant> <seconds>: loads the test dashboard (TEST_PATH) with card build <variant> from
// /builds, watches the live stream for <seconds> and reports every frame capture (canvas size,
// sync drawImage time, encode time, JPEG bytes) plus long main-thread tasks.
const fs = require('fs');
const path = require('path');
const { _android: android } = require('playwright-core');
const { PKG, CARD_PREFIX, TEST_PATH, OTHER_PATH, OVERLAY_CAMERA, pickDevice } = require('/lab/tools/playwright/lab-config');
const { serveVariant, INSTRUMENT } = require('./card-lab');
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const [variant, seconds] = [process.argv[2], +(process.argv[3] || 60)];


(async () => {
  const device = await pickDevice(android);
  const page = await (await device.webView({ pkg: PKG })).page();
  await serveVariant(page, variant);
  await page.addInitScript(INSTRUMENT);
  const origin = new URL(page.url()).origin;
  await page.goto(origin + TEST_PATH + '?external_auth=1');
  // Wait until the live video plays.
  const t0 = Date.now();
  let playing = false;
  while (Date.now() - t0 < 60000 && !playing) {
    await sleep(1000);
    playing = await page.evaluate(() => { const out = []; const walk = (r) => { out.push(...r.querySelectorAll('video')); for (const el of r.querySelectorAll('*')) if (el.shadowRoot) walk(el.shadowRoot); }; walk(document); return out.some((v) => v.currentTime > 1 && !v.paused); });
  }
  console.log(variant, 'playing after', Math.round((Date.now() - t0) / 1000), 's:', playing);
  await page.evaluate(() => { window.__lf.t0 = performance.now(); window.__lf.caps = []; window.__lf.draws = []; window.__lf.longtasks = []; });
  await sleep(seconds * 1000);
  const r = await page.evaluate(() => JSON.stringify(window.__lf));
  fs.writeFileSync(`/out/lf-${variant}.json`, r);
  const d = JSON.parse(r);
  console.log(`${variant}: ${d.caps.length} captures in ${seconds} s`);
  d.caps.forEach((c) => console.log('  ', c.join(' ')));
  console.log('  drawImage(video):', d.draws.map((x) => `${x[1]}x${x[2]} ${x[3]}ms`).join(', ') || '-');
  console.log('  long tasks:', d.longtasks.map((x) => x.join('@')).join(', ') || 'none');
  await device.close();
})().catch((e) => { console.error('ERR', e.message.split('\n').slice(0, 3).join(' | ')); process.exit(1); });
