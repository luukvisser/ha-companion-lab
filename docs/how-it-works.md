# How it works

```
 this machine                                        emulator (Android 17, swiftshader GPU)
 ─────────────                                       ───────────────────────────────────────
 adb server :5037 ───────────── adb ───────────────► Companion app (WebView)
   │  forward tcp:9333 → webview_devtools_remote_<pid>   └─ Home Assistant frontend
 tools/cdp.sh, tools/cdp/*.py  (plain CDP)                  ▲
 tools/pwa.sh + */playwright/*.js (Playwright _android)     │
 lab's Home Assistant ◄── http://localhost:8124 (adb reverse) ───┘
```

- **Playwright `_android`** (`tools/pwa.sh <path to script>`): `android.devices()` →
  `device.webView({ pkg })` → a normal Playwright `page` in under a second (no port forwarding),
  with `page.route` for intercepting requests and `page.click` as a real gesture (needed e.g. for
  fullscreen). `device.input.press` needs Playwright's driver APK; use
  `device.shell('input keyevent 4')` instead. Scripts of every layer load their settings with
  `require('/lab/tools/playwright/lab-config')`.
- **Plain CDP** (`tools/cdp.sh`, `tools/cdp/cdp.py`): for anything that depends on
  `visibilitychange` ([pitfalls.md](pitfalls.md)).
- **Page-side logs**: install a small recorder in the page, detach, act (background the app, switch
  pages), and read it back afterwards; nothing needs to stay attached.
- **Screen truth**: `tools/emu.sh shot` and `adb shell screenrecord` show what was really on
  screen, which a page-side log cannot ([pitfalls.md](pitfalls.md)).

| Core script | What it does |
|---|---|
| `lab doctor\|up\|status\|down\|shot\|reset-state\|build\|card\|prof\|avent` | the front door: wraps the scripts below and the layers' (`up --gpu`: GPU rendering on Linux, [gpu.md](gpu.md)) |
| `lab key home\|back\|switcher\|off\|on\|front` | a way out of the app or back; in fullscreen only `switcher` and `off` hide the page (docs/pitfalls.md) |
| `video/desktop/desktop.sh [call s]` | the desktop-browser route: headless Chromium logs in to the isolated stack as the test user, plays the test card, optionally calls with a fake microphone |
| `setup/install-sdk.sh` | emulator, platform-tools, system image for `$API_LEVEL`, SHA-1 verified |
| `setup/create-avd.sh` | writes the AVD; checks KVM |
| `setup/get-companion-apk.sh [version]` | downloads and installs the minimal APK; grants the local-network permission |
| `setup/start-emulator.sh [--no-window]` / `stop-emulator.sh` | start (boot, app, DevTools forward) / stop |
| `setup/build-images.sh` | the `ha-companion-lab-py` image (Python + websockets) and the Playwright image |
| `tools/emu.sh ui\|tap\|shot\|back\|home\|app` | screen readout, taps by text, screenshots, keys |
| `tools/cdp.sh` | evaluate JS in the app's page over plain CDP |
| `tools/prof.sh cov\|cpu\|mem\|listeners\|instr\|trace [-j action] [-x undo] [-b] ...` | profilers around an action in the page: exact JavaScript call counts, time per JavaScript function, memory (heap, DOM counters, allocations per function, process PSS), hardware instruction counts per process, a Chrome trace ([profiling.md](profiling.md)) |
| `tools/pwa.sh <script>` | run a Playwright `_android` script (path relative to the repository) |
| `tools/playwright/smoke.js` | attach to the app's WebView and print what it shows |
| `tools/playwright/visibility-pitfall.js` | shows that Playwright suppresses `visibilitychange` |
| `tools/cdp/fsprobe.py` | minimal element-fullscreen probe: how the app leaves fullscreen |
