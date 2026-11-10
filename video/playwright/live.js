// live.js <camera_entity>: overlays a card on that camera in the app and reports whether live video plays.
const { _android: android } = require('playwright-core');
const { PKG, CARD_PREFIX, TEST_PATH, OTHER_PATH, OVERLAY_CAMERA, pickDevice } = require('/lab/tools/playwright/lab-config');
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
(async () => {
  const device = await pickDevice(android);
  const page = await (await device.webView({ pkg: PKG })).page();
  const entity = process.argv[2];
  if (process.argv[3] === 'reload') { await page.reload(); await page.waitForFunction(() => !!customElements.get('advanced-camera-card') && !!document.querySelector('home-assistant')?.hass?.states, null, { timeout: 60000 }); await sleep(3000); }
  await page.evaluate((entity) => {
    clearInterval(window.__accHass);
    document.getElementById('acc-live')?.remove();
    const wrap = document.createElement('div');
    wrap.id = 'acc-live';
    wrap.style.cssText = 'position:fixed;top:0;left:0;right:0;z-index:99999;background:#fff;';
    const card = document.createElement('advanced-camera-card');
    card.setConfig({ type: 'custom:advanced-camera-card', cameras: [{ camera_entity: entity, live_provider: 'ha' }] });
    card.hass = document.querySelector('home-assistant').hass;
    window.__accHass = setInterval(() => { card.hass = document.querySelector('home-assistant').hass; }, 1000);
    wrap.append(card);
    document.body.append(wrap);
  }, entity);
  const deepAll = `(root, sel) => { const out = []; const walk = (r) => { out.push(...r.querySelectorAll(sel)); for (const el of r.querySelectorAll('*')) if (el.shadowRoot) walk(el.shadowRoot); }; walk(root); return out; }`;
  for (let i = 0; i < 12; i++) {
    await sleep(2500);
    const s = await page.evaluate((deepAll) => {
      const all = eval(deepAll);
      const v = all(document.getElementById('acc-live'), 'video');
      return v.map((x) => ({ t: +x.currentTime.toFixed(1), w: x.videoWidth, h: x.videoHeight, paused: x.paused, muted: x.muted, rs: x.readyState, src: x.srcObject ? 'stream' : (x.currentSrc ? 'url' : '-') }));
    }, deepAll);
    console.log(`${(i + 1) * 2.5}s`, JSON.stringify(s));
    if (s.some((x) => x.t > 3)) break;
  }
  await device.screenshot({ path: '/out/live.png' });
  await device.close();
})().catch((e) => { console.error('ERR', e.message.split('\n').slice(0, 4).join(' | ')); process.exit(1); });
