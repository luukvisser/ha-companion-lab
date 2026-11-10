#!/bin/bash
# ha-test-user.sh create|remove|status: a limited Home Assistant user for the lab's app login
# (not an admin, local network only), so the emulator never logs in with a real account.
#
# Needs an admin's long-lived token in $HA_TOKEN_FILE. The password goes to
# $TEST_USER_PASSWORD_FILE (mode 600) and is never printed; setup/app-login.sh reads it from there.
# Safe for an LLM to run: neither the token nor the password appears in its output.
set -euo pipefail
. "$(dirname "$0")/../lib.sh"
assert_pinned_target
[ -r "$HA_TOKEN_FILE" ] || { echo "no token file at HA_TOKEN_FILE ($HA_TOKEN_FILE)" >&2; exit 1; }
mkdir -p "$(dirname "$TEST_USER_PASSWORD_FILE")"
[ -e "$TEST_USER_PASSWORD_FILE" ] || install -m 600 /dev/null "$TEST_USER_PASSWORD_FILE"
chmod 600 "$TEST_USER_PASSWORD_FILE"
docker run --rm --network host -u "$(id -u):$(id -g)" -e HA_URL -e TEST_USER -e TEST_USER_NAME -e LAB_TEST_FAIL_AFTER_CREATE \
  -v "$HA_TOKEN_FILE:/token:ro" -v "$TEST_USER_PASSWORD_FILE:/secret" -v "$LAB_ROOT/setup:/t:ro" \
  ha-companion-lab-py python -I /t/ha_test_user.py "${1:-status}"
