#!/bin/bash
# stack.sh: the lab's own Home Assistant, a throwaway test HA (see README.md). `./lab up` runs it.
#
#   stack.sh up [--bridge]   build, start and set up: HA onboarded, go2rtc, the synthetic test
#                            stream, the lab's limited test user, the test camera
#                            (camera.test_pattern) and the test dashboard. With the Avent add-on
#                            (LAB_AVENT, default: on when an aventproxy checkout is present) also a
#                            fake Tuya API and the Avent integration; --bridge adds its simulated
#                            bridge (image avent-bridge:sim, built from aventproxy separately)
#   stack.sh down            stop and remove the containers (the data folder stays)
#   stack.sh reset           down, then delete the data folder (asks first)
#   stack.sh card <build>    installs card build $BUILDS_DIR/<build> into this stack's HA
#                                (served under CARD_PREFIX like a HACS install) and points the
#                                dashboard resource at it: then measure with the variant
#                                `deployed`, no interception needed
#   stack.sh status          containers, the URLs, the camera entity
#   stack.sh dps [json]      the simulated monitor's data points; with JSON, merge them
#                                (e.g. '{"207": 2450}' for 24.5 C)
#   stack.sh logs [service]  follow a service's log (homeassistant, fake-tuya, go2rtc, bridge)
#   stack.sh talk            what the simulated bridge received as talk-back, per session:
#                                duration, level, dominant frequency, share of the lab's 1 kHz tone
#                                (sim_talk.py; needs `up --bridge`)
#   stack.sh lan [34|33] <command>   the fake LAN monitors (LAB_AVENT_LAN=on; lan_monitor.py):
#                                state | push '<json>' | fault silent|refuse|close|normal |
#                                version 3.3|3.4|3.5 | discovery on|off | ip <172.31.240.x>;
#                                `stack.sh lan selftest` runs lan_monitor.py's self-test
#
# Nothing here touches another stack: own networks (one of them internal), own ports on
# 127.0.0.1, own data folder ($LAB_HA_DATA). Credentials live only in that folder, mode 600.
set -euo pipefail
HERE=$(cd "$(dirname "$0")" && pwd)
. "$HERE/../lib.sh"
export LAB_HA_DATA LAB_HA_PORT LAB_WEBRTC_PORT AVENT_LAB_SIM_SOURCE AVENT_LAB_CAMERA_NAME
export AVENT_LAB_LAN_DISCOVERY AVENT_LAB_LAN_34_VERSION AVENT_LAB_LAN_33_VERSION AVENT_LAB_LAN_33_QUERY
IMAGE=ha-companion-lab-ha:2026.11.0
HA_LOCAL="http://127.0.0.1:$LAB_HA_PORT"
# The Avent add-on: LAB_AVENT=on|off, or auto (on when the aventproxy checkout is there).
avent_on() {
  case "${LAB_AVENT:-auto}" in
    on) return 0 ;;
    off) return 1 ;;
    *) [ -d "$AVENT_INTEGRATION_SRC/custom_components/philips_avent" ] ;;
  esac
}
# The fake LAN monitors (compose.avent-lan.yml): LAB_AVENT_LAN=on, on top of the Avent add-on.
lan_on() { [ "${LAB_AVENT_LAN:-off}" = on ] && avent_on; }
compose() {
  if lan_on; then
    docker compose -f "$HERE/compose.yml" -f "$HERE/compose.avent.yml" -f "$HERE/compose.avent-lan.yml" "$@"
  elif avent_on; then
    docker compose -f "$HERE/compose.yml" -f "$HERE/compose.avent.yml" "$@"
  else
    docker compose -f "$HERE/compose.yml" "$@"
  fi
}

