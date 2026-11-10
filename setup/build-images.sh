#!/bin/bash
# build-images.sh: builds the small `ha-companion-lab-py` image (Python + websockets) used by the CDP
# tools and the Home Assistant setup scripts, and pulls the Playwright image.
set -euo pipefail
. "$(dirname "$0")/../lib.sh"
docker build -q -t ha-companion-lab-py "$LAB_ROOT/tools/cdp"
docker pull -q "$PW_IMAGE"
