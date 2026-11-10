#!/bin/bash
# stop-emulator.sh: stops the emulator cleanly and removes the DevTools forward.
set -uo pipefail
. "$(dirname "$0")/../lib.sh"
"$ADB" forward --remove-all 2>/dev/null
"$ADB" emu kill 2>/dev/null && echo "emulator stopping" || echo "no emulator running"