# Every write to Home Assistant from here must reach this stack's HA and nothing else: the port
# must be the one this stack's own proxy publishes on 127.0.0.1. (lab.env cannot redirect HA_URL
# for the scripts below either: they get it pinned through LAB_PIN_*, see lib.sh.)
# Runs a core script pinned to this stack (all three LAB_PIN_*; lib.sh refuses a partial pin).
stack_env() {
  env LAB_PIN_HA_URL="$HA_LOCAL" LAB_PIN_HA_TOKEN_FILE="$LAB_HA_DATA/token" \
    LAB_PIN_TEST_USER_PASSWORD_FILE="$LAB_HA_DATA/test-user-password" "$@"
}

assert_stack_target() {
  local published
  # `|| true`: with the stack down, docker port fails, and set -e would end here without a word.
  published=$(docker port lab-proxy 8123/tcp 2>/dev/null | head -1 || true)
  if [ "$published" != "127.0.0.1:$LAB_HA_PORT" ]; then
    echo "refusing: $HA_LOCAL is not this stack's proxy (lab-proxy publishes '${published:-nothing}')" >&2
    exit 1
  fi
}

copy_integration() {
  # Third-party code (aventproxy, MIT): copied into the data folder, never into the repository.
  local dest="$LAB_HA_DATA/avent-integration"
  if [ ! -d "$AVENT_INTEGRATION_SRC/custom_components/philips_avent" ]; then
    echo "no aventproxy checkout at AVENT_INTEGRATION_SRC ($AVENT_INTEGRATION_SRC): clone" \
      "https://github.com/thekoma/aventproxy there, or set AVENT_INTEGRATION_SRC in lab.env" >&2
    exit 1
  fi
  # Replace the contents, keep the folder: a running HA keeps its bind mount of it.
  mkdir -p "$dest/philips_avent"
  find "$dest/philips_avent" -mindepth 1 -delete
  if [ "$AVENT_INTEGRATION_REF" = WORKTREE ]; then
    cp -r "$AVENT_INTEGRATION_SRC/custom_components/philips_avent/." "$dest/philips_avent/"
  else
    git -C "$AVENT_INTEGRATION_SRC" archive "$AVENT_INTEGRATION_REF" custom_components/philips_avent |
      tar -x -C "$dest" --strip-components=1
  fi
  echo "integration: $(python3 -c "import json,sys; print(json.load(open(sys.argv[1]))['version'])" \
    "$dest/philips_avent/manifest.json") from $AVENT_INTEGRATION_SRC ($AVENT_INTEGRATION_REF)"
}

# Outbound firewall for every stack container, loaded into its own network namespace by a one-shot
# helper (NET_ADMIN only there, never on the host): a container may talk to loopback, to the stack's
# internal network (not its gateway, which is this machine), and answer connections made to it (the
# published HA and WebRTC ports). Anything else it starts is dropped: the internet, this machine's
# own addresses (LAN, Docker gateways) and with them every other service on it, e.g. a production
# Home Assistant or go2rtc. The `edge` network has no NAT either (compose.yml), as a second layer.
# The add + delete first make a second run replace the table instead of stacking the rules twice.
LOCKDOWN_RULES='
add table inet lab_lockdown
delete table inet lab_lockdown
table inet lab_lockdown {
  chain output {
    type filter hook output priority filter; policy drop;
    oif "lo" accept
    ct state established,related accept
    ip daddr 172.31.240.1 drop
    ip daddr 172.31.240.0/24 accept
  }
}'
lockdown() {
  local c n=0
  for c in $(compose --profile bridge ps -q); do
    printf '%s\n' "$LOCKDOWN_RULES" | docker run --rm -i --network "container:$c" --cap-add NET_ADMIN \
      --entrypoint nft "$IMAGE" -f - || { echo "lockdown of $c failed" >&2; exit 1; }
    n=$((n + 1))
  done
  echo "lockdown: outbound limited to the stack's own network in $n containers"
}

