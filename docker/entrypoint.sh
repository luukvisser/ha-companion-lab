#!/bin/bash
# Entrypoint of the emulator container (docker/compose.yml): the same setup/ scripts as the host
# route, then keeps running until stopped. First start: downloads the SDK pieces, the system image
# and the app into the volumes (a few GB); later starts reuse them, and the app's login.
#
# VIEWER=1: the emulator draws into a virtual X display, shown in the browser through noVNC on
# 127.0.0.1:${VIEWER_PORT:-6080} (this machine only; the full URL, with its token, is written to
# /data/viewer-url). Otherwise headless.
set -euo pipefail
cd /lab

# A virtual X display for the emulator's window, reachable only inside this container. The container
# shares the host's network namespace (compose: network_mode host), and Xvfb's default abstract
# socket (@/tmp/.X11-unix/X<n>) lives in the network namespace: every host process could open it.
# So: no TCP, no abstract socket (`-nolisten local`), only the filesystem socket under this
# container's own /tmp, and a cookie (-auth) that only this container's processes read. Display
# numbers far above what a desktop uses, so no host display is ever met.
start_x() { # start_x <display number>
  local n=$1
  export DISPLAY=":$n" XAUTHORITY=/tmp/lab-x/auth
  mkdir -p /tmp/lab-x && chmod 700 /tmp/lab-x
  rm -f "$XAUTHORITY" && touch "$XAUTHORITY" && chmod 600 "$XAUTHORITY"
  xauth -q -f "$XAUTHORITY" add ":$n" . "$(mcookie)"
  # /tmp survives a restart of the same container: a stale lock or socket of the previous run makes
  # Xvfb refuse to start while the old socket file still looks like a display (measured 10-11-2026:
  # the emulator then aborted). Remove them first, and wait for this Xvfb process, not for a file.
  rm -f "/tmp/.X$n-lock" "/tmp/.X11-unix/X$n"
  Xvfb ":$n" -screen 0 720x1440x24 -nolisten tcp -nolisten local -auth "$XAUTHORITY" &
  local xpid=$!
  for _ in 1 2 3 4 5 6 7 8 9 10; do
    kill -0 "$xpid" 2>/dev/null || break
    [ -S "/tmp/.X11-unix/X$n" ] && [ -e "/tmp/.X$n-lock" ] && return 0
    sleep 0.5
  done
  echo "the virtual display :$n did not start" >&2
  exit 1
}

stop() {
  echo "stopping the emulator"
  setup/stop-emulator.sh || true
  sleep 3
  exit 0
}
trap stop TERM INT

# /tmp survives `docker compose stop` + `up` of the same container. The emulator's own temporary
# state and a previous run's display files then made the restarted emulator abort at start-up
# (measured 10-11-2026: a recreated container booted, a restarted one did not). This container's
# /tmp is its own (not the host's), so clear what a previous run left.
# The emulator's crash database first goes to the data volume (a crash is diagnosed after a restart).
for db in /tmp/android-*/emu-crash-*.db; do
  [ -s "$db" ] && mkdir -p /data/out/crash && cp -a "$db" "/data/out/crash/$(date +%Y%m%d-%H%M%S)-$(basename "$db")"
done
rm -rf /tmp/android-* /tmp/.X*-lock /tmp/.X11-unix/X* /tmp/lab-x /tmp/lab-vnc

setup/install-sdk.sh
[ -f "$HOME/.android/avd/${AVD_NAME:-ha-companion-lab}.ini" ] || setup/create-avd.sh

window=--no-window
if [ "${VIEWER:-0}" = 1 ]; then
  start_x 1287
  # Two guards in front of the emulator's screen, both in the data volume (mode 600, never printed
  # here; read them with `docker compose -f docker/compose.yml exec emulator cat /data/viewer-url`
  # and `... cat /data/viewer-password`):
  # - a token: x11vnc listens on no TCP port at all, only on a unix socket named after a random
  #   128-bit token, in a mode-700 folder of this container; websockify (on 127.0.0.1) connects a
  #   browser to it only when the URL carries that token. A page in a browser on this machine cannot
  #   guess it, so it cannot reach the VNC server (websockify itself has no origin check).
  # - a VNC password: VNC's own authentication uses only the first 8 characters of a password, so it
  #   is 8 random letters and digits (about 47 bits), not a longer value that would look stronger.
  pw=/data/viewer-password
  # Also made new when it is not 8 characters (a file from before this rule held 24).
  if [ "$(tr -d '\n' <"$pw" 2>/dev/null | wc -c)" -ne 8 ]; then
    (umask 077 && python3 -c 'import secrets, string; a = string.ascii_letters + string.digits; print("".join(secrets.choice(a) for _ in range(8)))' >"$pw")
  fi
  chmod 600 "$pw"
  token=$(python3 -c 'import secrets; print(secrets.token_hex(16))')
  rm -rf /tmp/lab-vnc && mkdir -m 700 /tmp/lab-vnc
  (umask 077 && echo "http://127.0.0.1:${VIEWER_PORT:-6080}/vnc.html?path=websockify%3Ftoken%3D$token" >/data/viewer-url)
  # -passwdfile reads the password from the file (not the command line).
  # No TCP listener at all: -rfbport 0 switches off IPv4, but this x11vnc build listens on IPv6 by
  # default and still opened [::]:5900 (every interface, LAN included; measured 10-11-2026). Only
  # -rfbportv6 -1 together with -no6/-noipv6 left no TCP listener at all (each variant measured in
  # a throwaway container). No -localhost: it allows only 127.0.0.1 and so refused the unix
  # socket's clients (they have no address), which left the viewer unusable.
  x11vnc -display "$DISPLAY" -auth "$XAUTHORITY" -rfbport 0 -rfbportv6 -1 -no6 -noipv6 \
    -unixsock "/tmp/lab-vnc/$token" -passwdfile "$pw" -forever -shared -quiet &
  websockify --web /usr/share/novnc --token-plugin UnixDomainSocketDirectory \
    --token-source /tmp/lab-vnc "127.0.0.1:${VIEWER_PORT:-6080}" &
  window=
  echo "viewer: on 127.0.0.1:${VIEWER_PORT:-6080}; its URL with the token is in /data/viewer-url"
