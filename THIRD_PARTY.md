# Third-party components

This repository contains only its own files (BSD-3-Clause, see [LICENSE](LICENSE)). It vendors no
third-party code. Everything below is downloaded, pulled or built **on the user's machine** when a
script runs; nothing is redistributed by this repository.

**Never publish a Docker image or volume built by this lab.** The emulator's SDK, system image and
app are downloaded into volumes at first start (`docker/`), the test Home Assistant image is
derived locally (`stack/`), and the simulated bridge image is built from aventproxy;
publishing them would redistribute third-party software under terms this repository does not
handle (in particular Google's Android SDK License Agreement does not allow redistribution).

| Component | Used by | Licence | How it gets here | Redistributed by this repo |
|---|---|---|---|---|
| Android SDK: emulator, platform-tools (`adb`), system image (Google APIs, x86_64 or arm64-v8a) | core | [Android Software Development Kit License Agreement](https://developer.android.com/studio/terms) | `setup/install-sdk.sh` from Google's repository, SHA-1 checked, **only after the user accepted the licence** (`setup/accept-sdk-licenses.sh`) | no |
| Home Assistant Companion app for Android (minimal APK) | core | Apache-2.0 ([home-assistant/android](https://github.com/home-assistant/android)) | `setup/get-companion-apk.sh` from the GitHub release, SHA-256 checked against GitHub's digest | no |
| Playwright (container image with browsers; `playwright-core` in CI) | core | Apache-2.0 (bundled browsers under their own licences: Chromium BSD-style, Firefox MPL-2.0, WebKit LGPL/BSD) | `docker pull mcr.microsoft.com/playwright` (pinned by digest); npm in the CI example (exact version) | no |
| Python container (`python:3.13-alpine`, pinned by digest) and `websockets` 15.0.1 | core (`tools/cdp`) | PSF-2.0 and others (base image); BSD-3-Clause (websockets) | built locally by `setup/build-images.sh`; websockets by version and wheel hash | no |
| Ubuntu base image (`ubuntu:noble`, pinned by digest) and its packages: Xvfb (MIT/X11), x11vnc (GPL-2.0-or-later), noVNC (MPL-2.0), websockify (LGPL-3.0), PulseAudio (LGPL-2.1-or-later), curl (curl licence), unzip (Info-ZIP), Python 3 (PSF-2.0), emulator runtime libraries | core, Docker route | per package (Ubuntu archive) | built locally from `docker/Dockerfile` | no |
| VirtualGL 3.1.5 (`virtualgl_3.1.5_amd64.deb` from its GitHub release, SHA-256 pinned in `docker/Dockerfile`) | core (the opt-in GPU route, `docker/compose.gpu.yml`) | wxWindows Library Licence 3.1 (LGPL-2.1 with an exception) | `ADD` with checksum and `apt-get install` in the emulator image, built locally | no |
| Mesa (Ubuntu packages `libegl1`, `libgles2`, `libgl1-mesa-dri`, `mesa-vulkan-drivers`, `libvulkan1`, `mesa-utils`) | core (the GPU route) | MIT (Mesa) and others per package | `apt-get install` in the emulator image | no |
| gcc and libc6-dev (Ubuntu) | core (the GPU route: builds `docker/vglfix/vglfix.c` into the image, then removed) | GPL-3.0-or-later with the GCC Runtime Library Exception; LGPL-2.1 (glibc) | `apt-get install` during the image build, purged afterwards | no |
| MediaMTX (`bluenviron/mediamtx:*-ffmpeg`, pinned by digest), which includes FFmpeg (built with libx264, so GPL-2.0-or-later as a whole) | video | MIT (MediaMTX); GPL/LGPL (FFmpeg, x264) | `docker pull`, pinned | no |
| go2rtc (`alexxit/go2rtc`, pinned by digest), which includes Alpine's FFmpeg 8.1.3 (`--enable-gpl`, with x264 and x265: GPL-2.0-or-later as a whole); the lab runs that FFmpeg (talk-back tone, `check-talk.sh`, `ffmpeg:` sources) | video/audio, stack | MIT (go2rtc); GPL-2.0-or-later and LGPL-2.1-or-later (FFmpeg), GPL-2.0-or-later (x264, x265) | `docker pull`, pinned | no |
| Home Assistant (`ghcr.io/home-assistant/home-assistant`, pinned by digest) | stack | Apache-2.0 | `docker pull` as the base of a locally derived image | no |
| tinytuya 1.20.0 and colorama 0.4.6 | stack | MIT (tinytuya); BSD-3-Clause (colorama) | `pip install` by version and wheel hash into the locally derived Home Assistant image | no |
| iproute2 7.0.0 (`tc`) | stack (`netem.sh`) | GPL-2.0-or-later | `apk add` (exact version) into the locally derived Home Assistant image | no |
| nftables 1.1.6 (`nft`, the stack's outbound firewall) | stack (`stack.sh lockdown`) | GPL-2.0-only | `apk add` into the locally derived Home Assistant image | no |
| Philips Avent integration ([aventproxy](https://github.com/thekoma/aventproxy) `custom_components/philips_avent`) | stack | MIT | copied at `stack.sh up` from a local aventproxy checkout into the stack's data folder (gitignored) | no |
| Simulated Avent bridge (`avent-bridge:sim`, aventproxy's `sim` command) | stack | MIT | built locally from an aventproxy checkout (`docker/Dockerfile.sim`) | no |
| Advanced Camera Card builds | video/advanced-camera-card | MIT ([dermotduffy/advanced-camera-card](https://github.com/dermotduffy/advanced-camera-card)) | built locally by the user from a card checkout and served into the test HA or the emulator only | no |
| GitHub Actions (`actions/checkout`, pinned by commit) | CI | MIT | run by GitHub | no |
| Containers and tools used by the checks (`tools/checks.sh`): `koalaman/shellcheck`, `bash:3.2` and `bash:5.2`, `node:22-alpine`, `python:3.13-alpine` with yamllint, pathspec and PyYAML installed by pip at run time, `lycheeverse/lychee` | CI and local checks | GPL-3.0 (ShellCheck), GPL-3.0 (bash), MIT (Node.js), PSF-2.0 (Python), GPL-3.0 (yamllint), MPL-2.0 (pathspec), MIT (PyYAML), Apache-2.0 or MIT (lychee) | `docker run`, pinned by digest; the Python packages from PyPI by version and wheel hash | no |
| socat (`alpine/socat`, pinned by digest) | `tools/devcontainer-bridge.sh` | GPL-2.0 | `docker run`, pulled on use | no |

Screenshots in `docs/images/` were taken in this lab: they show the Android emulator's interface,
Home Assistant's interface (Apache-2.0) and a synthetic test picture generated by FFmpeg's
`testsrc2`. They contain no camera footage and no household data.

`stack/fake_tuya.py` imitates, for interoperability testing only, the request and
response shapes the Philips Avent integration expects from Tuya's mobile API. It contains no Tuya
code, keys or data, and it only answers inside the stack's internal network.
