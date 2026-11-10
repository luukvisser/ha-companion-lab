# Pitfalls (core; each one cost time)

- **Host GPU mode froze the WebView.** With `-gpu host` the page stayed `about:blank`, timers
  never fired, logcat showed `MESA: Failed to open rendernode`. `-gpu swiftshader_indirect` works
  but is software rendering: slow, and the launcher reports "isn't responding" for about 30 s after
  boot.
- **Android 17's local-network permission.** The first "allow … nearby devices" dialog is
  `ACCESS_LOCAL_NETWORK`. Denied, the app times out on any LAN or `10.0.2.2` address without
  opening a connection at all (`ss -tnp | grep qemu` shows none). `get-companion-apk.sh` grants it.
- **`uiautomator dump` exposes the text of password fields.** A login password was printed this
  way once. Do not dump the UI while a password field is filled; use screenshots there.
- **`adb shell` reads stdin.** Inside a `while read` loop it eats the loop's input (it made the
  back key look broken). Always `</dev/null`.
- **Leaving element fullscreen in the app:** the back key works; an edge swipe needs **two swipes**
  (immersive mode: the first only shows the system bars). One swipe too many sends the app to the
  background, after which the page stops rendering and the app may restart (new pid: forward the
  DevTools socket again, `forward_devtools` in `lib.sh`).
- **Playwright hides page visibility.** While Playwright is attached, sending the app to the
  background and back fires **no** `visibilitychange` (it enables focus emulation; disabling that
  through a raw CDP session did not help). A run under Playwright would report "never hidden". Use
  plain CDP, or install a page-side recorder and detach before the action.
- **A page-side log is not the screen.** The page's own log counts an `<img>` as present (loaded,
  visible) while it is still blank on screen because the browser has not decoded it yet; it
  reported "image shown" where a screen recording showed a white card. Only a screenshot or a
  screen recording shows what the user saw.
- **The app's WebView stops running page code a few seconds into the background.** With the app
  sent away (Home), a `setTimeout(0)` did not fire for over 90 s, and a Lit element created just
  before stayed unrendered (`hasUpdated: false`). Whatever must be on screen at the return has to be
  in place before, or right at, `visibilitychange` to hidden; nothing renders "in the background".
  Inspect a hidden page only with the plain CDP tools, and never wait on timers there.
- **Switching dashboards builds a card anew.** Back on a dashboard after another one, Home
  Assistant created the card again: anything a card keeps only in its element (for example a
  canvas) is gone, and only shared state (a module-level store, IndexedDB) carries over.
- **The emulator inflates timings.** It used about 3.4 of 4 cores with video playing (load average
  7-9), and its "GPU" runs on the CPU. Compare variants with each other on the emulator; do not
  quote its absolute times as phone times. Stop it when not testing.

Pitfalls specific to video and to the card are in their layers' READMEs.

- **More than one device on adb.** With a phone attached next to the emulator, a bare `adb shell`
  fails ("more than one device") and `android.devices()[0]` may be the phone. Every script drives
  `ANDROID_SERIAL` (adb's own variable): `setup/start-emulator.sh` starts the emulator on a fixed
  port (`EMULATOR_PORT`, default 5554, serial `emulator-5554`), `lib.sh` defaults the serial to the
  running emulator, and the Playwright scripts pick the device by that serial.
- **Downloads are checked.** `setup/install-sdk.sh` checks each zip's SHA-1 against Google's
  repository XML and skips a package already installed in that version (a new version replaces the
  package folder as a whole); `setup/get-companion-apk.sh` checks the APK's SHA-256 against the
  digest GitHub lists for the release asset, also for a cached file, and refuses a mismatch.
- **Home in fullscreen opens picture-in-picture** (emulator, 10-11-2026). With the card in
  fullscreen, Home floats the video in a small window (the app's window `pinned`, the activity only
  PAUSED and still visible): the page is not hidden and keeps playing, by design. With
  picture-in-picture off for the app (`lab pip off`, Android's Settings -> Apps -> Home Assistant ->
  Picture-in-picture), Home hides the page as on a real Pixel (10-11-2026: the last frame's time
  label on return). The lab keeps Android's default (on); `APP_PIP=off lab card ...` measures the
  other case. Screen off (`lab key off`) hides the page either way.