# The fake LAN monitors' made-up ids, names and local keys, written once (keys stay the same across
# restarts, as a real monitor's do until the cloud rotates them). Mode 600; never printed.
lan_keys() {
  local f="$LAB_HA_DATA/lan/monitors.json"
  mkdir -p "$LAB_HA_DATA/lan"
  [ -s "$f" ] && return 0
  (umask 077 && python3 -I -c '
import json, secrets, string, sys
alphabet = string.ascii_letters + string.digits
key = lambda: "".join(secrets.choice(alphabet) for _ in range(16))
json.dump({"monitors": [
    {"id": "labavent000000000001", "name": sys.argv[2], "product": "labproduct000000", "key": key()},
    {"id": "labavent000000000002", "name": "Lab second monitor", "product": "labproduct000002", "key": key()},
]}, open(sys.argv[1], "w"), indent=1)' "$f.tmp" "$AVENT_LAB_CAMERA_NAME" && mv "$f.tmp" "$f")
  echo "fake LAN monitors: made-up local keys written to $f"
}

first_config() {
  local cfg="$LAB_HA_DATA/ha/configuration.yaml"
  [ -e "$cfg" ] && return 0
  cat >"$cfg" <<'YAML'
# The lab's own Home Assistant (written once by stack.sh).
default_config:

# The stack's own go2rtc (WebRTC), as in a setup with an external go2rtc.
go2rtc:
  url: http://172.31.240.4:1984

logger:
  default: info
  logs:
    custom_components.philips_avent: debug
YAML
}

up() {
  local bridge=""
  [ "${1:-}" = --bridge ] && bridge=1
  # www/ before HA starts: HA serves /local/ (a card build, `card`) only if it exists at start-up.
  mkdir -p "$LAB_HA_DATA/ha/www" "$LAB_HA_DATA/certs"
  chmod 700 "$LAB_HA_DATA"
  local avent="" certs=""
  avent_on && avent=1
  [ -n "$avent" ] && copy_integration
  if [ "${LAB_AVENT_LAN:-off}" = on ] && [ -z "$avent" ]; then
    echo "LAB_AVENT_LAN=on needs the Avent add-on (an aventproxy checkout, or LAB_AVENT=on)" >&2; exit 1
  fi
  lan_on && lan_keys
  # Built by the Docker daemon: `nice` on this command would not lower the build itself.
  docker compose -f "$HERE/compose.yml" build -q homeassistant
  if [ -n "$avent" ]; then
    certs=$(docker run --rm --network none -u "$(id -u):$(id -g)" -v "$LAB_HA_DATA/certs:/out" \
      -v "$HERE/certs.py:/app/certs.py:ro" --entrypoint python3 "$IMAGE" -I /app/certs.py /out)
    echo "$certs"
  fi
  first_config
  if [ -n "$bridge" ] && [ -z "$avent" ]; then
    echo "--bridge needs the Avent add-on (an aventproxy checkout, or LAB_AVENT=on)" >&2; exit 1
  fi
  if [ -n "$bridge" ]; then
    docker image inspect avent-bridge:sim >/dev/null 2>&1 ||
      { echo "no image avent-bridge:sim: build aventproxy's simulation mode first" >&2; exit 1; }
    compose --profile bridge up -d
  else
    compose up -d
  fi
  # Renewed certificates are read only at start: restart what reads them.
  case "$certs" in *"certificates renewed"*) compose up -d --force-recreate homeassistant fake-tuya ;; esac
  # Right after start, before onboarding: until then nothing in the stack has been told to connect
  # anywhere (a window of a few seconds; documented in the README).
  lockdown
  assert_stack_target
  docker run --rm --network host -u "$(id -u):$(id -g)" -v "$LAB_HA_DATA:/data" \
    -v "$HERE/onboard.py:/app/onboard.py:ro" --entrypoint python3 "$IMAGE" -I /app/onboard.py \
    "$HA_LOCAL" 172.31.240.2 38554 ${avent:+avent}
  docker image inspect ha-companion-lab-py >/dev/null 2>&1 ||
    docker build -q -t ha-companion-lab-py "$LAB_ROOT/tools/cdp" >/dev/null
  stack_env "$LAB_ROOT/setup/ha-test-user.sh" create
  # The generic test camera on the synthetic stream, and the test dashboard on it. (With the Avent
  # add-on its simulated camera is there too: `video/ha-setup.sh dashboard` points the card at it.)
  stack_env "$LAB_ROOT/video/ha-setup.sh" camera "$LAB_DEFAULT_STREAM"
  # The Advanced Camera Card once a build is installed (`stack.sh card`, `lab card`); before that Home
  # Assistant's own camera card, live, so a fresh lab shows the stream at once.
  if docker run --rm -v "$LAB_HA_DATA/ha:/config:ro" --entrypoint sh "$IMAGE" -c \
      "test -f /config/www/${CARD_PREFIX#/local/}advanced-camera-card.js"; then
    stack_env "$LAB_ROOT/video/ha-setup.sh" dashboard '{"camera_entity":"camera.test_pattern","live_provider":"ha"}'
  else
    stack_env "$LAB_ROOT/video/ha-setup.sh" dashboard-card \
      '{"type":"picture-entity","entity":"camera.test_pattern","camera_view":"live","show_state":false}'
  fi

  # The camera's two-way audio is a Labs preview in Home Assistant 2026.11: without it the card's
  # `ha` provider offers no call. Switched on here so a fresh stack needs no step by hand.
  stack_env "$LAB_ROOT/video/ha-setup.sh" labs camera two_way_audio on | grep '^camera\.' || true
  status
}

