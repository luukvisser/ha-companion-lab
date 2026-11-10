# video/audio/ — sound scenes and talk-back

- Two synthetic sound scenes in the test stream (ffmpeg filters, no recordings):
  - `baby`: a grey picture with a crying-like sound in bursts (AAC 16 kHz);
  - `doorbell`: a 4:3 picture, a chime, then speech-like noise, every 8 s (G.711 A-law 8 kHz).
- A **lab go2rtc** with the streams `doorbell` and `baby`: each plays its scene and has a
  "speaker" (`receiver.sh`) that records whatever is talked back to it.
- `check-talk.sh`: what a camera last heard: sessions, duration, level.

It brings its own copy of the test stream and does not touch Home Assistant or any other go2rtc.

```bash
video/audio/lab-go2rtc.sh up                 # starts both
video/audio/lab-go2rtc.sh tone doorbell      # go2rtc plays a 4 s 1 kHz tone into the speaker
video/audio/lab-go2rtc.sh check doorbell     # what arrived
video/audio/lab-go2rtc.sh down
```

**Locked down:** the lab go2rtc and its stream sit on an internal Docker network with no route
out and no published port; go2rtc's API listens on the container's own loopback and is driven with
`docker exec`, and it has no WebRTC module (so no STUN). Nothing on this machine or the LAN can
reach it.

**A card talking to a camera** goes through Home Assistant instead: the lab's Home Assistant with
the Avent add-on and `--bridge` carries talk-back to a simulated camera that records it
(`./lab card call`, `stack/stack.sh talk`). Home Assistant's own two-way audio needs a camera
integration that declares it; a Generic Camera never does.

## Good to know

- An `exec` backchannel needs its codec named: `#backchannel=1#audio=alaw/8000`.
- Do not analyse talk-back with an ffmpeg that waits on stdin; `receiver.sh` writes the raw bytes.
- `lavfi`'s `sine` starts at −18 dBFS: a "−6 dB" tone peaks at −24 dB.
- The card's microphone in the app needs a secure context; `http://localhost:8124` (through
  `adb reverse`, the lab's default) counts as one.
