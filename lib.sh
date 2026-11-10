# shellcheck shell=bash
# Sourced by the scripts: loads lab.env and defaults.env and defines helpers.
LAB_ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
# A caller that must reach one particular Home Assistant (stack/stack.sh: the
# lab's own HA) pins it with LAB_PIN_* in the environment. Captured here, BEFORE lab.env is read,
# into read-only variables: lab.env can neither change them nor set a pin of its own (a LAB_PIN_*
# it assigns is ignored, an assignment to LAB_PINNED_* fails).
# Once per shell ($$): lib.sh may be sourced twice; a value inherited from the environment does not count.
if [ "${LAB_PINNED_SET:-}" != "$$" ]; then
  readonly LAB_PINNED_HA_URL="${LAB_PIN_HA_URL:-}"
  readonly LAB_PINNED_HA_TOKEN_FILE="${LAB_PIN_HA_TOKEN_FILE:-}"
  readonly LAB_PINNED_TEST_USER_PASSWORD_FILE="${LAB_PIN_TEST_USER_PASSWORD_FILE:-}"
  readonly LAB_PINNED_SET=$$
fi
# A pin is all three or nothing: a pinned run that wrote the test user's password into the main
# HA's password file would break the main HA's app login (review 3).
if [ -n "$LAB_PINNED_HA_URL$LAB_PINNED_HA_TOKEN_FILE$LAB_PINNED_TEST_USER_PASSWORD_FILE" ] &&
  { [ -z "$LAB_PINNED_HA_URL" ] || [ -z "$LAB_PINNED_HA_TOKEN_FILE" ] || [ -z "$LAB_PINNED_TEST_USER_PASSWORD_FILE" ]; }; then
  echo "a pin needs all of LAB_PIN_HA_URL, LAB_PIN_HA_TOKEN_FILE and LAB_PIN_TEST_USER_PASSWORD_FILE" >&2
  exit 1
fi
# Your settings (lab.env, optional), then the defaults for everything they leave unset (defaults.env
# keeps any value already set). Editing lab.env.example changes nothing: it is only a template.
if [ -f "$LAB_ROOT/lab.env" ]; then
  # shellcheck source=/dev/null
  . "$LAB_ROOT/lab.env"
fi
# shellcheck source=defaults.env
. "$LAB_ROOT/defaults.env"
# Apply the pin captured above over whatever lab.env set.
if [ -n "$LAB_PINNED_HA_URL" ]; then
  HA_URL=$LAB_PINNED_HA_URL
  HA_TOKEN_FILE=$LAB_PINNED_HA_TOKEN_FILE
  TEST_USER_PASSWORD_FILE=$LAB_PINNED_TEST_USER_PASSWORD_FILE
  # Whatever lab.env assigned to LAB_PIN_* is undone too, for the scripts this one starts.
  export LAB_PIN_HA_URL=$LAB_PINNED_HA_URL LAB_PIN_HA_TOKEN_FILE=$LAB_PINNED_HA_TOKEN_FILE \
    LAB_PIN_TEST_USER_PASSWORD_FILE=$LAB_PINNED_TEST_USER_PASSWORD_FILE