card() {
  local build=${1:?usage: stack.sh card <build name under $BUILDS_DIR>}
  local src="$BUILDS_DIR/$build"
  [ -f "$src/advanced-camera-card.js" ] || { echo "no card build at $src" >&2; exit 1; }
  # A folder below /local/ (the config folder's www/): plain path segments only, so it can never
  # point at www/ itself, its parent or anything outside it (the copy below empties it as root).
  # Matched as a whole value with [[ =~ ]] (grep would match per line, so a value with a newline
  # passed when any one line was valid).
  local prefix_re='^/local/[A-Za-z0-9_-]+(/[A-Za-z0-9_-]+)*/$'
  if [[ "$CARD_PREFIX" == *$'\n'* ]] || ! [[ "$CARD_PREFIX" =~ $prefix_re ]]; then
    echo "CARD_PREFIX ($CARD_PREFIX) must be /local/<folder>/ with plain path segments" >&2; exit 1
  fi
  local rel=${CARD_PREFIX#/local/}
  assert_stack_target
  # HA owns parts of the config folder as root, so copy through a container. The folder goes in as
  # an argument (never spliced into the script) and is checked again after resolving.
  docker run --rm -v "$LAB_HA_DATA/ha:/config" -v "$src:/src:ro" --entrypoint sh "$IMAGE" -c '
    set -eu
    d=$(python3 -c "import os, sys; print(os.path.realpath(os.path.join(*sys.argv[1:])))" /config/www "$1")
    case "$d" in
      /config/www/?*) ;;
      *) echo "refusing: $d is not below /config/www/" >&2; exit 1 ;;
    esac
    mkdir -p "$d"
    find "$d" -mindepth 1 -delete
    cp -r /src/. "$d/"
  ' sh "${rel%/}"
  local stamp
  stamp=$(date +%s)
  stack_env "$LAB_ROOT/video/ha-setup.sh" resource "${CARD_PREFIX}advanced-camera-card.js?v=$stamp"
  mkdir -p "$LAB_STATE_DIR" && printf '%s\n' "$build" >"$LAB_STATE_DIR/card-build"
  echo "card build '$build' installed; measure it as the variant 'deployed' (reload the app's page)"
}

