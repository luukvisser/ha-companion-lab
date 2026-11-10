// desktop.js <seconds of call, 0 for none>: the desktop-browser route. Headless Chromium (the
// Playwright image's) logs in to the lab's Home Assistant as the limited test user, opens the test
// dashboard, reports which player plays (WebRTC or HLS) and its decoded frames, and optionally makes
// a call from the card with a fake microphone that plays /tone.wav (the lab tone: 1 kHz, 2 s on,
// 1 s off). What reached the camera: stack/stack.sh talk. Run it through
// video/desktop/desktop.sh, which mounts the password file (read here, never printed) and the tone.
const { chromium } = require('playwright-core');
const fs = require('fs');
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const HA = process.env.DESKTOP_HA_URL || 'http://127.0.0.1:8124';
const TEST_PATH = process.env.TEST_PATH || '/test-dashboard/test';
const USER = process.env.TEST_USER || 'companion-lab';
const callSeconds = +(process.argv[2] || 0);

const VIDEO = `(() => { const out = []; const w = (r) => { for (const el of r.querySelectorAll('*')) { if (el.tagName === 'VIDEO') out.push(el); if (el.shadowRoot) w(el.shadowRoot); } }; w(document);
  return out.filter((v) => v.getBoundingClientRect().height > 20).map((v) => ({ player: v.srcObject ? 'webrtc' : 'media', t: +v.currentTime.toFixed(1), w: v.videoWidth, paused: v.paused,
    decoded: v.getVideoPlaybackQuality ? v.getVideoPlaybackQuality().totalVideoFrames : null })); })()`;
const CARD = `((t) => { const w = (r) => { for (const el of r.querySelectorAll('*')) { if (el.tagName.toLowerCase() === t) return el; if (el.shadowRoot) { const f = w(el.shadowRoot); if (f) return f; } } return null; }; return w(document); })('advanced-camera-card')`;
const act = (a) => `${CARD}._controller.getActionsManager().executeActions({ actions: { action: 'fire-dom-event', advanced_camera_card_action: '${a}' } })`;

(async () => {
  const password = fs.readFileSync('/secret/password', 'utf8').trim();
  const browser = await chromium.launch({
    args: ['--use-fake-ui-for-media-stream', '--use-fake-device-for-media-stream', '--use-file-for-fake-audio-capture=/tone.wav',
      '--autoplay-policy=no-user-gesture-required'],
  });
  const page = await (await browser.newContext({ viewport: { width: 412, height: 892 }, permissions: ['microphone'] })).newPage();
  const errors = [];
  page.on('console', (m) => { if (['error', 'warning'].includes(m.type())) errors.push(m.text().slice(0, 200)); });
  // The same watch as the emulator's call.py: getUserMedia and the peer connections' audio senders.
  await page.addInitScript(() => {
    const c = (window.__call = { gum: [], pcs: [] });
    const md = navigator.mediaDevices;
    if (md) {
      const orig = md.getUserMedia.bind(md);
      md.getUserMedia = (cons) => { const rec = { audio: !!(cons && cons.audio), result: 'pending' }; c.gum.push(rec);
        return orig(cons).then((st) => { rec.result = 'ok'; return st; }, (e) => { rec.result = 'error ' + e.name; throw e; }); };
    }
    const Orig = window.RTCPeerConnection;
    window.RTCPeerConnection = function (...a) { const pc = new Orig(...a); c.pcs.push(pc); return pc; };
    window.RTCPeerConnection.prototype = Orig.prototype;
  });
  await page.goto(HA + TEST_PATH);
  // Home Assistant's login page: user name and password, then submit.
  await page.getByLabel(/username/i).fill(USER);
  await page.locator('input[type="password"]').first().fill(password);
  await page.keyboard.press('Enter');
  await page.waitForURL((u) => u.pathname === TEST_PATH, { timeout: 30000 });
  console.log('browser', browser.version(), 'logged in, page', new URL(page.url()).pathname);
  for (let i = 0; i < 12; i++) {
    await sleep(2500);
    const v = await page.evaluate(VIDEO);
    console.log(`${(i + 1) * 2.5}s`, JSON.stringify(v));
    if (v.some((x) => x.t > 4)) break;
  }
  if (callSeconds > 0) {
    // As a user gesture (CDP userGesture), as in the emulator's call.py: page.evaluate is not one,
    // and without it call_start did nothing here (10-11-2026).
    const cdp = await page.context().newCDPSession(page);
    const gesture = (js) => cdp.send('Runtime.evaluate', { expression: js, userGesture: true, awaitPromise: false });
    await gesture(act('call_start'));
    await sleep(1500);
    await gesture(act('microphone_unmute'));
    await sleep(callSeconds * 1000);
    console.log('during the call', await page.evaluate(() => JSON.stringify({ gum: window.__call.gum,
      pcs: window.__call.pcs.map((pc) => ({ state: pc.connectionState, audio: pc.getSenders().filter((x) => x.track && x.track.kind === 'audio').map((x) => x.track.readyState + (x.track.enabled ? '' : ' disabled')) })) })));
    await gesture(act('call_end'));
    await sleep(2000);
    console.log('call held for', callSeconds, 's');
  }
  if (errors.length) console.log('page errors/warnings:', JSON.stringify([...new Set(errors)].slice(0, 8)));
  await browser.close();
})().catch((e) => { console.error('ERR', e.message.split('\n')[0]); process.exit(1); });
