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
docker run --rm --network host -u "$(id -u):$(id -g)" -e HA_URL \
  -v "$HA_TOKEN_FILE:/token:ro" -v "$LAB_ROOT/video:/t:ro" \
  ha-companion-lab-py python -I /t/ha_setup.py "$@"
# What the lab set, for meta.json and `lab reset-state` (the stream address holds no secret).
mkdir -p "$LAB_STATE_DIR"
case "${1:-}" in
  camera) printf '%s\n' "$2" >"$LAB_STATE_DIR/test-camera-stream" ;;
  remove) rm -f "$LAB_STATE_DIR/test-camera-stream" ;;
esac
