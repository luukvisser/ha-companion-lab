// devices.js: a check that needs no Home Assistant login (CI, first setup): Playwright sees the
// emulator through the adb server, the Companion app is installed and running.
const { _android: android } = require('playwright-core');
const { PKG, pickDevice } = require('/lab/tools/playwright/lab-config');
(async () => {
  const device = await pickDevice(android);
  console.log('device', device.serial(), device.model());
  const installed = (await device.shell(`pm path ${PKG}`)).toString();
  if (!installed.includes('package:')) throw new Error(`${PKG} is not installed`);
  const pid = (await device.shell(`pidof ${PKG}`)).toString().trim();
  console.log('app', PKG, pid ? `running (pid ${pid})` : 'installed, not running');
  await device.screenshot({ path: '/out/devices.png' });
  await device.close();
  if (!pid) process.exit(1);
})().catch((e) => { console.error('ERR', e.message.split('\n')[0]); process.exit(1); });