fi
# For scripts that write to Home Assistant, right before they do: under a pin, every file and
# address they are about to use must be the pinned one (anything the script or a helper changed
# after lib.sh is refused), and the caller's own LAB_PIN_* must still agree with what lib.sh
# captured (a script that re-exported another pin is refused too).
assert_pinned_target() {
  [ -z "$LAB_PINNED_HA_URL" ] && return 0
  local bad=
  [ "$HA_URL" = "$LAB_PINNED_HA_URL" ] || bad="HA_URL $HA_URL"
  [ "$HA_TOKEN_FILE" = "$LAB_PINNED_HA_TOKEN_FILE" ] || bad="$bad HA_TOKEN_FILE $HA_TOKEN_FILE"
  [ "$TEST_USER_PASSWORD_FILE" = "$LAB_PINNED_TEST_USER_PASSWORD_FILE" ] ||
    bad="$bad TEST_USER_PASSWORD_FILE $TEST_USER_PASSWORD_FILE"
  [ "${LAB_PIN_HA_URL:-}" = "$LAB_PINNED_HA_URL" ] || bad="$bad LAB_PIN_HA_URL changed"
  if [ -n "$bad" ]; then
    echo "refusing: not the pinned target $LAB_PINNED_HA_URL ($bad)" >&2
    exit 1
  fi
}
ADB="$SDK_DIR/platform-tools/adb"
# The device every adb call and Playwright script drives: ANDROID_SERIAL (adb's own variable), by
# default the running emulator whose AVD is the lab's ($AVD_NAME), so neither a phone attached next
# to it nor another emulator (e.g. one from Android Studio) is ever driven by mistake.
avd_of() {
  local name
  name=$("$ADB" -s "$1" shell getprop ro.boot.qemu.avd_name </dev/null 2>/dev/null | tr -d '\r')
  [ -n "$name" ] || name=$("$ADB" -s "$1" emu avd name </dev/null 2>/dev/null | head -1 | tr -d '\r')
  printf '%s' "$name"
}
# Whether an adb server already listens (ADB_SERVER_PORT, default 5037), checked without adb: any
# adb command starts a server when none runs, and sourcing lib.sh must never do that (a host server
# started by a script that never uses adb would then fight the Docker route's server for the port).
adb_server_up() {
  (exec 3<>"/dev/tcp/127.0.0.1/${ADB_SERVER_PORT:-5037}") 2>/dev/null
}
default_serial() {
  [ -x "$ADB" ] || return 0
  adb_server_up || return 0
  local list serial
  list=$("$ADB" devices </dev/null 2>/dev/null) || return 0
  for serial in $(printf '%s\n' "$list" | awk '$1 ~ /^emulator-/ && $2 == "device" {print $1}'); do
    if [ "$(avd_of "$serial")" = "$AVD_NAME" ]; then
      printf '%s\n' "$serial"
      return 0
    fi
  done
}
if [ -z "${ANDROID_SERIAL:-}" ]; then
  ANDROID_SERIAL=$(default_serial)
fi
# Only when known: an empty ANDROID_SERIAL would make adb look for a device named "".
if [ -n "${ANDROID_SERIAL:-}" ]; then export ANDROID_SERIAL; else unset ANDROID_SERIAL; fi
mkdir -p "$OUT_DIR" "$BUILDS_DIR"

# The host, in the terms of Google's SDK repository: HOST_OS linux|macosx, HOST_ARCH x64|aarch64,
# and the system image ABI that runs at native speed on it (x86_64, or arm64-v8a on Apple Silicon).
# shellcheck disable=SC2034  # HOST_OS is read by the scripts that source this file
case "$(uname -s)" in
  Linux) HOST_OS=linux ;;
  Darwin) HOST_OS=macosx ;;
  *) HOST_OS=unsupported ;;
esac
case "$(uname -m)" in
  x86_64 | amd64) HOST_ARCH=x64 ;;
  arm64 | aarch64) HOST_ARCH=aarch64 ;;
  *) HOST_ARCH=unsupported ;;
esac
if [ -z "${SDK_ABI:-}" ]; then
  [ "$HOST_ARCH" = aarch64 ] && SDK_ABI=arm64-v8a || SDK_ABI=x86_64
fi

