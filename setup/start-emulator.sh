#!/bin/bash
# start-emulator.sh [--no-window]: starts the AVD, waits for boot, launches the Companion app and
# forwards its WebView's DevTools to localhost:$CDP_PORT.
#
# Software GPU (swiftshader): the host GPU mode froze the app's WebView. It is slow: the emulator
# takes most of a 4-core machine while video plays, which inflates every timing (README).
set -euo pipefail
. "$(dirname "$0")/../lib.sh"

# Output captured first, then searched: `adb ... | grep -q` under pipefail can fail even on a match
# (grep exits at the first hit, adb then gets SIGPIPE).
devices=$("$ADB" devices </dev/null)
running=" $(printf '%s\n' "$devices" | awk '$2 == "device" {printf "%s ", $1}')"
if [ -n "${ANDROID_SERIAL:-}" ] && case "$running" in *" $ANDROID_SERIAL "*) true ;; *) false ;; esac; then
  # Only the lab's own AVD counts: never adopt (and log in, measure on, kill) a foreign emulator.
  avd=$(avd_of "$ANDROID_SERIAL")
  if [ "$avd" != "$AVD_NAME" ]; then
    echo "refusing: $ANDROID_SERIAL runs the AVD '${avd:-unknown}', not the lab's '$AVD_NAME'" >&2
    exit 1
  fi
  echo "the emulator $ANDROID_SERIAL already runs"
else
  # This emulator's own console port, and with it its serial: every adb call and Playwright script
  # then drives this one, even with a phone or another emulator attached. By default the first
  # console port (5554, 5556, ...) no running emulator uses.
  if [ -z "${EMULATOR_PORT:-}" ]; then
    EMULATOR_PORT=5554
    while case "$running" in *" emulator-$EMULATOR_PORT "*) true ;; *) false ;; esac; do
      EMULATOR_PORT=$((EMULATOR_PORT + 2))
    done
  fi
  ANDROID_SERIAL="emulator-$EMULATOR_PORT"
  export ANDROID_SERIAL
  # No array for the optional flag: "${extra[@]}" of an empty array aborts under `set -u` in
  # bash before 4.4, and macOS ships bash 3.2.
  window=""
  [ "${1:-}" = "--no-window" ] && window="-no-window"
  # Audio. EMULATOR_AUDIO=silent (the default): the guest keeps its sound card, the emulator gives it
  # no host sound (QEMU_AUDIO_DRV=none): nothing is heard or recorded, but a page that plays sound
  # has a device (the test stream has audio). `none`: no sound card (-no-audio). `lab-mic`: a
  # microphone that hears only the lab's virtual source (docker/entrypoint.sh, LAB_MIC=1); refused
  # without a lab Pulse server, so the host's real microphone can never be the emulator's.
  audio="-no-audio"
  if [ "${EMULATOR_AUDIO:-silent}" = silent ]; then
    audio=""
    export QEMU_AUDIO_DRV=none
  fi
  if [ "${EMULATOR_AUDIO:-silent}" = lab-mic ]; then
    lab_pulse_ok || exit 1
    audio="-allow-host-audio"
    # No fallback to another server: libpulse looks for one in its runtime folder when the given one
    # fails, so point that at the lab's folder too, and switch autospawn off.
    export XDG_RUNTIME_DIR=/tmp/lab-pulse PULSE_RUNTIME_PATH=/tmp/lab-pulse
    printf 'autospawn = no\ndefault-server = %s\n' "$PULSE_SERVER" >/tmp/lab-pulse/client.conf
    export PULSE_CLIENTCONFIG=/tmp/lab-pulse/client.conf
  fi
  # EMULATOR_HW_DECODER=off (the default): no goldfish (host-backed) video decoders; the guest's
  # software Codec2 decoders take their place. The goldfish H.264 decoder discards WebRTC's frames
  # (0 decoded at 1280x720 and at 320x240), and the WebView has no fallback (10-11-2026).
  hwdec=""
  # EMULATOR_FEATURES: extra emulator features, space-separated, e.g. "-Vulkan" -> -feature -Vulkan.
  features=""
  for f in ${EMULATOR_FEATURES:-}; do features="$features -feature $f"; done
  [ "${EMULATOR_HW_DECODER:-off}" = off ] && hwdec="-feature -HardwareDecoder"
  # shellcheck disable=SC2086 # $vgl, $window, $audio, $hwdec and $features are optional words
  # EMULATOR_VGL=1: GLX through VirtualGL on the GPU (`-d egl`: its first EGL device, the render
  # node; docker/compose.gpu.yml). Without it the emulator's GLX ends on the X server's software GL.
  vgl=""
  # /opt/vglfix.so (docker/vglfix/vglfix.c) corrects VirtualGL's return code for three config
  # attributes; without it the emulator found no usable config (measured 10-11-2026).
  [ "${EMULATOR_VGL:-0}" = 1 ] && vgl="env VGL_PRELOAD=/opt/vglfix.so /opt/VirtualGL/bin/vglrun -d egl"
  # Keep the previous run's log: a crash is often only understood after the restart.
  [ -f "$OUT_DIR/emulator.log" ] && mv -f "$OUT_DIR/emulator.log" "$OUT_DIR/emulator.log.1"
  (cd "$SDK_DIR" && nohup $vgl ./emulator/emulator -avd "$AVD_NAME" -gpu "${EMULATOR_GPU:-swiftshader_indirect}" $features \
    -port "$EMULATOR_PORT" -no-snapshot-save $audio -no-boot-anim $window $hwdec \
    > "$OUT_DIR/emulator.log" 2>&1 &)
  booted=""
  for _ in $(seq 1 "${BOOT_TIMEOUT_STEPS:-90}"); do
    sleep 4
    if [ "$("$ADB" shell getprop sys.boot_completed </dev/null 2>/dev/null | tr -d '\r')" = 1 ]; then
      booted=1
      break
    fi
  done
  if [ -z "$booted" ]; then
    echo "the emulator did not finish booting within $(( ${BOOT_TIMEOUT_STEPS:-90} * 4 )) s; its log:" >&2
    tail -20 "$OUT_DIR/emulator.log" >&2
    exit 1
  fi
  echo "booted: $ANDROID_SERIAL"
  # The launcher is busy ("isn't responding") for a while after a software-GPU boot.
  sleep 30
