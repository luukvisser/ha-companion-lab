#!/bin/bash
# echo "<js expression>" | tools/cdp.sh: evaluates it in the app's page over plain DevTools (no
# Playwright, so visibility events stay real) and prints the JSON result. Needs the forward from
# setup/start-emulator.sh (or `forward_devtools` from lib.sh after an app restart).
. "$(dirname "$0")/../lib.sh"
lab_py /lab/tools/cdp/cdp.py
