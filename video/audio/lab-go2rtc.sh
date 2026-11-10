#!/bin/bash
# lab-go2rtc.sh up|down|tone <stream>|check <stream>|status: the lab go2rtc for talk-back tests.
#
#   up              makes the talk-test tone (once, $LAB_AUDIO_DATA), then starts the lab go2rtc and
#                   its own test stream on the internal network `lab-audio`
#   down            stops and removes both
#   tone <stream>   plays the 4 s 1 kHz test tone (-24 dB) into <stream>'s speaker (doorbell or baby)
#   check <stream>  what that camera last heard (check-talk.sh)
#   status          whether it runs, and that its API answers only inside the container
#
# The API has no port anywhere outside the container (go2rtc.yaml): this script talks to it with
# `docker exec`.
set -euo pipefail
HERE=$(cd "$(dirname "$0")" && pwd)
. "$HERE/../../lib.sh"
LAB_UID=$(id -u)
LAB_GID=$(id -g)
export LAB_AUDIO_DATA TALK_STATUS_DIR LAB_UID LAB_GID
compose() { docker compose -f "$HERE/compose.yml" "$@"; }
die() { echo "lab-go2rtc.sh: $*" >&2; exit 1; }
running() { [ "$(docker inspect -f '{{.State.Running}}' lab-go2rtc 2>/dev/null)" = true ]; }
# The API, from inside the container (its loopback).
api() { docker exec lab-go2rtc curl -s --max-time 20 "$@"; }

case "${1:-}" in
  up)
    mkdir -p "$LAB_AUDIO_DATA" "$TALK_STATUS_DIR"
    chmod 700 "$LAB_AUDIO_DATA"
    if [ ! -s "$LAB_AUDIO_DATA/tone.wav" ]; then
      docker run --rm -u "$LAB_UID:$LAB_GID" --network none -v "$LAB_AUDIO_DATA:/out" \
        --entrypoint ffmpeg "$LAB_GO2RTC_IMAGE" -hide_banner -loglevel error \
        -f lavfi -i "sine=frequency=1000:duration=4:sample_rate=8000" -af "volume=-24dB" \
        -ac 1 /out/tone.wav || die "could not make the test tone"
    fi
    compose up -d || die "could not start the lab go2rtc (see the docker compose output above)"
    ;;
  down) compose down ;;
  tone)
    stream=${2:?usage: lab-go2rtc.sh tone doorbell|baby}
    running || die "the lab go2rtc is not running: lab-go2rtc.sh up first"
    if ! code=$(api -o /dev/null -w '%{http_code}' -X POST \
      "http://127.0.0.1:1984/api/streams?dst=$stream&src=ffmpeg:/data/tone.wav%23audio=pcma%23input=file"); then
      die "the API inside the container did not answer"
    fi
    echo "play the test tone into $stream: HTTP $code"
    [ "$code" = 200 ] || die "the lab go2rtc refused the tone (HTTP $code)"
    ;;
  check)
    stream=${2:?usage: lab-go2rtc.sh check doorbell|baby}
    "$HERE/check-talk.sh" "$TALK_STATUS_DIR" "$stream"
    ;;
  status)
    compose ps --format '{{.Name}} {{.State}}'
    running || { echo "not running"; exit 0; }
    echo "API inside the container: HTTP $(api -o /dev/null -w '%{http_code}' http://127.0.0.1:1984/api/streams || echo none)"
    echo "published ports: $(docker port lab-go2rtc 2>/dev/null | wc -l) (0 expected)"
    ;;
  *) sed -n '2,12p' "$0"; exit 1 ;;
esac
