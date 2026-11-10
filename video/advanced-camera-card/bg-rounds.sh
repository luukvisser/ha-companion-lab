#!/bin/bash
# bg-rounds.sh <variant> <rounds>: loads the test dashboard with card build <variant> (or
# `deployed`), sends the app to the background and back <rounds> times with nothing attached to the
# page, then prints per return, from the page's own log: what the card showed first and when, when
# a captured-frame image appeared and how long its decode took, and how long the card showed no
# video, image or canvas.
#
# The page log counts an <img> as shown while it may still be blank on screen (not decoded); check
# with bg-video.sh, which rates the real screen.
. "$(dirname "$0")/../../lib.sh"
"$LAB_ROOT/tools/pwa.sh" video/advanced-camera-card/playwright/lf-setup.js "$1" || exit 1
sleep 5
for _ in $(seq 1 "$2"); do
  leave_app "${LEAVE:-home}"
  sleep 8
  return_app "${LEAVE:-home}"
  sleep 12
done
"$LAB_ROOT/tools/pwa.sh" video/advanced-camera-card/playwright/lf-read.js "$1" > "$OUT_DIR/bg-$1.json"
python3 "$(dirname "$0")/tools/bg_summary.py" "$OUT_DIR/bg-$1.json"
