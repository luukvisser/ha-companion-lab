#!/bin/bash
# devcontainer-bridge.sh up|down|status: relays from the Docker bridge address to the lab's
# loopback-only ports, so a devcontainer (or any container on the default bridge) can reach the
# adb server, the app's DevTools and the isolated test Home Assistant without host networking.
#
# The relays listen on the Docker bridge's address (e.g. 172.17.0.1) and accept connections only
# from the bridge's own subnet (socat `range=`): a LAN host that routes to that address, or a
# container on another Docker network, is refused. Any container on the default bridge can use them
# while they run (the adb server has no login): stop them when done.
# In the devcontainer: runArgs --add-host=host.docker.internal:host-gateway, then use
# host.docker.internal:<relay port>. See README "Using the lab from a devcontainer".
set -euo pipefail
. "$(dirname "$0")/../lib.sh"

SOCAT_IMAGE="${SOCAT_IMAGE:-alpine/socat:1.8.1.1@sha256:7f9a06753033f2b7de18edc2353f2c15153413d95a039163c6db270fc7a6c3b0}"
BRIDGE_IP="${BRIDGE_IP:-$(docker network inspect bridge --format '{{(index .IPAM.Config 0).Gateway}}')}"
BRIDGE_SUBNET="${BRIDGE_SUBNET:-$(docker network inspect bridge --format '{{(index .IPAM.Config 0).Subnet}}')}"
# name local-port relay-port
RELAYS="adb 5037 ${RELAY_ADB_PORT:-15037}
cdp ${CDP_PORT:-9333} ${RELAY_CDP_PORT:-19333}
ha ${LAB_HA_PORT:-8124} ${RELAY_HA_PORT:-18124}"

case "${1:-status}" in
  up)
    [ -n "$BRIDGE_IP" ] && [ -n "$BRIDGE_SUBNET" ] || { echo "no Docker bridge address or subnet found" >&2; exit 1; }
    while read -r name port relay; do
      docker rm -f "lab-bridge-$name" >/dev/null 2>&1 || true
      docker run -d --name "lab-bridge-$name" --network host --restart no --cap-drop ALL \
        --security-opt no-new-privileges "$SOCAT_IMAGE" \
        "TCP-LISTEN:$relay,bind=$BRIDGE_IP,range=$BRIDGE_SUBNET,fork,reuseaddr" "TCP:127.0.0.1:$port" >/dev/null
      echo "$name: host.docker.internal:$relay (listens on $BRIDGE_IP:$relay, only for $BRIDGE_SUBNET) -> 127.0.0.1:$port"
    done <<< "$RELAYS"
    ;;
  down)
    while read -r name _ _; do docker rm -f "lab-bridge-$name" >/dev/null 2>&1 || true; done <<< "$RELAYS"
    echo "relays stopped"
    ;;
  status)
    docker ps --filter name=lab-bridge- --format '{{.Names}} {{.Status}}'
    ;;
  *)
    echo "usage: $0 up|down|status" >&2; exit 2 ;;
esac
