# Security

This is a test lab. It runs software that is meant to be poked at, so it is built to stay on the
machine it runs on. What it exposes, and how:

| Part | Listens on | Guard |
|---|---|---|
| `adb` server (host or Docker route) | 127.0.0.1:5037 | loopback only; anything local can use it (it can control the emulator) |
| The app's DevTools (forwarded) | 127.0.0.1:`CDP_PORT` | loopback only; full control of the app's page |
| noVNC viewer (Docker route, `VIEWER=1`) | 127.0.0.1:6080 (websockify); the VNC server itself on no TCP port, only a unix socket inside the container | a random 128-bit token in the URL (websockify connects only a URL with it to the VNC socket, so a page in a browser cannot reach the VNC server) plus a VNC password of 8 random letters and digits (VNC uses only the first 8 characters, about 47 bits); both in files with mode 600, never printed |
| Isolated test Home Assistant (`stack`) | 127.0.0.1:8124 (a proxy; HA itself only on an internal Docker network) | the stack's own users; never the production Home Assistant |
| Its go2rtc WebRTC | 127.0.0.1:8557 | loopback only; go2rtc's API (no login) only on the internal network, where Home Assistant drives it |
| Lab go2rtc for talk-back tests (`video/audio`) | nothing outside its own internal Docker network | its API is reached only through `docker exec`; WebRTC disabled; no STUN or other traffic leaves the machine |
| Test stream (MediaMTX) | 127.0.0.1:`TESTSTREAM_PORT` | loopback only; serves synthetic pictures only |
| The emulator's virtual displays (Docker route, viewer or microphone) | no TCP, no abstract socket: only a filesystem socket in the container's own `/tmp` | an X cookie (mode 600) in the container; the container shares the host's network namespace, where an abstract socket would be open to every local process, so Xvfb runs with `-nolisten local` |
| The lab microphone's Pulse server (Docker route, `LAB_MIC=1`) | unix sockets in the container's private `/tmp/lab-pulse` (mode 700) | `start-emulator.sh` uses it only if the folder and socket are real (no symlink), owned by the user with mode 700, and hold this run's id; the emulator gets no fallback server, so it can never use a desktop's real microphone |
| Devcontainer relays (`tools/devcontainer-bridge.sh`, opt-in) | the Docker bridge address | only connections from the default bridge's subnet are accepted (a LAN host routing to that address, or a container on another Docker network, is refused); any container on the default bridge can reach the lab while they run: stop them when done |

Rules the scripts enforce or follow:

- **Never point the lab at a production Home Assistant you are not testing on.** The isolated
  stack's scripts pin their target (`LAB_PIN_*`, captured before `lab.env` is read) and refuse any
  other; a hostile `lab.env` cannot redirect them.
- **The app logs in as a limited test user** (not the owner, not an admin, local network only).
  `setup/ha-test-user.sh` checks those rights as Home Assistant reports them and deletes the user
  again if they differ; it only ever removes a user with exactly those rights.
- **Secrets are never printed:** tokens, the test user's password, the VNC password and generated
  certificates live in files with mode 600 in the gitignored data folders. Do not run
  `uiautomator dump` (`tools/emu.sh ui`) while a password field is filled: it returns the field's
  text.
- **Downloads are verified or pinned:** Android SDK packages by SHA-1 from Google's repository XML,
  the Companion app by the SHA-256 GitHub lists. Container images (base images, the tools'
  images, go2rtc, MediaMTX, Playwright, Home Assistant) are pinned by digest; Python packages by
  version and wheel hash (`--require-hashes`); the Avent image's two Alpine packages (`iproute2`, `nftables`)
  and the CI example's `playwright-core` by exact version. Not pinned: the Ubuntu packages the
  Docker route's emulator image installs with `apt-get` (from the pinned Ubuntu release's own
  repositories, at build time).
- **No real cameras, no cloud, no other service on this machine:** the lab's Home Assistant
  has a synthetic camera; the Avent add-on fakes the vendor API inside the internal network. Home
  Assistant, the fake API and the bridge are only on an internal network; go2rtc and the proxy are also on `edge` (for the
  published ports), which has no NAT. On top of that, `stack.sh up` loads an outbound firewall
  into every stack container's own network namespace: a container may only talk to loopback, to the
  internal network (not its gateway, which is this machine) and answer connections made to it.
  Anything it starts towards the internet or this machine's own addresses (its LAN address, the
  Docker gateways, and so a production Home Assistant or go2rtc running here) is dropped. Measured:
  a listener on the edge network was reachable from an unlocked container and not from the locked
  go2rtc and proxy. The firewall is loaded a few seconds after the containers start,
  before onboarding tells anything in the stack to connect anywhere.

## Reporting a vulnerability

Please do not open a public issue for a security problem. Use GitHub's private vulnerability
reporting for this repository ("Report a vulnerability" under the Security tab). Include the route,
versions and steps to reproduce, without secrets.
