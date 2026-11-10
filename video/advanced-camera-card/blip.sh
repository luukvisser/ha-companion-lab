#!/bin/bash
# blip.sh <builds> <rounds>: for each build (comma-separated names under $BUILDS_DIR), install it
# into the lab's Home Assistant, start the app fresh, and measure what entering and leaving
# fullscreen does to the test dashboard card's live media (cdp/blip.py; results in
# $OUT_DIR/blip-<build>.json). The app restart per build is needed: a page reload leaves H.265
# WebRTC decoding nothing in the emulator (measured 10-11-2026), and the new card must load.
set -euo pipefail
. "$(dirname "$0")/../../lib.sh"
IFS=, read -r -a builds <<<"$1"
for b in "${builds[@]}"; do
  "$LAB_ROOT/stack/stack.sh" card "$b" >/dev/null
  fresh_app
  script=${BLIP_SCRIPT:-blip.py}
  name=${script%.py}
  write_meta "${name//_/-}-$b" "$b"
  lab_py /lab/video/advanced-camera-card/cdp/"$script" "$b" "$2"
done