# The lab microphone (EMULATOR_AUDIO=lab-mic): the emulator may only use the Pulse server that
# docker/entrypoint.sh started in this run. A world-writable /tmp lets anyone place a folder or a
# symlink at /tmp/lab-pulse, e.g. pointing at a desktop's real Pulse server and so its real
# microphone; checked: PULSE_SERVER is exactly that socket, the folder is a real folder (no symlink)
# owned by this user with mode 700, the socket is a real socket owned by this user, and the folder
# holds this run's id (LAB_PULSE_RUN, set by the entrypoint).
lab_pulse_ok() {
  local dir=/tmp/lab-pulse sock=/tmp/lab-pulse/native me mode
  me=$(id -u)
  if [ "${PULSE_SERVER:-}" != "unix:$sock" ]; then
    echo "lab microphone: PULSE_SERVER must be unix:$sock (the lab's own server)" >&2; return 1
  fi
  if [ -L "$dir" ] || [ ! -d "$dir" ] || [ -L "$sock" ] || [ ! -S "$sock" ]; then
    echo "lab microphone: $dir or its socket is missing or a symlink; refusing" >&2; return 1
  fi
  mode=$(stat -c '%u %a' "$dir" 2>/dev/null || stat -f '%u %Lp' "$dir")
  if [ "$mode" != "$me 700" ] || [ "$(stat -c %u "$sock" 2>/dev/null || stat -f %u "$sock")" != "$me" ]; then
    echo "lab microphone: $dir is not this user's private folder ($mode); refusing" >&2; return 1
  fi
  if [ -z "${LAB_PULSE_RUN:-}" ] || [ "$(cat "$dir/run-id" 2>/dev/null)" != "$LAB_PULSE_RUN" ]; then
    echo "lab microphone: $dir was not made by this run of docker/entrypoint.sh; refusing" >&2; return 1
  fi
}

# Portable helpers (GNU coreutils on Linux, BSD tools on macOS).
sha1_of() { if command -v sha1sum >/dev/null; then sha1sum "$1"; else shasum -a 1 "$1"; fi | cut -d' ' -f1; }
sha256_of() { if command -v sha256sum >/dev/null; then sha256sum "$1"; else shasum -a 256 "$1"; fi | cut -d' ' -f1; }
size_of() { wc -c <"$1" | tr -d ' '; }
# Milliseconds since the epoch (macOS's date has no %N).
now_ms() { python3 -c 'import time; print(int(time.time() * 1000))'; }

# The app's process id, empty when it does not run.
app_pid() { "$ADB" shell pidof "$PKG" </dev/null 2>/dev/null | tr -d '\r'; }

# Forward the app WebView's DevTools socket to localhost:$CDP_PORT. The socket name carries the
# pid, so do this again after the app restarted.
forward_devtools() {
  local pid
  pid=$(app_pid)
  [ -n "$pid" ] || { echo "the app does not run" >&2; return 1; }
  "$ADB" forward --remove-all
  "$ADB" forward "tcp:$CDP_PORT" "localabstract:webview_devtools_remote_$pid" >/dev/null &&
    echo "DevTools of pid $pid on localhost:$CDP_PORT"
}

# Start the app. `</dev/null`: adb shell reads stdin, and inside a `while read` loop it would eat
# the loop's input.
launch_app() { "$ADB" shell monkey -p "$PKG" -c android.intent.category.LAUNCHER 1 </dev/null >/dev/null 2>&1; }

# Ways out of the app and back, for scripts and `lab key`. They differ in what the page sees
# (measured 10-11-2026): out of fullscreen all three hide the page; in fullscreen `home` does NOT
# (no visibilitychange, the video keeps playing), `switcher` and `off` do.
#   leave_app home|switcher|off      Home key | app switcher (recents) | screen off (power key)
#   return_app home|switcher|off     the app to the front | the same | screen on, keyguard dismissed
# return_cmd prints the device-side command of return_app, for scripts that stamp it themselves.
leave_app() {
  case "${1:-home}" in
    home) "$ADB" shell input keyevent 3 </dev/null ;;
    switcher) "$ADB" shell input keyevent 187 </dev/null ;;
    off) "$ADB" shell input keyevent 26 </dev/null ;;
    *) echo "unknown way out: $1 (home, switcher, off)" >&2; return 2 ;;
  esac
}
return_cmd() {
  case "${1:-home}" in
    home | switcher) echo "monkey -p $PKG -c android.intent.category.LAUNCHER 1 >/dev/null 2>&1" ;;
    off) echo "input keyevent 224; sleep 0.5; wm dismiss-keyguard" ;;
    *) echo "unknown way back: $1" >&2; return 2 ;;
  esac
}
return_app() {
  local c
  c=$(return_cmd "${1:-home}") || return 2
  "$ADB" shell "$c" </dev/null
}

