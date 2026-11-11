#!/bin/bash
# ha-setup.sh camera|dashboard|remove [...]: runs video/ha_setup.py against $HA_URL with the
# token from $HA_TOKEN_FILE (mounted read-only into the container, never printed). Examples:
#
#   video/ha-setup.sh camera rtsp://192.0.2.10:18554/pattern
#   video/ha-setup.sh dashboard '{"camera_entity":"camera.test_pattern","live_provider":"ha"}'
#   video/ha-setup.sh dashboard '{"camera_entity":"camera.test_pattern","live_provider":"ha",
#       "image":{"mode":"last_frame"}}' '{"status_bar":{"items":{"title":{"enabled":false}}}}'
#   video/ha-setup.sh remove [--dashboard]   (the camera; --dashboard also the test dashboard)
#
# The RTSP address is as Home Assistant sees it (the host running teststream, from HA's side).
set -euo pipefail
. "$(dirname "$0")/../lib.sh"
assert_pinned_target
[ -r "$HA_TOKEN_FILE" ] || { echo "no token file at HA_TOKEN_FILE ($HA_TOKEN_FILE)" >&2; exit 1; }
out=$(docker run --rm --network host -u "$(id -u):$(id -g)" -e HA_URL \
  -v "$HA_TOKEN_FILE:/token:ro" -v "$LAB_ROOT/video:/t:ro" \
  ha-companion-lab-py python -I /t/ha_setup.py "$@") || { printf '%s\n' "$out"; exit 1; }
printf '%s\n' "$out"
# What the lab set, for meta.json and `lab reset-state` (the stream address holds no secret). An
# existing camera keeps its stream, so only a camera that was really added is recorded (11-11-2026:
# `lab up` recorded pattern_video over a camera that stayed on pattern_pcma).
mkdir -p "$LAB_STATE_DIR"
case "${1:-}" in
  camera) case "$out" in *"already there"*) ;; *) printf '%s\n' "$2" >"$LAB_STATE_DIR/test-camera-stream" ;; esac ;;
  remove) rm -f "$LAB_STATE_DIR/test-camera-stream" ;;
esac
