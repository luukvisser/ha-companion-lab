#!/bin/bash
# netem.sh: make the test stack's network slow, lossy or absent, to measure dropouts.
#
#   netem.sh delay <ms> [jitter ms] [target]  add latency (and jitter) to the target's traffic
#   netem.sh loss <percent> [target]          drop that share of the target's packets
#   netem.sh rate <kbit> [target]             limit the target's outgoing bandwidth
#   netem.sh show [target]                    the target's current shaping
#   netem.sh clear [target]                   remove all shaping
#   netem.sh cut [target]                     disconnect the target from the stack network
#   netem.sh restore [target]                 connect it again (same address)
#
# target: a service of the stack (homeassistant or ha, fake-tuya, go2rtc, teststream, proxy,
# bridge), default `bridge` (the simulated camera side). Shaping is applied
# with `tc` inside the target's own network namespace, from a short-lived helper container with
# NET_ADMIN; nothing on this machine's own network changes. It shapes the target's outgoing
# traffic (for the bridge: the media towards go2rtc and HA). Scenarios: see README.md.
set -euo pipefail
HERE=$(cd "$(dirname "$0")" && pwd)
. "$HERE/../lib.sh"
export LAB_HA_DATA
IMAGE=ha-companion-lab-ha:2026.11.0
NET=ha-companion-lab-stack_lab

# A target is a service of compose.yml (homeassistant, fake-tuya, go2rtc, teststream, proxy,
# bridge); `ha` is short for homeassistant. Container names come from compose.yml itself, so a
# service whose container is named differently (homeassistant: lab-ha) is still found.
service() { case "${1:-bridge}" in ha) echo homeassistant ;; *) echo "${1:-bridge}" ;; esac; }
compose_json() { docker compose -f "$HERE/compose.yml" --profile bridge config --format json; }
container() {
  local svc
  svc=$(service "$1")
  compose_json | python3 -c '
import json, sys
services = json.load(sys.stdin)["services"]
name = sys.argv[1]
if name not in services:
    sys.exit("unknown target %s (services: %s)" % (name, ", ".join(sorted(services))))
print(services[name].get("container_name") or name)' "$svc"
}

# Run a command in the target's network namespace, with NET_ADMIN, in a short-lived helper.
in_ns() {
  local target=$1 name
  shift
  name=$(container "$target") || exit 1
  docker run --rm --network "container:$name" --cap-add NET_ADMIN \
    --entrypoint "$1" "$IMAGE" "${@:2}"
}

# The target's interface on the stack network (a service on two networks has two).
lab_if() {
  in_ns "$1" ip -o -4 addr show | awk '$4 ~ /^172\.31\.240\./ {print $2; exit}'
}

tc_in() {
  local target=$1 dev
  shift
  dev=$(lab_if "$target")
  [ -n "$dev" ] || { echo "$target has no interface on the stack network" >&2; exit 1; }
  in_ns "$target" tc "${@//IFACE/$dev}"
}

cmd=${1:-}
case "$cmd" in
  delay)
    ms=${2:?delay in ms}; jitter=${3:-0}; target=${4:-bridge}
    tc_in "$target" qdisc replace dev IFACE root netem delay "${ms}ms" "${jitter}ms"
    echo "$target: +${ms} ms (jitter ${jitter} ms)" ;;
  loss)
    pct=${2:?loss in percent}; target=${3:-bridge}
    tc_in "$target" qdisc replace dev IFACE root netem loss "${pct}%"
    echo "$target: ${pct}% loss" ;;
  rate)
    kbit=${2:?rate in kbit/s}; target=${3:-bridge}
    tc_in "$target" qdisc replace dev IFACE root tbf rate "${kbit}kbit" burst 32kbit latency 400ms
    echo "$target: limited to ${kbit} kbit/s" ;;
  show) tc_in "${2:-bridge}" qdisc show dev IFACE ;;
  clear)
    tc_in "${2:-bridge}" qdisc del dev IFACE root 2>/dev/null || true
    echo "${2:-bridge}: no shaping" ;;
  cut)
    name=$(container "${2:-bridge}") || exit 1
    docker network disconnect "$NET" "$name"
    echo "${2:-bridge}: disconnected" ;;
  restore)
    target=${2:-bridge}
    ip=$(compose_json | python3 -c "import json,sys; s=json.load(sys.stdin)['services'][sys.argv[1]]['networks']['lab']; print((s or {}).get('ipv4_address',''))" "$(service "$target")")
    name=$(container "$target") || exit 1
    docker network connect ${ip:+--ip "$ip"} "$NET" "$name"
    echo "$target: connected again${ip:+ at $ip}" ;;
  *) sed -n '2,16p' "$0" ;;
esac
