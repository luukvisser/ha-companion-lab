#!/bin/bash
# card.sh <measurement> <builds> [args]: one entry point for the card measurements. <builds> is a
# comma-separated list of names under $BUILDS_DIR. Every measurement here runs against the isolated
# lab's Home Assistant (stack/: `./lab up`), installs each build into it, starts the app
# fresh, and writes the run's setup to $OUT_DIR/<result>.meta.json next to the result.
#
#   blip <builds> [rounds]             fullscreen enter/leave on the test card: event order, new
#                                      players, muted/paused flips, time without video (cdp/blip.py);
#                                      BLIP_FRAMES=1 adds frame counts (see this folder's README for the caveat)
#   blip-interrupt <builds> [rounds]   Home during the fullscreen transition, then whether a real
#                                      hidden spell still acts (cdp/blip_interrupt.py; HOME_DELAYS)
#   call <builds> [seconds]            a two-way-audio call from the test card (cdp/call.py); then
#                                      what the simulated bridge received (stack.sh talk)
#   call-cut <builds> [cut s] [tail s] a call during which the app's connection to Home Assistant is
#                                      cut for <cut s> (default 8; netem.sh cut proxy), then restored;
#                                      the call's state, the card's call and microphone state and the
#                                      page's HA connection every 2 s, Android's recording events, and
#                                      the cut's times; the call is held cut + tail s (default 25)
#   mute-cycles <builds> [cycles] [toggle|back|swipe|bg|switcher|off]
#                                      unmute, then fullscreen enter and leave <cycles> times (leave by
#                                      the card's fullscreen toggle or the Android back key): muted
#                                      after each step? (cdp/mute_cycles.py)
#   cov <builds> [rounds]              calls into the card's functions when entering fullscreen,
#                                      against an idle window (tools/prof.sh cov)
#   loading <builds> [rounds]          the loading indicator against the picture under it, from the
#                                      first load and on returns (playwright/loading-overlap.js)
#   doubletap <builds> [gaps] [rounds] double tap after a pinch: back to the default zoom?
#                                      (playwright/doubletap.js)
#   bg-rounds|bg-shots|bg-video <builds> [rounds]
#                                      background and return (see their own headers)
#   fullscreen <builds> [rounds] [api|back|swipe] [expanded 0|1]
#                                      the fullscreen height jump on a hand-placed card
#                                      (fullscreen-measure.sh)
#
# The card's configuration is the test dashboard's (video/ha-setup.sh dashboard ...), the stream the
# test camera's (video/ha-setup.sh camera ...): both are recorded in the meta.json.
set -euo pipefail
here=$(cd "$(dirname "$0")" && pwd)
. "$here/../../lib.sh"
# Pin every write to the lab's Home Assistant (lib.sh captures pins when it is sourced, so re-run pinned).
if [ -z "${LAB_PINNED_HA_URL:-}" ]; then
  exec env LAB_PIN_HA_URL="http://127.0.0.1:$LAB_HA_PORT" \
    LAB_PIN_HA_TOKEN_FILE="$LAB_HA_DATA/token" \
    LAB_PIN_TEST_USER_PASSWORD_FILE="$LAB_HA_DATA/test-user-password" "$0" "$@"
fi
what=${1:?usage: card.sh <blip|blip-interrupt|call|call-cut|mute-cycles|cov|loading|doubletap|bg-rounds|bg-shots|bg-video|fullscreen> <builds> [args]}
builds=${2:?give one or more build names under $BUILDS_DIR, comma-separated}
shift 2
FS="window.__covCard = ((t) => { const w = (r) => { for (const el of r.querySelectorAll('*')) { if (el.tagName.toLowerCase() === t) return el; if (el.shadowRoot) { const f = w(el.shadowRoot); if (f) return f; } } return null; }; return w(document); })('advanced-camera-card'); window.__covCard._controller.getFullscreenManager().setFullscreen(true)"
EXIT="document.exitFullscreen().catch(() => 0)"
GOTO="history.pushState(null, '', '$TEST_PATH'); window.dispatchEvent(new CustomEvent('location-changed', { detail: { replace: false } }))"

case "$what" in
  blip) exec "$here/blip.sh" "$builds" "${1:-5}" ;;
  blip-interrupt) exec "$here/blip-interrupt.sh" "$builds" "${1:-3}" ;;
  fullscreen) exec "$here/fullscreen-measure.sh" "$builds" "${1:-3}" "${2:-api}" "${3:-0}" ;;
esac

