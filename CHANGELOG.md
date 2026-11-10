# Changelog

Dates are DD-MM-YYYY.

## Unreleased

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
