#!/bin/bash
# check-talk.sh <status dir> <name>: what the lab camera <name> last heard: the sessions, the
# duration (8000 bytes per second) and the level of the last one. Measures with the pinned go2rtc
# image's ffmpeg (LAB_GO2RTC_IMAGE), without network.
set -euo pipefail
. "$(cd "$(dirname "$0")" && pwd)/../../lib.sh"
dir=${1:?usage: check-talk.sh <status dir> <name>}; name=${2:?usage: check-talk.sh <status dir> <name>}
[ -f "$dir/$name-talk.sessions" ] || { echo "no talk received by $name"; exit 1; }
tail -4 "$dir/$name-talk.sessions"
bytes=$(wc -c < "$dir/$name-talk.alaw")
echo "last session: $bytes bytes = $(awk "BEGIN{printf \"%.1f\", $bytes/8000}") s"
[ "$bytes" -gt 0 ] || exit 1
out=$(docker run --rm --network none -u "$(id -u):$(id -g)" -v "$dir:/status:ro" --entrypoint ffmpeg \
  "$LAB_GO2RTC_IMAGE" -hide_banner -loglevel info -f alaw -ar 8000 -ac 1 -i "/status/$name-talk.alaw" \
  -af "astats=measure_overall=RMS_level+Peak_level:measure_perchannel=none" -f null - 2>&1) ||
  { echo "check-talk.sh: ffmpeg could not read the recording" >&2; exit 1; }
grep -E "RMS level|Peak level" <<<"$out" | sed 's/^.*\] /level: /'
