#!/bin/bash
# bg-video.sh <variant> <rounds>: background-and-return rounds recorded with `adb screenrecord`;
# rates every frame (30 fps) of the card area as W (mostly white) or P (picture) and prints the
# segments in ms from the relaunch (negative: before it), e.g. `P@-1000 P@0 W@833 P@1267`. This is
# what was really on screen: the page's own log (bg-rounds.sh) cannot see an image that is present
# but not yet decoded.
#
# Timing: the recording's start and the relaunch are both stamped with the device's own clock
# (/proc/uptime) right before each command, and the difference is subtracted. What remains is
# screenrecord's own start-up before its first frame (not measured; typically tens of ms), so
# times may read slightly late.
#
# CARD_CROP (ffmpeg crop w:h:x:y, in screen pixels) is where the card sits on screen; the default
# fits the test dashboard on a 1080x2400 screen. PINCH=1 zooms the live view with a real two-finger
# pinch before each round. Recordings stay in $OUT_DIR/video-<variant>/.
. "$(dirname "$0")/../../lib.sh"
CROP=${CARD_CROP:-1000:500:40:250}
O="$OUT_DIR/video-$1"
rm -rf "$O"
mkdir -p "$O"
"$LAB_ROOT/tools/pwa.sh" video/advanced-camera-card/playwright/lf-setup.js "$1" >/dev/null || exit 1
sleep 5
for r in $(seq 1 "$2"); do
  if [ -n "${PINCH:-}" ]; then "$LAB_ROOT/tools/pwa.sh" video/advanced-camera-card/playwright/pinch.js >/dev/null 2>&1; sleep 2; fi
  leave_app "${LEAVE:-home}"
  sleep 8
  "$ADB" shell "cut -d' ' -f1 /proc/uptime > /sdcard/rec_t0; screenrecord --time-limit 6 --bit-rate 6000000 /sdcard/r.mp4" </dev/null &
  REC=$!
  sleep 1
  "$ADB" shell "cut -d' ' -f1 /proc/uptime > /sdcard/launch_t0; $(return_cmd "${LEAVE:-home}")" </dev/null
  wait "$REC"
  sleep 1
  "$ADB" pull /sdcard/r.mp4 "$O/r$r.mp4" </dev/null >/dev/null 2>&1
  rec=$("$ADB" shell cat /sdcard/rec_t0 </dev/null | tr -d '\r')
  launch=$("$ADB" shell cat /sdcard/launch_t0 </dev/null | tr -d '\r')
  python3 -c "print(round(($launch - $rec) * 1000))" > "$O/r$r.offset"
  sleep 6
done
# The rounds count only if the page ran the variant's own build (interception ends when lf-setup.js
# detaches; a later card request would have gone to Home Assistant).
"$LAB_ROOT/tools/pwa.sh" video/advanced-camera-card/playwright/lf-read.js "$1" > "$O/log.json" &&
  python3 "$(dirname "$0")/tools/bg_summary.py" --check-variant "$O/log.json" || exit 1
# Every recording through one ffmpeg container, then rated here.
docker run --rm -u "$(id -u):$(id -g)" -v "$O:/o" --entrypoint sh "$LAB_MEDIAMTX_IMAGE" -c '
  for f in /o/r*.mp4; do
    ffmpeg -hide_banner -loglevel error -y -i "$f" -vf "fps=30,crop='"$CROP"',scale=50:25,format=gray" -f rawvideo "${f%.mp4}.gray"
  done'
for r in $(seq 1 "$2"); do
  echo "round $r: $(python3 "$(dirname "$0")/tools/rate_frames.py" "$O/r$r.gray" 50 25 30 "$(cat "$O/r$r.offset")")"
done
