// Settings shared by the Playwright scripts of every layer, from the environment (tools/pwa.sh
// passes lab.env). Scripts load it as require('/lab/tools/playwright/lab-config').
// Core: the device to drive (ANDROID_SERIAL, as for adb; lib.sh defaults it to the running
// emulator). With a phone attached next to the emulator, the first device in the list could be
// the phone: always pick by serial.
async function pickDevice(android) {
  const devices = await android.devices();
  const serial = process.env.ANDROID_SERIAL;
  const device = serial ? devices.find((d) => d.serial() === serial) : devices.length === 1 ? devices[0] : null;
  if (!device) {
    throw new Error(`no device ${serial || '(set ANDROID_SERIAL: more than one, or none)'}; found: ${devices.map((d) => d.serial()).join(', ') || 'none'}`);
  }
  return device;
}

module.exports = {
  pickDevice,
  // Core: the Companion app's package (`.minimal` for the GitHub "minimal" APK).
  PKG: process.env.PKG || 'io.homeassistant.companion.android.minimal',
  // Core: any page to navigate to when a script needs to leave the page under test.
  OTHER_PATH: process.env.OTHER_PATH || '/profile/general',
  // Video layer: the hidden test dashboard (video/ha-setup.sh dashboard).
  TEST_PATH: process.env.TEST_PATH || '/test-dashboard/test',
  // Video layer: a camera for cards placed into the page by hand. Use an image camera: a
  // hand-placed card does not start Home Assistant live video (docs/pitfalls.md).
  OVERLAY_CAMERA: process.env.OVERLAY_CAMERA || 'camera.test_pattern',
  // Card layer: where Home Assistant serves the card's JavaScript (HACS: /hacsfiles/<name>/),
  // intercepted to serve builds from $BUILDS_DIR.
  CARD_PREFIX: process.env.CARD_PREFIX || '/local/community/advanced-camera-card/',
};