fi

# LAB_MIC=1: a microphone for talk tests that hears only a known test tone. A Pulse server private
# to this container (no host audio socket or /dev/snd is mounted): its default source "labmic" is a
# pipe fed in real time by setup/feed-tone.py with a 1 kHz tone, 2 s on and 1 s off, at -20 dBFS
# peak (-23 dBFS RMS while on). The emulator gets this server only (start-emulator.sh refuses any
# other), so the host's real microphone can never reach it.
if [ "${LAB_MIC:-0}" = 1 ]; then
  # A clean state on every start: /tmp survives a restart of the same container, and a stale
  # mic.fifo kept module-pipe-source from loading (Android then recorded the null sink's silence).
  # The folder is made new and private (mode 700) on every run, with a run id that
  # start-emulator.sh checks, so the emulator can only ever use this run's server.
  rm -rf /tmp/lab-pulse /tmp/pulse
  mkdir -m 700 /tmp/lab-pulse /tmp/pulse
  LAB_PULSE_RUN=$(python3 -c 'import secrets; print(secrets.token_hex(8))')
  (umask 077 && echo "$LAB_PULSE_RUN" >/tmp/lab-pulse/run-id)
  export LAB_PULSE_RUN
  # module-pipe-source creates the FIFO itself and refuses an existing path (PulseAudio 16.1).
  # The server also listens on libpulse's default socket for XDG_RUNTIME_DIR=/tmp, so a client
  # that does not read PULSE_SERVER finds it too.
  pulseaudio --daemonize=yes --exit-idle-time=-1 --disallow-exit -n \
    --load="module-pipe-source source_name=labmic file=/tmp/lab-pulse/mic.fifo format=s16le rate=48000 channels=1" \
    --load="module-null-sink sink_name=labsink" \
    --load="module-native-protocol-unix socket=/tmp/lab-pulse/native auth-anonymous=1" \
    --load="module-native-protocol-unix socket=/tmp/pulse/native auth-anonymous=1" \
    --log-target=file:/tmp/lab-pulse/pulseaudio.log ||
    { echo "lab microphone: pulseaudio did not start; its log:" >&2; tail -20 /tmp/lab-pulse/pulseaudio.log >&2 || true; exit 1; }
  export PULSE_SERVER=unix:/tmp/lab-pulse/native EMULATOR_AUDIO=lab-mic XDG_RUNTIME_DIR=/tmp
  for _ in 1 2 3 4 5; do pactl info >/dev/null 2>&1 && break; sleep 1; done
  if ! pactl list short sources | grep -q '\blabmic\b'; then
    echo "lab microphone: the labmic source did not load; refusing to start with a silent microphone" >&2
    exit 1
  fi
  pactl set-default-source labmic && pactl set-default-sink labsink
  python3 setup/feed-tone.py /tmp/lab-pulse/mic.fifo 1000 2.0 1.0 -20 &
  # The headless emulator build (`-no-window` runs qemu-system-*-headless) has no Pulse support at
  # all ("Could not init `pa' audio driver"); only the windowed build links libpulse. So the
  # microphone needs a window: an invisible virtual display when the viewer is off.
  if [ -n "$window" ]; then
    start_x 1286
    window=
  fi
  # The emulator's own sound (what the app plays) ends in labsink: record it with
  # `parecord -d labsink.monitor` inside the container (video/tools/av-delay.sh does).
  echo "lab microphone: 1 kHz tone (2 s on, 1 s off, -20 dBFS), the emulator's only audio source; output to labsink"
fi

# EMULATOR_VGL=1 (docker/compose.gpu.yml): the emulator's GL renderer uses GLX, which needs an X
# display; VirtualGL (start-emulator.sh) renders that GLX on the GPU's render node. A display of
# its own when no other one runs; the emulator itself stays headless.
if [ "${EMULATOR_VGL:-0}" = 1 ] && [ -z "${DISPLAY:-}" ]; then
  start_x 1285
fi

# The first boot has no app yet: start-emulator.sh then fails at launching it, which is fine here.
setup/start-emulator.sh $window || true
. ./lib.sh
if ! "$ADB" shell pm path "$PKG" </dev/null 2>/dev/null | grep -q package:; then
  setup/get-companion-apk.sh
fi
setup/start-emulator.sh $window
echo "ready: adb on 127.0.0.1:5037, the app's DevTools on 127.0.0.1:$CDP_PORT"

# Stay up; `docker compose stop` sends TERM, which stops the emulator cleanly.
while sleep 5; do
  "$ADB" get-state </dev/null >/dev/null 2>&1 || { echo "the emulator is gone"; exit 1; }
done
