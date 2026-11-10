# Docker route

The Android emulator and the Companion app in a container, for Linux hosts with KVM and for CI.
`./lab up` uses it; this folder holds the runtime image, its entrypoint and the compose files.

```bash
./lab up                      # or by hand:
docker compose -f docker/compose.yml up -d               # first start: downloads a few GB, boots
docker compose -f docker/compose.yml logs -f emulator    # wait for "ready"
```

Before the first start, accept Google's Android SDK licence once (it is stored in the `sdk`
volume; nothing is downloaded before that):
`docker compose -f docker/compose.yml run --rm -it --entrypoint /lab/setup/accept-sdk-licenses.sh emulator`.

The app's login lives in the `avd` volume and survives restarts; `docker compose -f
docker/compose.yml down -v` removes it with the downloads.

| Part | What it does |
|---|---|
| `Dockerfile` | Ubuntu 24.04 (pinned) with the libraries the emulator loads, the download tools, Xvfb/x11vnc/noVNC for the optional viewer, Mesa and VirtualGL for the optional GPU route. The SDK pieces are not in it. |
| `entrypoint.sh` | installs the SDK pieces, creates the AVD the first time, starts the emulator and the app, then stays up; `stop` shuts the emulator down cleanly. |
| `compose.yml` | host networking (the container's adb server is the tools' `127.0.0.1:5037`), `/dev/kvm`, volumes `sdk`, `avd`, `data` |
| `compose.gpu.yml` | the opt-in GPU route (`./lab up --gpu`, [docs/gpu.md](../docs/gpu.md)) |

## Settings (on the `up` command)

`EMULATOR_HW_DECODER` (default `off`: WebRTC video needs the guest's software decoders),
`EMULATOR_AUDIO` (`none`, or `silent` for video with sound), `EMULATOR_GPU`, `APP_PIP`,
`LAB_MIC=1` (the lab microphone: a 1 kHz test tone), `VIEWER=1` (watch it in a browser). All of
them: [docs/settings.md](../docs/settings.md).

## Watching it: the viewer

`VIEWER=1 ./lab up` (or the compose command) serves the emulator's screen through noVNC on
127.0.0.1:6080. The URL (with a random token, new at every start) is in `/data/viewer-url` and the
VNC password in `/data/viewer-password`; read them yourself with
`docker compose -f docker/compose.yml exec emulator cat /data/viewer-url` (an agent must not print
them). VNC has no TCP port at all (only a unix socket), websockify connects only with the token,
VNC then asks its password, and the X displays have no TCP or abstract socket.

## Limits

- **Linux with KVM only.** Docker on macOS and Windows runs in a VM without `/dev/kvm`: use the
  [host route](../docs/host-route.md) there.
- **Software rendering by default** (SwiftShader): timings are slower than a phone's. The GPU
  route is faster but experimental.
- **One adb server.** The container's takes 127.0.0.1:5037; stop a host adb server first
  (`adb kill-server`).
- The WebView in the emulator crashes at app start now and then; the lab's scripts relaunch it.
