# video/ — test camera layer

A synthetic camera, so stream tests never need a real (or someone's private) camera. With the
lab's Home Assistant (`./lab up`) all of this is set up for you: the test stream, the camera
`camera.test_pattern` and the hidden test dashboard `/test-dashboard/test`.

- `teststream/`: MediaMTX with ffmpeg test pictures and sound over RTSP.
- `ha-setup.sh` / `ha_setup.py`: the stream as a Home Assistant Generic Camera and a hidden test
  dashboard (not in the sidebar, open to the non-admin test user) with one camera card, whose
  configuration you set per test.
- `playwright/dashlive.js`, `playwright/live.js`: live-video checks in the app.
- [audio/](audio/README.md): sound scenes and a go2rtc that records what is talked back to it.
- `tools/av-delay.sh`: video and audio delay from the source to the app (below).

```bash
video/ha-setup.sh dashboard '{"camera_entity":"camera.test_pattern","live_provider":"ha"}'
tools/pwa.sh video/playwright/dashlive.js     # opens the dashboard in the app, reports the <video>
```

![The test picture](../docs/images/test-pattern.jpg)

*The `pattern` picture: ffmpeg's `testsrc2`, with a running clock and frame counter top left.*

## Stream paths

| Path | Video | Audio |
|---|---|---|
| `pattern` | H.264 1280×720 15 fps | AAC 16 kHz, a beeping 440 Hz tone |
| `pattern_video` | same | none |
| `pattern_pcma` | same | G.711 A-law 8 kHz, a beeping tone (the lab's default) |
| `pattern_h265` | H.265 1280×720 15 fps | none |
| `baby`, `doorbell` | see [audio/](audio/README.md) | |
| `sync`, `sync_aac` | 30 fps with a time code, for `tools/av-delay.sh` | G.711 / AAC with a beep each second |

## With your own Home Assistant

```bash
TESTSTREAM_BIND=127.0.0.1 video/teststream/teststream.sh up    # or this machine's LAN address
video/ha-setup.sh camera rtsp://<address Home Assistant reaches this machine on>:18554/pattern
video/ha-setup.sh dashboard '<card JSON>'
video/ha-setup.sh remove --dashboard                           # afterwards
```

This needs an admin token in `HA_TOKEN_FILE` (used only by `ha-setup.sh`) and the card installed.
The host port is 18554, because the emulator itself listens on 8554.

## Delay measurement

`video/tools/av-delay.sh 20 round1` (with `LAB_MIC=1` and the app showing a card on the `sync_aac`
path) reads the source time stamped in each frame and beep, a page clock drawn by the app, and the
emulator's sound output, and reports the video delay, the audio delay and the offset between them.
Its uncertainty is about ±50 ms; the details are in the script's header and `tools/av_delay.py`
(`--self-test`).

## Good to know

- **A hand-placed card does not start Home Assistant live video** (`live.js`): HA's stream element
  asks for capabilities before it has `hass` and does not retry. For live video, use the test
  dashboard.
- **Resolution: 1080p is the top that plays reliably.** On the default route (the guest's
  software decoders, `EMULATOR_HW_DECODER=off`) 1440p and 4K give frames only now and then,
  through WebRTC and at low bitrates (4K at 4 Mbit/s, 1440p at 7 Mbit/s); 4K at 12 Mbit/s gave
  no frame in 170 s, and HLS gave none. For 4K over HLS: `lab down`, then
  `EMULATOR_HW_DECODER=on lab up`; use H.264 (not HEVC), preferably 4 Mbit/s. WebRTC does not
  work in that mode (the WebView then offers no H.264 for it). Expect the first frame only after
  a card retry (about 50-120 s), about 1 fps, and "isn't responding" dialogs (tap Wait). Use it to
  see that a picture comes, never for timing claims. Measured 24-11-2026 under heavy host load,
  so the speeds are pessimistic; on a real phone, which decodes 4K in hardware, this was not
  measured.
- **A stopped stream is not frozen video.** After a stop, the card reconnected about 13 s later and
  played about 2 s of buffered media; something that stamps frames must not count that as new.
