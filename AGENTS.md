# AGENTS.md

Instructions for AI coding agents working in or with this repository (Codex, Copilot, Cursor,
Gemini CLI, Claude Code and others that read `AGENTS.md`). Claude Code also has the same text as a
skill in `.claude/skills/ha-companion-lab/SKILL.md`; keep the two in step.

Use this toolkit when a change to Home Assistant frontend code (a card, a dashboard, a panel)
makes a claim about behaviour in the Companion app (a jump, a blip, a blank moment, a timing, what
happens on background/return or fullscreen), or when a cause is only inferred.

## Hard rules

- **Measure, never guess.** Base claims on measurements in this lab or on a real device, never on
  what the code suggests should happen. Say what was measured, on what, and what was assumed.
- **Only the isolated test Home Assistant.** Point the lab at the Home Assistant `./lab up`
  starts (or a test instance the user named), never at a production Home Assistant.
- **The app logs in as the limited test user** (`setup/ha-test-user.sh`), never a real account.
  Ask the user before creating one.
- **Never print secrets:** tokens, the test user's password, the VNC password, certificates and
  keys stay in their files (mode 600). Never dump the screen's UI (`uiautomator dump`,
  `tools/emu.sh ui`) while a password field is filled: it returns the field's text.
- **Licences:** never accept the Android SDK licence (or any other) for the user; they accept it
  themselves (`setup/accept-sdk-licenses.sh`).
- **No real cameras, no cloud:** never stream-test a real household camera; use the synthetic test
  stream and the simulated bridge.

## Rule: measure, never guess

- A cause marked "likely", "inferred" or "from memory" is a question to measure first.
- Measure yourself where the toolkit can. Where only a real phone can answer (real GPU timings, a
  specific device), give the user two or three ways to measure, easiest first, and wait.
- In plans and PR texts, say what was measured (and on what: emulator, browser, phone) and what was
  assumed. Never quote emulator absolute timings as phone timings.
- Repeat a measurement (3-5 rounds) before concluding; give per-round numbers or a median with range.

## Start

`./lab up` starts everything: the lab's own Home Assistant (isolated, no internet; `stack/`) with
the test stream, the camera `camera.test_pattern`, the hidden test dashboard and the limited test
user, then the emulator with the app logged in. Check `./lab status` first: it may already run.
`./lab up --own-ha` uses the Home Assistant named in `lab.env` instead; ask the user before that.

- **video/**: the test stream and the test dashboard's card:
  `video/ha-setup.sh dashboard '<card JSON>'`. Never stream-test real cameras of a household.
- **video/advanced-camera-card/**: only for that card. `./lab build <checkout> <name>`, then
  `./lab card <measurement> <builds>`, which installs each build into the lab's Home Assistant.
  Against another Home Assistant, the scripts serve a build by interception and check afterwards
  that the page ran it.
- **The Avent add-on** (`LAB_AVENT`, on when an aventproxy checkout exists): a fake vendor API and,
  with `./lab up --bridge`, a simulated bridge for calls and network conditions (`netem.sh`). Never
  stream-test a real monitor: a family's parent unit comes first.

## The app's login: a limited test user

The app logs in with a test user, never with a real account.

- The lab's Home Assistant creates it by itself. On another Home Assistant, ask the user before
  creating one, and run `setup/ha-test-user.sh status` first.
- `setup/ha-test-user.sh create` makes it through Home Assistant's API (an admin token in
  `HA_TOKEN_FILE` is needed). The script checks the rights as Home Assistant reports them (not the
  owner, only the `system-users` group, local network only) and deletes the user again if they
  differ. It refuses to touch an existing user of that name with more rights.
- Show the user the output of `status` afterwards.
- The password goes to `TEST_USER_PASSWORD_FILE` (mode 600). Never print, read out or repeat it, nor
  the token. Do not run `uiautomator dump` (`tools/emu.sh ui`) while a password field is filled: it
  returns the field's text.
- When done: `setup/ha-test-user.sh remove` (it only removes a user with the limited rights).
- Never print `/data/viewer-password` (the Docker route's VNC password) or anything under the
  lab data folders' credential files; the user reads those themselves.

## Choosing the tool

- Start with `./lab status` (what runs, which build, stream and card configuration) and
  `./lab help`; card measurements are `./lab card <measurement> <builds>`, profilers `./lab prof`.
  Every result in `$OUT_DIR` has a `<name>.meta.json` with its setup: quote it with the result.
- Layout, DOM, network, which build loads: Playwright, `tools/pwa.sh <path/to/script.js>`.
- Anything involving `visibilitychange` (background/return, auto-mute, lazy unload, freeze): plain
  CDP (`tools/cdp.sh`, `video/advanced-camera-card/fullscreen-measure.sh`), or a page-side recorder
  installed with Playwright and read back after Playwright detached (`lf-setup.js` → action →
  `lf-read.js`). Playwright attached = no visibility events.
- How much work something costs (comparing builds): `tools/prof.sh cov` (exact call counts); a
  fixed piece of work in instructions: `tools/prof.sh instr`; where time goes: `tools/prof.sh trace`.
  Durations in the emulator are not a phone's (docs/profiling.md).
- What the user really saw: a screenshot (`tools/emu.sh shot`) or a screen recording
  (`bg-video.sh`). A page log counts an undecoded, still blank `<img>` as shown.
- Live video: a real dashboard (the test dashboard), not a hand-placed card.
- Never `tools/emu.sh ui` while a password field is filled.
- Leaving fullscreen: back key, or two edge swipes.

## Afterwards

Put the lab back and stop it: `./lab reset-state` (default card build, test camera stream and test
card, app restarted), then `./lab down --all` (the emulator and the isolated stack): the emulator
takes most of a 4-core machine.
