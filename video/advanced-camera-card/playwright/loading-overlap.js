// loading-overlap.js <variant> [rounds] [wait s]: how long the card's loading indicator
// (`advanced-camera-card-loading`) covers a picture. Loads the test dashboard (TEST_PATH) with card
// build <variant> (from /builds, or `deployed`), then leaves for OTHER_PATH and returns <rounds>
// times (default 3); each phase is logged for <wait> seconds (default 15).
//
// Per animation frame, inside the card only: the indicator's computed opacity (it fades over 1.5 s
// once the card has initialized), whether a loaded <img> is visible (and its kind: data:, blob:,
// http), and whether a video is playing. Per phase it prints when the indicator appeared, when it
// fell under 5% opacity, when the first image and the first playing video showed, and the time the
// indicator (opacity >= 5%) overlapped an image while no video played.
//
// Caution: an <img> counts as shown once loaded, also while it is still blank on screen (not yet
// decoded); bg-video.sh shows what was really on screen. Playwright stays attached, so the page gets
// no visibility events (not needed here).
const { _android: android } = require('playwright-core');
const { PKG, TEST_PATH, OTHER_PATH, pickDevice } = require('/lab/tools/playwright/lab-config');
const { serveVariant, verifyVariant } = require('./card-lab');
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const [variant, rounds, wait] = [process.argv[2], +(process.argv[3] || 3), +(process.argv[4] || 15)];
if (!variant) { console.error('usage: loading-overlap.js <variant> [rounds] [wait s]'); process.exit(2); }

const LOG = () => {
  const acc = (window.__lo = { t0: performance.now(), frames: [], phases: [] });
  let last = '';
  const step = () => {
    const now = performance.now();
    const cards = [];
    const find = (r) => { for (const el of r.querySelectorAll('*')) { if (el.tagName.toLowerCase() === 'advanced-camera-card') cards.push(el); else if (el.shadowRoot) find(el.shadowRoot); } };
    find(document);
    let op = null; let img = ''; let vid = 0;
    const vis = (el) => (el.checkVisibility ? el.checkVisibility({ checkOpacity: true, checkVisibilityCSS: true }) : true) && el.getBoundingClientRect().height > 20;
    const walk = (r) => {
      for (const el of r.querySelectorAll('*')) {
        const t = el.tagName.toLowerCase();
        if (t === 'advanced-camera-card-loading') { const o = +getComputedStyle(el).opacity; op = Math.max(op ?? 0, o); }
        else if (t === 'img' && el.complete && el.naturalWidth > 0 && vis(el)) img = img || (el.src.startsWith('data:') ? 'data' : el.src.startsWith('blob:') ? 'blob' : 'http');
        else if (t === 'video' && vis(el) && !el.paused && el.readyState >= 2 && el.videoWidth > 0) vid++;
        if (el.shadowRoot) walk(el.shadowRoot);
      }
    };
    for (const c of cards) if (c.shadowRoot) walk(c.shadowRoot);
    const key = `${op === null ? '-' : op.toFixed(2)}|${img}|${vid}`;
    if (key !== last) { acc.frames.push([Math.round(now - acc.t0), op, img, vid]); last = key; }
    requestAnimationFrame(step);
  };
  requestAnimationFrame(step);
};

// Summarise the frames of one phase [from, to) (ms since t0).
const summarise = (frames, from, to) => {
  const f = frames.filter((x) => x[0] < to);
  // The state at `from` is the last change before it.
  const before = f.filter((x) => x[0] <= from).pop();
  const seg = (before ? [[from, ...before.slice(1)]] : []).concat(f.filter((x) => x[0] > from));
  const out = { appeared: null, under5: null, firstImg: null, imgKind: null, firstVideo: null, overlapImg: 0, overlapNothing: 0 };
  for (let i = 0; i < seg.length; i++) {
    const [t, op, img, vid] = seg[i];
    const end = i + 1 < seg.length ? seg[i + 1][0] : to;
    const rel = t - from;
    if (op !== null && op >= 0.05 && out.appeared === null) out.appeared = rel;
    if (out.appeared !== null && out.under5 === null && (op === null || op < 0.05)) out.under5 = rel;
    if (img && out.firstImg === null) { out.firstImg = rel; out.imgKind = img; }
    if (vid && out.firstVideo === null) out.firstVideo = rel;
    if (op !== null && op >= 0.05 && !vid) { if (img) out.overlapImg += end - t; else out.overlapNothing += end - t; }
  }
  return out;
};

(async () => {
  const device = await pickDevice(android);
  const page = await (await device.webView({ pkg: PKG })).page();
  await serveVariant(page, variant);
  await page.addInitScript(LOG);
  const origin = new URL(page.url()).origin;
  await page.goto(origin + TEST_PATH + '?external_auth=1');
  const nav = (p) => page.evaluate((x) => { history.pushState(null, '', x); window.dispatchEvent(new CustomEvent('location-changed', { detail: { replace: false } })); }, p);
  const mark = (name) => page.evaluate((n) => { window.__lo.phases.push([n, Math.round(performance.now() - window.__lo.t0)]); }, name);
  // The first load started at t0 (the log starts with the document).
  await page.evaluate(() => window.__lo.phases.push(['first load', 0]));
  await sleep(wait * 1000);
  for (let i = 1; i <= rounds; i++) {
    await mark('away');
    await nav(OTHER_PATH);
    await sleep(4000);
    await mark(`return ${i}`);
    await nav(TEST_PATH);
    await sleep(wait * 1000);
  }
  await mark('end');
  const { frames, phases } = await page.evaluate(() => window.__lo);
  const check = await verifyVariant(page, variant);
  console.log('variant', JSON.stringify(check));
  console.log('ms from the phase start | indicator appeared | under 5% | first image (kind) | first video | indicator over an image, no video | indicator over no image, no video');
  for (let i = 0; i < phases.length - 1; i++) {
    const [name, from] = phases[i];
    if (name === 'away') continue;
    const s = summarise(frames, from, phases[i + 1][1]);
    console.log(`${name} | ${s.appeared ?? '-'} | ${s.under5 ?? '-'} | ${s.firstImg ?? '-'} (${s.imgKind ?? '-'}) | ${s.firstVideo ?? '-'} | ${s.overlapImg} | ${s.overlapNothing}`);
  }
  if (process.env.FRAMES) console.log(JSON.stringify(frames));
  await page.unrouteAll({ behavior: 'ignoreErrors' });
  await device.close();
  if (check.ok === false) { console.error('variant check failed: the page loaded card files from elsewhere'); process.exit(1); }
})().catch((e) => { console.error('ERR', e.message.split('\n').slice(0, 3).join(' | ')); process.exit(1); });
