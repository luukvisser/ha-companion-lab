# stack/: the lab's own Home Assistant

A throwaway Home Assistant for the emulator's app to log in to, so nothing touches a Home Assistant
you care about. `./lab up` starts it; you rarely need `stack.sh` directly.

```
 this machine            ┌─────────────── internal network (no internet) ───────────────┐
 127.0.0.1:8124 ── proxy ┤ Home Assistant ── go2rtc ── test stream (MediaMTX)           │
 127.0.0.1:8557 ─────────┤                    (WebRTC media)                              │
                         │ Avent add-on: fake Tuya API, simulated bridge                 │
                         └───────────────────────────────────────────────────────────────┘
```

What `up` sets up: Home Assistant (onboarded, owner `lab-owner` with a random password, a token),
go2rtc for WebRTC, the synthetic test stream, the lab's **limited test user** for the app (not an
admin, local network only), the **test camera** `camera.test_pattern` and the **test dashboard**
`/test-dashboard/test`. The app reaches it as `http://localhost:8124` (adb reverse). Credentials
are only in `$LAB_HA_DATA`, mode 600, and are never printed.

## Commands

```bash
stack/stack.sh up [--bridge]   # build, start, set up (idempotent)
stack/stack.sh status          # containers, addresses, the camera
stack/stack.sh card <build>    # install a card build from $BUILDS_DIR and point the dashboard resource at it
stack/stack.sh down            # containers away, data kept
stack/stack.sh reset           # containers and data folder away (asks first)
stack/netem.sh delay 300 50 | loss 5 | rate 800 | cut | restore | clear [service]   # network conditions
```

## Isolation

- Every container sits on an internal network without internet; only the proxy (HA, 8124) and
  go2rtc's WebRTC port (8557) are published, on 127.0.0.1. `up` also loads a firewall into every
  container's network that drops outbound traffic outside the stack.
- **Only this stack is written to.** The scripts get its address, token and password files pinned
  (`LAB_PIN_*`, lib.sh), which `lab.env` cannot override, and refuse a write unless the address is
  the port this stack's own proxy publishes.

## The Philips Avent add-on (optional)

With an [aventproxy](https://github.com/thekoma/aventproxy) checkout at `AVENT_INTEGRATION_SRC`
(or `LAB_AVENT=on`), `up` also adds the Philips Avent integration (copied from the checkout into
the data folder, never into this repository) against a **fake Tuya API** (`fake_tuya.py`, with a
lab CA only this HA trusts), and `--bridge` adds aventproxy's **simulated bridge**
(`avent-bridge:sim`, built from the checkout): a fake baby monitor with video, sound and two-way
audio. `stack.sh talk` shows what the simulated camera received in a call (length, level, the
lab tone's frequency); `stack.sh dps '{"207": 2450}'` sets the monitor's data points. Files:
`compose.avent.yml`, `fake_tuya.py`, `certs.py`, `sim_talk.py`.

## Fake LAN monitors (optional)

`LAB_AVENT_LAN=on stack/stack.sh up` (with the Avent add-on) adds two fake baby monitors that speak
the Tuya LAN protocol (`lan_monitor.py`, `compose.avent-lan.yml`), so the integration's LAN client
(`lan.py`, tinytuya) can be measured and its fixes proven without a real camera:

- `lab-lan-34` (172.31.240.30) speaks 3.4 and is the monitor the fake Tuya API already reports;
  `lab-lan-33` (172.31.240.31) speaks 3.3 and is a second device, "Lab second monitor". With the
  switch on, the fake API hands both a local key, so the integration starts its LAN client; with it
  off, no device has one, as before. The keys are made up at the first `up`
  (`$LAB_HA_DATA/lan/monitors.json`, mode 600, never printed). The integration adds new devices
  only in its config flow: the second monitor appears in a fresh data folder.
- Discovery: UDP 6667 broadcasts every 5 s on the lab network (3.5 in its own framing, and an
  answer to tinytuya's discovery request on 7000); `AVENT_LAB_LAN_DISCOVERY=off` for a Home
  Assistant that gets none, as in a bridge network. Nothing binds a port on this machine.
- TCP 6668: the 3.4/3.5 session-key handshake, heartbeats, DP_QUERY (on 3.3 answered with "json obj
  data unvalid", as an SCD923 does), writes (acknowledged, then pushed to every session).
- As measured on an SCD951 (02-11-2026): at most 3 sessions, a 4th is refused; a wrong-key handshake
  holds its session 10 s before the monitor drops it.

```bash
stack/stack.sh lan 34 state                    # protocol, faults, open sessions, data points
stack/stack.sh lan 34 push '{"207": 2450}'     # change data points and push them (24.5 C)
stack/stack.sh lan 34 fault silent             # keep TCP open, answer nothing (refuse: no new
                                               # sessions; close: close every session; normal)
stack/stack.sh lan 34 version 3.5              # a firmware update: sessions close, then 3.5
stack/stack.sh lan 34 discovery off            # stop (or start) the broadcasts
stack/stack.sh lan 34 ip 172.31.240.40         # back on the network at another address
stack/stack.sh lan selftest                    # lan_monitor.py --self-test, tinytuya as the client
```

**What it proves, and what not.** The fake speaks the protocol as tinytuya (the integration's client
library) and the integration understand it, so it proves how the integration handles these frames
and faults, not how real firmware behaves. The session limit, the wrong-key hold and the 3.3 query
answer follow measurements on real monitors; how a 4th session is refused, empty acks, pushes after
a write and the rest are assumptions, listed in `lan_monitor.py`. LAN and cloud data points are
separate: a push changes Home Assistant's state until the next cloud poll brings the cloud's value.

## Settings

`LAB_HA_DATA`, `LAB_HA_PORT`, `LAB_WEBRTC_PORT`, `LAB_AVENT`, `AVENT_INTEGRATION_SRC`,
`AVENT_INTEGRATION_REF` and `LAB_AVENT_LAN`: see [docs/settings.md](../docs/settings.md).