fi

# WebView flags (read at each app start; this image is userdebug, which allows them). With the
# hardware decoder off, AllowMediaCodecSoftwareDecoder lets WebRTC use the guest's software H.264
# decoder: without it the WebView offers no H.264 at all (measured 10-11-2026).
if [ "${EMULATOR_HW_DECODER:-off}" = off ]; then
  "$ADB" shell "echo '_ --enable-features=AllowMediaCodecSoftwareDecoder' > /data/local/tmp/webview-command-line" </dev/null
else
  "$ADB" shell rm -f /data/local/tmp/webview-command-line </dev/null
fi
# APP_PIP=on|off (defaults.env: on, Android's default): picture-in-picture for the app. On, Home in
# fullscreen floats the video in a small window and the page is not hidden (measured 10-11-2026); off,
# the page is hidden, as on a real Pixel.
app_pip "$APP_PIP"
"$ADB" shell am force-stop "$PKG" </dev/null
# The app's login through localhost (a secure context, needed for the microphone) reaches the host
# through adb reverse, which does not survive an emulator restart: set it on every start.
# LAB_REVERSE_PORTS (default 8124, the lab's Home Assistant); empty for none.
for port in ${LAB_REVERSE_PORTS-8124}; do
  "$ADB" reverse "tcp:$port" "tcp:$port" </dev/null >/dev/null
done

launch_app
for _ in $(seq 1 30); do
  sleep 2
  pid=$(app_pid)
  [ -n "$pid" ] || continue
  # Captured, then searched (see above): the socket list is long, and a piped grep -q can make the
  # pipeline fail on SIGPIPE although the socket is there.
  sockets=$("$ADB" shell cat /proc/net/unix </dev/null 2>/dev/null || true)
  case "$sockets" in *"webview_devtools_remote_$pid"*) break ;; esac
done
[ -n "$(app_pid)" ] || { echo "the Companion app did not start" >&2; exit 1; }
forward_devtools
echo "device: $ANDROID_SERIAL (set ANDROID_SERIAL to this for later scripts if another device is attached)"