# Docker gives a container a new network namespace when it restarts, so `docker restart` (or a
# recreate) silently drops its lockdown rules: status checks every running container for them.
status() {
  compose --profile bridge ps --format '{{.Name}} {{.State}}' 2>/dev/null || true
  local c missing=""
  for c in $(compose --profile bridge ps -q 2>/dev/null); do
    docker run --rm --network "container:$c" --cap-add NET_ADMIN --entrypoint nft "$IMAGE" \
      list table inet lab_lockdown >/dev/null 2>&1 ||
      missing="$missing $(docker inspect -f '{{.Name}}' "$c" | tr -d /)"
  done
  if [ -n "$missing" ]; then
    echo "WARNING: no lockdown in:$missing (restarted or recreated?); run: stack.sh lockdown" >&2
  else
    echo "lockdown: loaded in every running container"
  fi
  echo "Home Assistant: $HA_LOCAL (from the emulator: http://localhost:$LAB_HA_PORT, adb reverse)"
  echo "test dashboard: $TEST_PATH; test camera: camera.test_pattern; Avent add-on: $(avent_on && echo "on, camera $(cat "$LAB_HA_DATA/camera-entity" 2>/dev/null || echo -)" || echo off)"
  if lan_on; then
    echo "fake LAN monitors: lab-lan-34 (172.31.240.30), lab-lan-33 (172.31.240.31) unless moved with stack.sh lan ip; stack.sh lan [34|33] state"
  fi
  echo "credentials and token: $LAB_HA_DATA (mode 600; never printed)"
}

# The fake LAN monitors' control endpoint (lan_monitor.py), reached from inside the container.
lan_call() { # lan_call <container> <action> [json]
  docker exec "$1" python3 -I -c '
import json, sys, urllib.error, urllib.request
url = "http://127.0.0.1:8080/lab/" + sys.argv[1]
r = urllib.request.Request(url, data=sys.argv[2].encode() if len(sys.argv) > 2 else None,
                           headers={"Content-Type": "application/json"})
try:
    print(json.dumps(json.load(urllib.request.urlopen(r)), indent=1))
except urllib.error.HTTPError as e:
    sys.exit("refused: %s" % e.read().decode())
except urllib.error.URLError as e:
    sys.exit("not reachable: %s" % e.reason)' "${@:2}"
}

lan() {
  if [ "${1:-}" = selftest ]; then
    docker run --rm --name lab-lan-selftest --network none --cpus 2 --memory 2g \
      -v "$HERE/lan_monitor.py:/app/lan_monitor.py:ro" --entrypoint python3 "$IMAGE" -I /app/lan_monitor.py --self-test
    return
  fi
  local which=34
  case "${1:-}" in 34 | 33) which=$1; shift ;; esac
  local c="lab-lan-$which" cmd=${1:-state}
  docker ps --format '{{.Names}}' | grep -qx "$c" ||
    { echo "$c is not running (LAB_AVENT_LAN=on stack.sh up)" >&2; exit 1; }
  case "$cmd" in
    state) lan_call "$c" state ;;
    push) lan_call "$c" dps "${2:?usage: stack.sh lan [34|33] push '<json>'}" ;;
    fault) lan_call "$c" fault "{\"fault\": \"${2:?silent, refuse, close or normal}\"}" ;;
    version) lan_call "$c" version "{\"version\": \"${2:?3.3, 3.4 or 3.5}\"}" ;;
    discovery)
      case "${2:-}" in on) lan_call "$c" discovery '{"on": true}' ;; off) lan_call "$c" discovery '{"on": false}' ;;
        *) echo "usage: stack.sh lan [34|33] discovery on|off" >&2; exit 1 ;; esac ;;
    ip)
      # The monitor restarts on another address, as after a new DHCP lease: it leaves the network
      # first, so its sessions end without a word to the client (as a camera that reboots), then
      # comes back with the new address, which its broadcasts announce. The container keeps its
      # network namespace, so its lockdown stays. Back: `ip` with its own address (.30 or .31).
      local ip=${2:?usage: stack.sh lan [34|33] ip 172.31.240.<n>}
      [[ "$ip" =~ ^172\.31\.240\.([0-9]+)$ ]] && [ "${BASH_REMATCH[1]}" -ge 30 ] && [ "${BASH_REMATCH[1]}" -le 250 ] ||
        { echo "the new address must be 172.31.240.30-250 (lower ones belong to the stack)" >&2; exit 1; }
      local net=ha-companion-lab-stack_lab old
      old=$(docker inspect -f '{{with index .NetworkSettings.Networks "ha-companion-lab-stack_lab"}}{{.IPAddress}}{{end}}' "$c")
      [ "$old" = "$ip" ] && { echo "$c: already at $ip"; return; }
      [ -n "$old" ] && docker network disconnect "$net" "$c"
      lan_call "$c" fault '{"fault": "close"}' >/dev/null
      if ! docker network connect --ip "$ip" "$net" "$c"; then
        # Address taken (the other monitor's, say): back where it was, so the monitor is not lost.
        [ -n "$old" ] && docker network connect --ip "$old" "$net" "$c"
        echo "$c: could not take $ip; back at ${old:-no address}" >&2; exit 1
      fi
      echo "$c: now at $ip" ;;
    *) sed -n '/^#   stack.sh lan /,/^#.*selftest/p' "$0" ;;
  esac
}