IFS=, read -r -a list <<<"$builds"
for b in "${list[@]}"; do
  "$LAB_ROOT/stack/stack.sh" card "$b" >/dev/null
  case "$what" in
    cov)
      fresh_app
      lab_py /lab/tools/cdp/prof.py act -j "$GOTO" >/dev/null
      sleep 20
      "$LAB_ROOT/tools/prof.sh" cov -b -r "${1:-3}" -f advanced-camera-card -l "card-$b" -j "$FS" -x "$EXIT" ;;
    call)
      write_meta "call-$b" "$b"
      fresh_app
      lab_py /lab/video/advanced-camera-card/cdp/call.py "$b" "${1:-8}"
      sleep 2
      "$LAB_ROOT/stack/stack.sh" talk | tee "$OUT_DIR/call-$b.talk.txt" ;;
    call-cut)
      write_meta "call-cut-$b" "$b"
      fresh_app
      cut=${1:-8} tail=${2:-25}
      lab_py /lab/video/advanced-camera-card/cdp/call.py "cut-$b" $((cut + tail)) &
      callpid=$!
      # Android's own view, every 2 s: is the app listed as recording (what the microphone
      # indicator shows)? Wall-clock ms, to line up with the page's timeline.
      (while kill -0 "$callpid" 2>/dev/null; do
        rec=$("$ADB" shell dumpsys audio </dev/null 2>/dev/null | sed -n '/## RecordActivityMonitor/,/^## [A-Z]/p' | grep -c "$PKG" || true)
        echo "android-recording $(date +%s%3N) $rec"
        sleep 2
      done) &
      recpid=$!
      sleep 22   # the video and the call start about 15 s in (measured), then a few seconds of call
      echo "cut at $(date +%s%3N)"
      "$LAB_ROOT/stack/netem.sh" cut proxy >/dev/null
      sleep "$cut"
      "$LAB_ROOT/stack/netem.sh" restore proxy >/dev/null
      echo "restored at $(date +%s%3N)"
      wait "$callpid" || true
      kill "$recpid" 2>/dev/null || true
      sleep 3   # the bridge writes a session's end line when the call has closed
      "$LAB_ROOT/stack/stack.sh" talk | tail -3 ;;
    mute-cycles)
      write_meta "mute-cycles-$b" "$b"
      fresh_app
      lab_py /lab/video/advanced-camera-card/cdp/mute_cycles.py "$b" "${1:-8}" "${2:-toggle}" 2>&1 |
        while IFS= read -r line; do
          case "$line" in
            "HOSTACT back "*) "$ADB" shell input keyevent 4 </dev/null; echo "${line##* }" >"$OUT_DIR/host-done" ;;
            "HOSTACT leave-"*) way=${line#HOSTACT leave-}; leave_app "${way%% *}"; echo "${line##* }" >"$OUT_DIR/host-done" ;;
            "HOSTACT return-"*) way=${line#HOSTACT return-}; return_app "${way%% *}"; echo "${line##* }" >"$OUT_DIR/host-done" ;;
            "HOSTACT swipe "*)
              # In immersive fullscreen the first edge swipe only shows the system bars.
              "$ADB" shell input touchscreen swipe 1 1200 450 1200 200 </dev/null
              sleep 1.5
              "$ADB" shell input touchscreen swipe 1 1200 450 1200 200 </dev/null
              echo "${line##* }" >"$OUT_DIR/host-done" ;;
            *) echo "$line" ;;
          esac
        done ;;
    loading)
      write_meta "loading-$b" "$b"
      fresh_app
      tools_pwa=("$LAB_ROOT/tools/pwa.sh" video/advanced-camera-card/playwright/loading-overlap.js deployed "${1:-3}" 15)
      "${tools_pwa[@]}" | tee "$OUT_DIR/loading-$b.txt" ;;
    doubletap)
      write_meta "doubletap-$b" "$b"
      fresh_app
      lab_py /lab/tools/cdp/prof.py act -j "$GOTO" >/dev/null
      sleep 20
      "$LAB_ROOT/tools/pwa.sh" video/advanced-camera-card/playwright/doubletap.js "${1:-single,100,200,280,400}" "${2:-3}" |
        tee "$OUT_DIR/doubletap-$b.txt" ;;
    bg-rounds | bg-shots | bg-video)
      write_meta "$what-$b" "$b"
      fresh_app
      "$here/$what.sh" deployed "${1:-5}" | tee "$OUT_DIR/$what-$b.txt" ;;
    *) echo "unknown measurement: $what" >&2; exit 2 ;;
  esac
done
