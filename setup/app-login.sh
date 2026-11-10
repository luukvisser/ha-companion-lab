#!/bin/bash
# app-login.sh <HA URL as the emulator sees it, e.g. http://localhost:8124>: walks the Companion
# app's onboarding (2026.11 on Android 17) with the lab's limited test user (setup/ha-test-user.sh):
# server address, local-network access, the login (filled over DevTools from the 600 password file,
# never typed through adb, never printed), the device name, and declines location and
# notifications. Run it on a freshly installed app (setup/get-companion-apk.sh).
#
# Never dumps the screen (uiautomator) while the login form is on screen: Android reports the text
# of password fields too. The screens before and after the login are read by their texts only.
set -euo pipefail
. "$(dirname "$0")/../lib.sh"
URL=${1:?usage: app-login.sh <HA URL from the emulator, e.g. http://localhost:8124>}
[ -s "$TEST_USER_PASSWORD_FILE" ] || { echo "no test user password at $TEST_USER_PASSWORD_FILE: run setup/ha-test-user.sh create first" >&2; exit 1; }

# Texts of the screen, one per line (only for screens without a password field).
# emu.sh prints each text as a Python string literal: in single quotes, or in double quotes when
# the text has an apostrophe ("you're").
texts() { "$LAB_ROOT/tools/emu.sh" ui 2>/dev/null | python3 -c 'import sys,re; [print(m.group(2)) for l in sys.stdin for m in [re.search(r"^\S+ ([\x27\x22])(.*?)\1", l)] if m and m.group(2)]'; }
has() { texts | grep -q -i -- "$1"; }
tap() { "$LAB_ROOT/tools/emu.sh" tap "$1" >/dev/null; }
wait_for() { for _ in $(seq 1 "${2:-20}"); do has "$1" && return 0; sleep 2; done; return 1; }

"$ADB" shell pm grant "$PKG" android.permission.ACCESS_LOCAL_NETWORK </dev/null 2>/dev/null || true
launch_app
# From the welcome screen, or from the address screen if an earlier run got that far.
wait_for "Connect to my Home\|What is your Home\|Enter address manually\|Welcome home\|name this device" 30 || { echo "the app's welcome screen did not appear" >&2; exit 1; }
at_login=""; past_login=""
has "name this device" && past_login=1           # an earlier run already logged in
has "Welcome home" && at_login=1                # an earlier run reached the (empty) login page
if [ -z "$at_login" ] && [ -z "$past_login" ]; then
if has "Connect to my Home"; then tap "Connect to my Home"; sleep 3; fi
has "Don.t allow" && tap "Don"           # a nearby-devices prompt: local-network access is granted above
wait_for "Enter address manually\|What is your Home" 20 || { echo "no address screen" >&2; exit 1; }
has "Enter address manually" && { tap "Enter address manually"; sleep 2; }
wait_for "What is your Home" 10 || { echo "no address field" >&2; exit 1; }
# Tap the address field (the screen's only edit field) and type the address.
bounds=$("$LAB_ROOT/tools/emu.sh" ui | awk '/^EditText/ {print; exit}' | grep -o '\[[0-9,]*\]\[[0-9,]*\]')
xy=$(python3 -c 'import re,sys; a=list(map(int,re.findall(r"\d+",sys.argv[1]))); print((a[0]+a[2])//2,(a[1]+a[3])//2)' "$bounds")
# shellcheck disable=SC2086 # two numbers
"$ADB" shell input tap $xy </dev/null
"$ADB" shell input text "$URL" </dev/null
sleep 1
tap "Connect"
fi

# The login page is a web page in the app's WebView: from here on, no UI dumps until it is gone.
if [ -z "$past_login" ]; then
for _ in $(seq 1 30); do
  pid=$("$ADB" shell pidof "$PKG" </dev/null 2>/dev/null | tr -d '\r') || true
  [ -n "$pid" ] && "$ADB" shell cat /proc/net/unix </dev/null 2>/dev/null | grep -q "webview_devtools_remote_$pid" && break
  sleep 2
done
forward_devtools
rc=0
docker run --rm --network host -u "$(id -u):$(id -g)" -e CDP_PORT -e TEST_USER \
  -v "$TEST_USER_PASSWORD_FILE:/secret:ro" -v "$LAB_ROOT/setup:/t:ro" \
  ha-companion-lab-py python -I -u /t/app_login_cdp.py || rc=$?
# The app takes the login over natively, so the page itself may not show that it went through;
# its next screen does. (On a failed login the DevTools step has cleared the password field, so
# reading the screen is safe from here.)
[ "$rc" = 2 ] && { echo "no login form appeared" >&2; exit 1; }
wait_for "name this device" 15 || { echo "the login did not go through (no device-name screen)" >&2; exit 1; }
fi

# After the login: keep the suggested device name (the emulator's model), then the remote-access
# note, the location question (no location), and the notifications sheet (no notifications),
# which only appears once the dashboard has loaded.
has "name this device" && tap "Save"
for _ in $(seq 1 12); do
  sleep 3
  if has "Got it"; then tap "Got it"
  elif has "Less secure"; then tap "Less secure"; sleep 1; tap "Next"
  elif has "Do not allow"; then tap "Do not allow"; break
  elif has "Don.t allow"; then tap "Don"
  fi
done
forward_devtools
echo "logged in as $TEST_USER at $URL"