# app_pip on|off: picture-in-picture for the app (Android's per-app permission; also allow|ignore).
app_pip() {
  local mode
  case "${1:-$APP_PIP}" in
    on | allow) mode=allow ;;
    off | ignore) mode=ignore ;;
    *) echo "app_pip on|off (got: ${1:-})" >&2; return 2 ;;
  esac
  "$ADB" shell appops set "$PKG" PICTURE_IN_PICTURE "$mode" </dev/null
}

# fresh_app: start the app fresh and wait until its WebView has a page on DevTools (the socket appears only
# once it loads). Up to 5 launches: the WebView crashes at start now and then (below).
fresh_app() {
  local try pages pid
  # Picture-in-picture as set (APP_PIP, default on): `APP_PIP=off lab card ...` measures with it off.
  app_pip "$APP_PIP" || return 1
  for try in 1 2 3 4 5; do
    "$ADB" shell am force-stop "$PKG" </dev/null
    launch_app
    for _ in $(seq 40); do
      sleep 1
      forward_devtools >/dev/null 2>&1 || continue
      # Captured, then matched: a piped grep -q can fail the pipeline on SIGPIPE (pipefail).
      pages=$(curl -sf "http://127.0.0.1:$CDP_PORT/json" 2>/dev/null || true)
      case "$pages" in
        *'"type": "page"'*)
          # The WebView sometimes crashes about 1 s into the page load (SIGSEGV, 3-5 of 10
          # starts, with and without the WebView flag, 10-11-2026): only a page that is still
          # there 5 s later, in the same process, counts.
          pid=$(app_pid)
          sleep 5
          pages=$(curl -sf "http://127.0.0.1:$CDP_PORT/json" 2>/dev/null || true)
          if [ -n "$pid" ] && [ "$(app_pid)" = "$pid" ]; then
            case "$pages" in *'"type": "page"'*) return 0 ;; esac
          fi
          break ;;
      esac
    done
    echo "no page on DevTools after launch $try; relaunching" >&2
  done
  return 1
}
# write_meta <name> [build]: the setup of a measurement run, as JSON in $OUT_DIR/<name>.meta.json
# (lablib.save_result merges it into each result's meta.json; LAB_META_FILE points the container at
# it). Read-only: device properties, the WebView flag file, the emulator container's settings, the
# card build's hash, what the lab last set (LAB_STATE_DIR) and, under a pin, the test dashboard's card
# and resource as Home Assistant has them (ha_setup.py show). Never a token or password.
write_meta() {
  local name=$1 build=${2:-} hash="" dash="null" route=host hw=""
  mkdir -p "$OUT_DIR"
  if [ -n "$build" ] && [ -f "$BUILDS_DIR/$build/advanced-camera-card.js" ]; then
    hash=$(sha256sum "$BUILDS_DIR/$build/advanced-camera-card.js" | cut -c1-16)
  fi
  if docker inspect ha-companion-lab-emulator-1 >/dev/null 2>&1; then
    route=docker
    hw=$(docker inspect ha-companion-lab-emulator-1 --format '{{range .Config.Env}}{{println .}}{{end}}' |
      awk -F= '/^EMULATOR_(HW_DECODER|AUDIO)=/ {printf "%s%s=%s", sep, $1, $2; sep=" "}')
  fi
  if [ -n "${LAB_PINNED_HA_URL:-}" ] && [ -r "${HA_TOKEN_FILE:-}" ]; then
    dash=$(docker run --rm --network host -u "$(id -u):$(id -g)" -e HA_URL -v "$HA_TOKEN_FILE:/token:ro" \
      -v "$LAB_ROOT/video:/t:ro" ha-companion-lab-py python -I /t/ha_setup.py show 2>/dev/null || echo null)
  fi
  M_INFO=$( [ -n "$build" ] && tr '\n' ' ' <"$BUILDS_DIR/$build/BUILD-INFO" 2>/dev/null || true) \
    M_NAME=$name M_BUILD=$build M_HASH=$hash M_DASH=$dash M_ROUTE=$route M_EMU=$hw M_STATE=$LAB_STATE_DIR \
    M_FLAGS=$("$ADB" shell cat /data/local/tmp/webview-command-line </dev/null 2>/dev/null | tr -d '\r' || true) \
    M_APP=$("$ADB" shell dumpsys package "$PKG" </dev/null 2>/dev/null | awk -F= '/versionName/ {print $2; exit}' | tr -d '\r') \
    M_WV=$("$ADB" shell dumpsys package com.google.android.webview </dev/null 2>/dev/null | awk -F= '/versionName/ {print $2; exit}' | tr -d '\r') \
    M_ANDROID=$("$ADB" shell getprop ro.build.version.release </dev/null 2>/dev/null | tr -d '\r') \
    python3 -I - "$OUT_DIR/$name.meta.json" <<'PY'
import json, os, sys
e = os.environ
def state(n):
    try:
        return open(os.path.join(e["M_STATE"], n)).read().strip() or None
    except OSError:
        return None
try:
    ha = json.loads(e.get("M_DASH") or "null")
except ValueError:
    ha = None
json.dump({
    "run": e["M_NAME"], "build": e["M_BUILD"] or None, "build_sha256_16": e["M_HASH"] or None,
    "build_info": e.get("M_INFO", "").strip() or None,
    "installed_build": state("card-build"), "test_camera_stream": state("test-camera-stream"),
    "home_assistant": ha, "route": e["M_ROUTE"], "emulator": e["M_EMU"] or None,
    "android": e["M_ANDROID"] or None, "companion_app": e["M_APP"] or None, "webview": e["M_WV"] or None,
    "webview_flags": e["M_FLAGS"] or None,
    "env": {k: v for k, v in e.items() if k.startswith(("BLIP_", "HOME_DELAYS", "PINCH", "TEST_PATH"))},
}, open(sys.argv[1], "w"), indent=1)
PY
  export LAB_META_FILE="/out/$name.meta.json"
}

# Run a Python script from the lab in the ha-companion-lab-py image, on the host network.
lab_py() {
  docker run --rm -i --cpu-shares 256 --network host -u "$(id -u):$(id -g)" \
    -e CDP_PORT -e CARD_PREFIX -e OVERLAY_CAMERA -e HA_URL -e TEST_PATH -e OTHER_PATH -e BLIP_FRAMES -e HOME_DELAYS -e BG_SECONDS \
    -e LAB_META_FILE \
    -v "$LAB_ROOT:/lab:ro" -v "$BUILDS_DIR:/builds:ro" -v "$OUT_DIR:/out" \
    ha-companion-lab-py python -I -u "$@"
}
export LAB_HA_DATA LAB_HA_PORT LAB_WEBRTC_PORT LAB_AVENT
export CDP_PORT CARD_PREFIX OVERLAY_CAMERA HA_URL PKG TEST_PATH OTHER_PATH CARD_CROP
export APP_PIP
export TEST_USER TEST_USER_NAME TEST_USER_PASSWORD_FILE HA_URL_EMULATOR TESTSTREAM_PORT
export LAB_GO2RTC_IMAGE LAB_MEDIAMTX_IMAGE
