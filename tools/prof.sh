#!/bin/bash
# prof.sh <cov|cpu|mem|listeners|instr|trace> [-s s] [-r rounds] [-b] [-j js] [-f filter] [-n top] [-l label]:
# profilers for the app's page, around an optional action (-j, JavaScript evaluated in the page with
# a user gesture at the start of each window). Results in $OUT_DIR/prof-<mode>-<label>.*.
#
#   cov    exact call counts per JavaScript function (V8 precise coverage); -f limits it to scripts
#          whose URL contains the text (e.g. advanced-camera-card). Independent of CPU speed.
#   cpu    sampled self/total time per JavaScript function (V8 CPU profiler), .cpuprofile files.
#   mem    JavaScript heap and DOM counters after GC, before and after each round; bytes allocated
#          per function in the window; plus each process's PSS (dumpsys meminfo) before and after
#          the whole run.
#   listeners  event listeners per target and handler position, before and after -r rounds of
#          action and undo: which ones were added and not removed.
#   instr  hardware instruction and cycle counts (simpleperf, as root in the userdebug image) of
#          the app process, the WebView renderer (where the page's JavaScript runs) and
#          media.swcodec (software video decoding). Instructions repeat to about 0.002% for a fixed
#          workload; cycles and time do not (measured 10-11-2026).
#   trace  a Chrome trace for DevTools/Perfetto, with a summary of the renderer's main thread.
#
# -s seconds per window (5), -r rounds (3), -b a baseline window without the action before each
# action window, -x JS undoing the action after each action window (outside the window; e.g.
# leaving fullscreen, so the next round can enter again), -n top functions/events (15), -l label.
# Example: tools/prof.sh cov -b -f advanced-camera-card \
#   -j "document.querySelector('home-assistant')...requestFullscreen()"
# Caution: instr starts its action through a container (about 1 s into the window); give the window
# enough seconds. Counts include whatever else the page did in the window: compare like with like
# (same page, same state), and use -b to see the background.
set -euo pipefail
. "$(dirname "$0")/../lib.sh"
mode=${1:?usage: prof.sh cov|instr|trace [options]}
shift
forward_devtools >/dev/null
# The run's setup next to its result (lib.sh write_meta; the label is the -l value).
label=run prev=""
for arg in "$@"; do [ "$prev" = -l ] && label=$arg; prev=$arg; done
write_meta "prof-$mode-$label" "$(cat "$LAB_STATE_DIR/card-build" 2>/dev/null || true)"
pss() { # total PSS in KB of the app, each WebView renderer and media.swcodec
  local name pid
  {
    echo "app $(app_pid)"
    "$ADB" shell ps -A -o PID,NAME </dev/null | awk '/sandboxed_process/ {n++; print "renderer" n, $1}'
    echo "swcodec $("$ADB" shell pidof media.swcodec </dev/null | tr -d '\r')"
  } | while read -r name pid; do
    printf '%s %s\n' "$name" "$("$ADB" shell su 0 dumpsys meminfo "$pid" </dev/null | awk '/TOTAL PSS:/ {print $3; exit}')"
  done
}
if [ "$mode" = mem ]; then
  pss >"$OUT_DIR/prof-mem-pss-before"
  lab_py /lab/tools/cdp/prof.py "$mode" "$@"
  pss >"$OUT_DIR/prof-mem-pss-after"
  echo "process PSS, MB, before -> after the run (no forced GC in the processes):"
  join "$OUT_DIR/prof-mem-pss-before" "$OUT_DIR/prof-mem-pss-after" | awk '{ printf "  %-10s %.1f -> %.1f\n", $1, $2 / 1024, $3 / 1024 }'
  exit
fi
if [ "$mode" != instr ]; then
  lab_py /lab/tools/cdp/prof.py "$mode" "$@"
  exit
fi

secs=5 rounds=3 base="" js="" undo="" label=run
while getopts "s:r:bj:x:l:f:n:" o; do
  case "$o" in
    s) secs=$OPTARG ;; r) rounds=$OPTARG ;; b) base=1 ;; j) js=$OPTARG ;; x) undo=$OPTARG ;;
    l) label=$OPTARG ;;
    f | n) ;;
    *) exit 2 ;;
  esac
done
procs() { # name=pid for the app, each WebView renderer, and media.swcodec
  echo "app=$(app_pid)"
  "$ADB" shell ps -A -o PID,NAME </dev/null | awk '/sandboxed_process/ {n++; print "renderer" n "=" $1}'
  echo "swcodec=$("$ADB" shell pidof media.swcodec </dev/null | tr -d '\r')"
}
mapfile -t P < <(procs)
tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT
out="$OUT_DIR/prof-instr-$label.tsv"
printf 'round\tphase\tprocess\tinstructions\tcycles\n' >"$out"
window() { # window <round> <phase>
  local p name pid
  for p in "${P[@]}"; do
    name=${p%%=*} pid=${p#*=}
    "$ADB" shell "su 0 simpleperf stat -e instructions:u,cpu-cycles:u -p $pid --duration $secs" \
      </dev/null >"$tmp/$name" 2>&1 &
  done
  sleep 0.3
  if [ "$2" = action ] && [ -n "$js" ]; then lab_py /lab/tools/cdp/prof.py act -j "$js" >/dev/null; fi
  wait
  for p in "${P[@]}"; do
    name=${p%%=*}
    awk -v r="$1" -v ph="$2" -v n="$name" '
      /instructions:u/ { gsub(",", "", $1); i = $1 } /cpu-cycles:u/ { gsub(",", "", $1); c = $1 }
      END { printf "%s\t%s\t%s\t%s\t%s\n", r, ph, n, (i == "" ? "-" : i), (c == "" ? "-" : c) }' "$tmp/$name" >>"$out"
  done
}
for r in $(seq "$rounds"); do
  [ -n "$base" ] && window "$r" baseline
  window "$r" action
  if [ -n "$undo" ]; then
    lab_py /lab/tools/cdp/prof.py act -j "$undo" >/dev/null
    sleep 2
  fi
done
echo "instructions (millions) per $secs s window; cycles in $out"
awk -F'\t' 'NR > 1 { v = ($4 == "-") ? "-" : sprintf("%.1f", $4 / 1e6); printf "%s %-8s %-10s %s\n", $1, $2, $3, v }' "$out"
