#!/bin/bash
# blip-interrupt.sh <builds> <rounds>: like blip.sh, but each round leaves the app (Home) during the
# fullscreen transition, comes back, and then checks that a later real hidden spell (Home for 6 s)
# still acts (cdp/blip_interrupt.py; results in $OUT_DIR/blip-interrupt-<build>.json).
set -euo pipefail
. "$(dirname "$0")/../../lib.sh"
export BLIP_SCRIPT=blip_interrupt.py
# Home must land within the transition (a few hundred ms): a new `adb shell` per press took 1-3.5 s
# to start on a busy emulator (10-11-2026), so one device shell is opened now and fed commands.
fifo=$(mktemp -u)
mkfifo "$fifo"
"$ADB" shell <"$fifo" >/dev/null 2>&1 &
devshell=$!
exec 9>"$fifo"
rm -f "$fifo"
trap 'exec 9>&-; kill "$devshell" 2>/dev/null || true' EXIT
# blip.sh runs the script; this wrapper answers its HOSTACT lines (Home, back to the app).
"$(dirname "$0")/blip.sh" "$@" 2>&1 | while IFS= read -r line; do
  echo "$line"
  case "$line" in
    "HOSTACT homein "*)
      # HOSTACT homein <seconds> <token>: scheduled in the open device shell, confirmed at once.
      read -r _ _ secs token <<<"$line"
      printf '(sleep %s; cmd input keyevent 3) &\n' "$secs" >&9
      echo "$token" >"$OUT_DIR/host-done" ;;
    "HOSTACT home "*) printf 'cmd input keyevent 3\n' >&9; echo "${line##* }" >"$OUT_DIR/host-done" ;;
    "HOSTACT front "*) launch_app; echo "${line##* }" >"$OUT_DIR/host-done" ;;
  esac
done
