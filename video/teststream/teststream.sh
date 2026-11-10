#!/bin/bash
# teststream.sh up|down|status: the test stream (compose.yml) with the lab's pinned
# MediaMTX image (LAB_MEDIAMTX_IMAGE in lab.env.example). TESTSTREAM_BIND as in the compose file.
set -euo pipefail
HERE=$(cd "$(dirname "$0")" && pwd)
. "$HERE/../../lib.sh"
export TESTSTREAM_BIND="${TESTSTREAM_BIND:-127.0.0.1}"
compose() { docker compose -f "$HERE/compose.yml" "$@"; }
case "${1:-}" in
  up) compose up -d ;;
  down) compose down ;;
  status) compose ps --format '{{.Name}} {{.State}}' ;;
  *) sed -n '2,3p' "$0"; exit 1 ;;
esac