dps() {
  local body=${1:-}
  if [ -n "$body" ]; then
    docker exec lab-fake-tuya python3 -I -c "
import json, sys, urllib.request
r = urllib.request.Request('http://127.0.0.1:8080/lab/dps', data=sys.argv[1].encode(), method='POST',
                           headers={'Content-Type': 'application/json'})
print(urllib.request.urlopen(r).read().decode())" "$body"
  else
    docker exec lab-fake-tuya python3 -I -c "
import urllib.request; print(urllib.request.urlopen('http://127.0.0.1:8080/lab/dps').read().decode())"
  fi
}

reset() {
  read -r -p "Delete the stack and $LAB_HA_DATA (HA config, token, passwords)? Type yes: " answer
  [ "$answer" = yes ] || { echo "kept"; return; }
  # --remove-orphans: also the fake LAN monitors when LAB_AVENT_LAN is off by now (their bind mount
  # is in the folder deleted below).
  compose --profile bridge down -v --remove-orphans
  # Home Assistant writes as root; delete through a container, limited to this one folder.
  docker run --rm -v "$LAB_HA_DATA:/d" --entrypoint find "$IMAGE" /d -mindepth 1 -delete
  rmdir "$LAB_HA_DATA"
  echo "reset: containers and $LAB_HA_DATA removed"
}

talk() {
  docker ps --format '{{.Names}}' | grep -q '^lab-bridge$' ||
    { echo "the simulated bridge is not running (stack.sh up --bridge)" >&2; exit 1; }
  local tmp f
  tmp=$(mktemp -d)
  chmod 700 "$tmp"
  # The bridge's /tmp/talk is a tmpfs in a read-only container: copy the files out, read-only.
  for f in $(docker exec lab-bridge sh -c 'ls /tmp/talk 2>/dev/null' || true); do
    case "$f" in *-talk.ulaw | *-talk.sessions) docker exec lab-bridge cat "/tmp/talk/$f" >"$tmp/$f" ;; esac
  done
  set -- "$tmp"/*-talk.sessions
  [ -e "$1" ] || { echo "no talk sessions recorded yet"; rm -rf "$tmp"; return 0; }
  for f in "$@"; do
    id=$(basename "$f" -talk.sessions)
    echo "== $id"
    python3 -I "$LAB_ROOT/stack/sim_talk.py" "$tmp" "$id"
  done
  rm -rf "$tmp"
}

case "${1:-}" in
  up) up "${2:-}" ;;
  # --remove-orphans: also the fake LAN monitors when LAB_AVENT_LAN is off by now.
  down) compose --profile bridge down --remove-orphans ;;
  reset) reset ;;
  card) card "${2:-}" ;;
  status) status ;;
  lockdown) lockdown ;;
  dps) dps "${2:-}" ;;
  logs) compose --profile bridge logs -f "${2:-homeassistant}" ;;
  talk) talk ;;
  lan) shift; lan "$@" ;;
  *) awk 'NR > 1 && /^# Nothing here/ { exit } NR > 1' "$0" ;;
esac
