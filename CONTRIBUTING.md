# Contributing

Thanks for helping. This lab exists to replace assumptions about the Companion app with
measurements, so contributions are held to the same idea.

## Principles

- **Measure, never guess.** A claim about behaviour or timing in the app comes from a run on a
  device or emulator, and the pull request says what was measured, on which setup, and what was
  not. Where a cause is only inferred, measure it first.
- **Small pull requests.** One problem per pull request; separable features go into their own.
  Every part must be needed for the problem the pull request states.
- **Every claim tested.** The pull request says how you ran what you changed (route, versions,
  result) and what you could not run.
- **Never against someone's real home.** Use the lab's isolated test Home Assistant or a Home
  Assistant you own; never stream-test a household's real cameras; never log the app in with a
  real account (use the limited test user, `setup/ha-test-user.sh`).
- **No house data.** No tokens, passwords, LAN addresses, host names, entity or device names, or
  screenshots of a real dashboard. The checks grep for the obvious ones; you are responsible for
  the rest.
- **Licences.** Your contribution is under BSD-3-Clause. Do not add third-party code to the
  repository: fetch or build it at run time, and list it in [THIRD_PARTY.md](THIRD_PARTY.md).
  Never publish an image or volume that contains the Android SDK.

## Running the checks

The same checks run in CI on every pull request ([.github/workflows/checks.yml](.github/workflows/checks.yml)).
Locally, with Docker:

```bash
tools/checks.sh          # shellcheck, bash -n (bash 5 and 3.2), Python compile and self-tests,
                         # node --check, yamllint, the house-data grep, README link check
```

Changes that affect the emulator, the app or the stacks also need a run on a device: describe it in
the pull request.

## AI-assisted contributions

Welcome, with disclosure: say which model or tool you used and for what, and confirm you reviewed
and ran the change yourself. This repository itself was built with Claude Opus 5.5 and reviewed and
tested by its author.

## Reporting a problem

Open an issue with the route (host or Docker, OS), versions (emulator, system image, Companion app,
Home Assistant), the exact command and its output (with secrets removed). Security issues: see
[SECURITY.md](SECURITY.md).
