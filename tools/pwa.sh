#!/bin/bash
# pwa.sh <script.js> [args]: runs a Playwright `_android` script (a path relative to the repository
# root, e.g. tools/playwright/smoke.js or video/playwright/dashlive.js) against the
# host's adb server (Playwright connects to 127.0.0.1:5037 and finds the app's WebView by package
# name itself; no port forwarding needed). Card builds are mounted at /builds, results go to /out.
#
# Caution: while Playwright is attached the page gets no visibilitychange events (README). Use
# tools/cdp.sh, a plain-CDP script, or a page-side log read after detaching, for anything about
# hidden/visible.
set -euo pipefail
. "$(dirname "$0")/../lib.sh"
S=$1
shift
# A lower CPU share for the container itself (`nice` on the docker command would only lower the
# client): measurements on the emulator compete for the same cores.
exec docker run --rm --cpu-shares 256 --network host -u "$(id -u):$(id -g)" -e HOME=/tmp \
  -e NODE_PATH=/w/node_modules -e ANDROID_SERIAL -e PKG -e CARD_PREFIX -e TEST_PATH -e OTHER_PATH -e OVERLAY_CAMERA \
  -v "$PW_NODE_MODULES:/w/node_modules:ro" -v "$LAB_ROOT:/lab:ro" \
  -v "$BUILDS_DIR:/builds:ro" -v "$OUT_DIR:/out" \
  "$PW_IMAGE" node "/lab/$S" "$@"
