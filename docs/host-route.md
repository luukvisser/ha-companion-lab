# Other machines and the host route

The same `setup/` scripts run in each route; only where the emulator runs differs.

| Your machine | Route | Status |
|---|---|---|
| Linux x86_64 with KVM | **Host**: `setup/` scripts directly (below), with a window to watch | used for the first measurements |
| Linux x86_64 with KVM, or CI | **Docker**: `docker/compose.yml`, headless, optional browser viewer ([docker/README.md](../docker/README.md)) | run end to end (the lab's default route) |
| GitHub Actions | the Docker route in [.github/workflows/emulator-smoke.yml](../.github/workflows/emulator-smoke.yml) (manual trigger) | **untested** |
| macOS, Apple Silicon | **Host**: same scripts; `install-sdk.sh` picks the macOS aarch64 emulator and the arm64-v8a image | download plan checked against Google's XML; **not run on a Mac** |
| macOS, Intel | **Host**: macOS x64 emulator, x86_64 image | download plan checked; **not run** |
| Windows | **WSL2** with nested virtualisation (Windows 11: `/dev/kvm` inside WSL2) and the Linux host route, or the Windows emulator from Android Studio with these tools pointed at its adb | **not tried**; the scripts are bash and do not handle native Windows |

Pitfalls of the routes:

- **No KVM in Docker on macOS and Windows.** Docker there runs containers in a VM without
  `/dev/kvm`: the Docker route is Linux-only. On a Mac the emulator runs natively (Apple's
  Hypervisor framework), so the host route is the one there.
- **Software GPU everywhere.** The host GPU mode froze the app's WebView in our tests, so the AVD
  uses swiftshader on every route: slow, and it inflates timings ([pitfalls.md](pitfalls.md)).
- **The login lives in the AVD.** On the host it is in `~/.android/avd/`; in Docker in the `avd`
  volume, so `docker compose down -v` logs the app out (and deletes the downloads).
- **One adb server.** The Docker route's adb server takes 127.0.0.1:5037 (host networking); stop a
  host adb server first.
- **Emulator channel.** `install-sdk.sh` takes the newest *stable* emulator; the measurements here
  ran on 37.3.8 (build 16847572), a newer build from Google's preview channel.

## Requirements (host route)

- Linux on x86_64 with **KVM** usable by your user (`/dev/kvm`; the `kvm` group or an ACL), or a
  Mac (Apple Silicon or Intel). Python 3, curl and unzip.
- **Docker**, for the Python and Playwright tools. No Java, no Android Studio, no sudo.
- About 3 GB of disk for the SDK pieces and image; about 3 GB of RAM and two cores for the
  emulator while it runs.
- A Home Assistant reachable from this machine and a user for the emulator to log in with: a
  limited test user (`setup/ha-test-user.sh create`: not an admin, local network only).
- For Playwright: a `node_modules` with `playwright-core` matching the Playwright image (1.62),
  e.g. a frontend repository's after installing its dependencies (`PW_NODE_MODULES`).

## The host route, step by step

```bash
cp lab.env.example lab.env          # only if something differs from defaults.env (docs/settings.md)
setup/build-images.sh               # ha-companion-lab-py image, Playwright image
setup/accept-sdk-licenses.sh        # once: read and accept Google's Android SDK licence (by you)
setup/install-sdk.sh                # emulator, adb, system image; SHA-1 checked against Google's XML
setup/create-avd.sh                 # the AVD, written by hand (no Java); checks KVM
setup/start-emulator.sh             # boot (the app does not exist yet: ignore its error)
setup/get-companion-apk.sh          # Companion app (minimal APK) + the local-network permission
```

Log in once in the emulator window: "Connect to my Home Assistant server" → "Enter address
manually" → `http://10.0.2.2:8123` for a Home Assistant of your own (the emulator's alias for this machine; use Home Assistant's
LAN address if it runs elsewhere), or let `setup/app-login.sh` do it as the limited test user
(about two minutes; it fills the login page through DevTools, keeps the default device name and
answers the onboarding prompts). Then:

```bash
setup/start-emulator.sh             # launches the app, forwards its DevTools to localhost:9333
tools/pwa.sh tools/playwright/smoke.js     # Playwright attaches: prints the page and viewport
echo 'document.title' | tools/cdp.sh       # plain CDP: evaluates JS in the app's page
tools/emu.sh shot first                    # screenshot to $OUT_DIR/first.png
setup/stop-emulator.sh
```
