#!/bin/bash
# desktop.sh [call seconds]: the desktop-browser route against the lab's Home Assistant (headless
# Chromium from the Playwright image; video/desktop/desktop.js). A second client beside the emulator:
# desktop Chromium's own decoders, and a fake microphone that plays the lab tone. Logs in as the
# limited test user (its password file is mounted read-only and never printed). Then
# `stack/stack.sh talk` shows what reached the camera.
set -euo pipefail
. "$(dirname "$0")/../../lib.sh"
pw="$LAB_HA_DATA/test-user-password"
[ -r "$pw" ] || { echo "no test-user password at $pw (stack/stack.sh up)" >&2; exit 1; }
tone="$LAB_STATE_DIR/lab-tone.wav"
if [ ! -f "$tone" ]; then
  mkdir -p "$LAB_STATE_DIR"
  # The lab tone as a file: 1 kHz, 2 s on, 1 s off, -20 dBFS peak, 48 kHz mono, 60 s.
  python3 -I - "$tone" <<'PY'
import math, struct, sys, wave
rate, amp = 48000, 32767 * 10 ** (-20 / 20)
frames = bytearray()
for n in range(60 * rate):
    on = (n / rate) % 3 < 2
    frames += struct.pack("<h", int(amp * math.sin(2 * math.pi * 1000 * n / rate)) if on else 0)
with wave.open(sys.argv[1], "wb") as w:
    w.setnchannels(1); w.setsampwidth(2); w.setframerate(rate); w.writeframes(bytes(frames))
PY
fi
exec docker run --rm --network host -u "$(id -u):$(id -g)" -e HOME=/tmp -e NODE_PATH=/w/node_modules \
  -e TEST_PATH -e TEST_USER -e DESKTOP_HA_URL="http://127.0.0.1:$LAB_HA_PORT" \
  -v "$PW_NODE_MODULES:/w/node_modules:ro" -v "$LAB_ROOT:/lab:ro" \
  -v "$pw:/secret/password:ro" -v "$tone:/tone.wav:ro" \
  "$PW_IMAGE" node /lab/video/desktop/desktop.js "${1:-0}"
