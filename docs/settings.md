# Settings

Every setting the lab reads, in one place. Set them in `lab.env` (copy `lab.env.example`; it is read
first) or in the environment of a command (`VAR=value lab ...`). What neither sets comes from
`defaults.env`, which you do not edit. Nothing here is secret: tokens and passwords live in their own
files (mode 600), named by the `*_FILE` settings, and no script prints them.

**Where they apply.** *lab.env* settings are read by every script through `lib.sh`. *Container*
settings are read when the emulator container starts (`docker/compose.yml`): set them on the
`lab up` / `docker compose up` command. *Run* settings are read by one measurement, on its command.

## Core: emulator, app, DevTools

| Setting | Default | Read by | What |
|---|---|---|---|
| `SDK_DIR` | `~/android-sdk` | setup/ | where the SDK pieces are installed (host route) |
| `API_LEVEL` | `37` | setup/ | the system image's Android API level (37 = Android 17) |
| `SDK_ABI` | the host's (x86_64 / arm64-v8a) | setup/ | the image's ABI |
| `AVD_NAME` | `ha-companion-lab` | setup/, lib.sh | the AVD; only an emulator running it is ever driven |
| `AVD_WIDTH`, `AVD_HEIGHT`, `AVD_DENSITY` | `1080`, `2400`, `420` | setup/create-avd.sh | the phone's screen |
| `EMULATOR_PORT` | `5554` | setup/start-emulator.sh | the emulator's console port (its serial is `emulator-<port>`) |
| `BOOT_TIMEOUT_STEPS` | `90` (× 4 s) | setup/start-emulator.sh | how long to wait for the boot |
| `ANDROID_SERIAL` | the lab's running emulator | lib.sh, Playwright | the device every adb call drives |
| `ADB_SERVER_PORT` | `5037` | lib.sh | the adb server |
| `COMPANION_VERSION` | `2026.11.1` | setup/get-companion-apk.sh | the Companion app release |
| `PKG` | `io.homeassistant.companion.android.minimal` | everything | the app's package |
| `HA_URL` | `http://127.0.0.1:$LAB_HA_PORT` (the lab's Home Assistant) | setup/, video/ha-setup.sh | Home Assistant as seen from this machine |
| `HA_URL_EMULATOR` | `http://localhost:$LAB_HA_PORT` (through adb reverse) | setup/app-login.sh | Home Assistant as seen from the emulator |
| `HA_TOKEN_FILE` | `$LAB_HA_DATA/token` | setup/, video/ha-setup.sh | file with an admin token (secret file) |
| `TEST_USER`, `TEST_USER_NAME` | `companion-lab`, `Companion lab` | setup/ha-test-user.sh | the limited user the app logs in with |
| `TEST_USER_PASSWORD_FILE` | `$LAB_HA_DATA/test-user-password` | setup/ | its password (secret file) |
| `CDP_PORT` | `9333` | lib.sh, tools/cdp | the app WebView's DevTools on this machine |
| `OUT_DIR` | `~/ha-companion-lab-data/out` | everything | results: `<name>.json` with `<name>.meta.json` |
| `LAB_STATE_DIR` | `~/ha-companion-lab-data/state` | lab, lib.sh | what the lab last set (card build, test stream) |
| `PW_IMAGE` | Playwright 1.62.0 (by digest) | tools/pwa.sh | the Playwright container |
| `PW_NODE_MODULES` | `~/ha-companion-lab-data/playwright/node_modules` | tools/pwa.sh | its `playwright-core` (`lab playwright-install`) |

## Container settings (the emulator container)

| Setting | Default | What |
|---|---|---|
| `EMULATOR_HW_DECODER` | `off` | `off`: the guest's software video decoders, which WebRTC video needs; `on`: the emulator's own |
| `EMULATOR_AUDIO` | `silent` | `silent` (a sound card without host sound: pages play the test stream's audio, nothing is heard), `none` (no sound card, `-no-audio`) |
| `EMULATOR_GPU` | `swiftshader_indirect` | the `-gpu` mode; `lab up --gpu` sets `host` with `docker/compose.gpu.yml` (docs/gpu.md) |
| `EMULATOR_VGL` | `0` | `1` (set by `docker/compose.gpu.yml`): run the emulator under VirtualGL with `vglfix.so` |
| `EMULATOR_FEATURES` | none | extra `-feature` flags, space-separated (e.g. `-Vulkan`) |
| `RENDER_GID` | none | the render node's group, for `docker/compose.gpu.yml` |
| `APP_PIP` | `on` (Android's default) | `on` or `off`: picture-in-picture for the app; applied at the emulator's start and whenever a script starts the app fresh, so `APP_PIP=off lab card ...` measures with it off (as on a real Pixel); `lab pip on\|off` switches it now; in a script `app_pip on\|off` (lib.sh) |
| `LAB_REVERSE_PORTS` | `8124` | host ports the app reaches as `localhost` (adb reverse, set at every start) |
| `LAB_MIC` | `0` | `1`: the emulator's microphone hears the lab's test tone (windowed build) |
| `VIEWER`, `VIEWER_PORT` | `0`, `6080` | `1`: the browser viewer (noVNC) on 127.0.0.1 |

## Video layer

| Setting | Default | Read by | What |
|---|---|---|---|
| `TEST_PATH` | `/test-dashboard/test` | measurements | the page under test |
| `OTHER_PATH` | `/profile/general` | measurements | a page to leave it for |
| `OVERLAY_CAMERA` | `camera.test_pattern` | hand-placed cards | the camera of an overlay card |
| `TESTSTREAM_PORT`, `TESTSTREAM_BIND` | `18554`, `127.0.0.1` | video/teststream | the stand-alone test stream |
| `LAB_GO2RTC_IMAGE`, `LAB_MEDIAMTX_IMAGE` | pinned by digest | all layers | the go2rtc and MediaMTX images |
| `TALK_STATUS_DIR`, `LAB_AUDIO_DATA` | under `~/ha-companion-lab-data` | video/audio | talk-back recordings and tones |

## Card layer

| Setting | Default | Read by | What |
|---|---|---|---|
| `BUILDS_DIR` | `~/ha-companion-lab-data/builds` | card measurements | one folder per card build (its `dist/`) |
| `CARD_PREFIX` | `/local/community/advanced-camera-card/` | card measurements | where Home Assistant serves the card |
| `CARD_CROP` | `1000:500:40:250` | bg-shots.sh, bg-video.sh | the card's area on screen (ffmpeg crop) |
| `BLIP_FRAMES` | off | run: `lab card blip` | `1`: count presented frames (only useful with `--gpu`) |
| `HOME_DELAYS` | `0.05,0.2,0.4` | run: `lab card blip-interrupt` | seconds from scheduling Home to pressing it, per round |
| `PINCH` | off | run: bg-video.sh | `1`: zoom the live view with a pinch before each round |
| `LEAVE` | `home` | run: bg-rounds.sh, bg-shots.sh, bg-video.sh | how the app is left and resumed: `home`, `switcher` (app switcher) or `off` (screen off and on); in fullscreen only `switcher` and `off` hide the page |
| `BG_SECONDS` | `5` | run: `lab card mute-cycles ... bg\|switcher\|off` | how long the app is away |
| `FRAMES` | off | run: loading-overlap.js | `1`: also print the raw per-frame log |

## The lab's Home Assistant (stack/)

To use your own Home Assistant instead, set `HA_URL`, `HA_URL_EMULATOR`, `HA_TOKEN_FILE` and
`TEST_USER_PASSWORD_FILE` in `lab.env` and start with `./lab up --own-ha`.

| Setting | Default | What |
|---|---|---|
| `LAB_HA_DATA` | `~/ha-companion-lab-data/stack` | its data folder (HA config, token, test user's password; mode 700) |
| `LAB_HA_PORT`, `LAB_WEBRTC_PORT` | `8124`, `8557` | its ports on 127.0.0.1 |
| `LAB_AVENT` | `auto` | the Philips Avent add-on: `on`, `off`, or `auto` (on when an aventproxy checkout is at `AVENT_INTEGRATION_SRC`) |
| `AVENT_INTEGRATION_SRC`, `AVENT_INTEGRATION_REF` | `~/aventproxy`, `origin/main` | where the integration is copied from (`WORKTREE`: the files as they are) |
| `AVENT_LAB_SIM_SOURCE`, `AVENT_LAB_CAMERA_NAME` | the test stream's `baby` path, `Lab baby monitor` | the simulated camera |
| `LAB_DEFAULT_BUILD`, `LAB_DEFAULT_STREAM` | `main`, the test stream's `pattern_pcma` (with audio) | the test camera's stream at `lab up`, and what `lab reset-state` restores |
| `LAB_PIN_HA_URL`, `LAB_PIN_HA_TOKEN_FILE`, `LAB_PIN_TEST_USER_PASSWORD_FILE` | none | set by the lab itself (all three or none): every write to Home Assistant goes to the pinned one; `lab.env` cannot set or change them (lib.sh) |
