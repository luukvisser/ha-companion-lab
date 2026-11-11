# Changelog

Dates are DD-MM-YYYY.

## Unreleased

Since then (11-11-2026):

- **audio by default:** the test camera streams `pattern_pcma` (with G.711 audio) and the emulator
  has a silent sound card (`EMULATOR_AUDIO=silent`); fixes for `lab up` after `lab down`, a stale
  AVD lock, and the stream recorded in `meta.json`.
- **`lab card doubletap`** uses Chrome's synthesized double tap and zooms in with `ptz_digital`:
  touch events sent one by one reach the page several times slower than sent.
- **new `lab card` measurements:** `menu` (the menu's layout per frame after a return), `taps` (menu
  buttons tapped while the media loads, traced to the action the card runs) and `config` (every
  camera card of a dashboard file: loads without a configuration error?).

First public version (11-11-2026):

- **core:** an Android 17 emulator in Docker (or on the host) with the Home Assistant Companion
  app, logged in as a limited test user; checked downloads and an explicit Android SDK licence
  step; Playwright and plain-CDP tools; `./lab` as the front door; a `meta.json` with every result.
- **the lab's Home Assistant (`stack/`):** a throwaway, internet-free Home Assistant started by
  `./lab up`, with go2rtc, a synthetic test stream, a test camera and a hidden test dashboard; an
  optional Philips Avent add-on with a fake vendor API, a simulated bridge, network conditions and
  talk-back analysis. `./lab up --own-ha` uses your own Home Assistant instead.
- **video:** synthetic test streams with sound scenes, a talk-back receiver, a video and audio
  delay measurement.
- **video/advanced-camera-card:** build and compare card builds in the app: fullscreen,
  background and return, calls, loading, zoom, rated screenshots and screen recordings.
- **profilers:** call counts, CPU per function, memory and listeners, instruction counts, traces.
- **WebRTC video in the emulator**, and **GPU rendering (experimental)** with `./lab up --gpu`.
- **CI:** all checks on every pull request; image builds on changes.
