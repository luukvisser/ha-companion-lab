#!/bin/bash
# bg-shots.sh <variant> <rounds>: background-and-return rounds with adb screenshots for 4 s after
# each relaunch; rates the card area of each screenshot as W (mostly near-white) or P (picture).
# Screenshots take 0.5-1.5 s each on the emulator: coarse. bg-video.sh is the fine-grained version.
#
# CARD_CROP (ffmpeg crop w:h:x:y, in screen pixels) is where the card sits on screen; the default
# fits the test dashboard on a 1080x2400 screen.
. "$(dirname "$0")/../../lib.sh"
CROP=${CARD_CROP:-1000:500:40:250}
O="$OUT_DIR/shots-$1"
rm -rf "$O"
mkdir -p "$O"
"$LAB_ROOT/tools/pwa.sh" video/advanced-camera-card/playwright/lf-setup.js "$1" >/dev/null || exit 1
sleep 5
for r in $(seq 1 "$2"); do
  leave_app "${LEAVE:-home}"
  sleep 8
  T0=$(now_ms)
  return_app "${LEAVE:-home}"
  i=0
  while [ $(( $(now_ms) - T0 )) -lt 4000 ]; do
    t=$(( $(now_ms) - T0 ))
    "$ADB" exec-out screencap -p > "$O/r$r-$i-$t.png"
    i=$((i + 1))
  done
  sleep 8
done
# The rounds count only if the page ran the variant's own build (interception ends when lf-setup.js
# detaches; a later card request would have gone to Home Assistant).
"$LAB_ROOT/tools/pwa.sh" video/advanced-camera-card/playwright/lf-read.js "$1" > "$O/log.json" &&
  python3 "$(dirname "$0")/tools/bg_summary.py" --check-variant "$O/log.json" || exit 1
# Every screenshot through one ffmpeg container, then rated here.
docker run --rm -u "$(id -u):$(id -g)" -v "$O:/o" --entrypoint sh "$LAB_MEDIAMTX_IMAGE" -c '
  for f in /o/*.png; do
    ffmpeg -hide_banner -loglevel error -y -i "$f" -vf "crop='"$CROP"',scale=100:50,format=gray" -f rawvideo "${f%.png}.gray"
  done'
for f in "$O"/*.gray; do
  name=$(basename "$f" .gray)
  echo "$name $(python3 "$(dirname "$0")/tools/rate_frames.py" "$f" 100 50 0)"
done | sort -t- -k1,1 -k3,3n
