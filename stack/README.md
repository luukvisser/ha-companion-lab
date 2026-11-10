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

## Settings

`LAB_HA_DATA`, `LAB_HA_PORT`, `LAB_WEBRTC_PORT`, `LAB_AVENT`, `AVENT_INTEGRATION_SRC` and
`AVENT_INTEGRATION_REF`: see [docs/settings.md](../docs/settings.md).
