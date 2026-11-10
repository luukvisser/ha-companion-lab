#!/bin/bash
# fullscreen-measure.sh <variants> <rounds> <api|back|swipe> <expanded 0|1>
# Plain-CDP measurement of a camera card entering and leaving fullscreen in the app, per card build
# (comma-separated variant names under $BUILDS_DIR; each build is served to the emulator only).
# Leaving: `api` = document.exitFullscreen(), `back` = the Android back key, `swipe` = two edge
# swipes (in immersive fullscreen the first only shows the system bars). Results in
# $OUT_DIR/result.json; summarise with:
# python3 video/advanced-camera-card/cdp/summary.py $OUT_DIR/result.json
. "$(dirname "$0")/../../lib.sh"
rm -f "$OUT_DIR/back-done" "$OUT_DIR/result.json"
write_meta result "$1"
lab_py /lab/video/advanced-camera-card/cdp/measure.py "$1" "$2" "$3" "$4" 2>&1 | while IFS= read -r line; do
  echo "$line"
  # "HOSTACT <back|swipe> <token>": do it, then confirm with that round's token.
  case "$line" in
    "HOSTACT back "*)
      "$ADB" shell input keyevent 4 </dev/null
      echo "${line##* }" > "$OUT_DIR/back-done" ;;
    "HOSTACT swipe "*)
      "$ADB" shell input touchscreen swipe 1 1200 450 1200 200 </dev/null
      sleep 1.5
      "$ADB" shell input touchscreen swipe 1 1200 450 1200 200 </dev/null
      echo "${line##* }" > "$OUT_DIR/back-done" ;;
  esac
done
