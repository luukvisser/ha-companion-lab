---
name: ha-companion-lab
description: Measure how Home Assistant frontend code behaves in the Companion app on an Android emulator (layout, visibility, fullscreen, live video, timings), against a throwaway Home Assistant the lab starts, with a synthetic test camera and Advanced Camera Card build comparisons. Use when a claim about phone behaviour needs a measurement instead of an assumption.
---

# HA Companion lab

Use this toolkit when a change to Home Assistant frontend code (a card, a dashboard, a panel)
makes a claim about behaviour in the Companion app (a jump, a blip, a blank moment, a timing, what
happens on background/return or fullscreen), or when a cause is only inferred.

**Read [AGENTS.md](../../../AGENTS.md) in the repository root first.** It holds the full instructions:
the layers, the app's test user, which tool to choose, and what to do afterwards. This skill repeats
only its hard rules, which CI keeps identical (`tools/checks.sh`, "hard rules in step"). The front
door is `./lab` (`./lab help`); settings are in docs/settings.md.

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
