#!/bin/bash
# accept-sdk-licenses.sh: shows the licence(s) the Android SDK packages this lab downloads are under
# (Google's text, from its repository XML) and records your acceptance, so setup/install-sdk.sh may
# download them. Each licence is shown in full and must be accepted by typing "accept"; the SHA-1 of
# the accepted text goes to $SDK_DIR/licenses/<id>, the same place sdkmanager uses. A changed text
# must be accepted again.
#
# Non-interactive (CI): set ANDROID_SDK_ACCEPT_LICENCE_SHA1 to the SHA-1 of the exact text you read
# and accepted (this script prints it). There is deliberately no blanket "yes": accepting Google's
# terms is a decision of the person running the lab, not of the lab.
set -euo pipefail
. "$(dirname "${BASH_SOURCE[0]}")/../lib.sh"

DL="$SDK_DIR/dl"
mkdir -p "$DL" "$SDK_DIR/licenses"
# Only the repository metadata is fetched here; no SDK package is downloaded.
INSTALL_SDK_PLAN_ONLY=1 "$LAB_ROOT/setup/install-sdk.sh" >/dev/null 2>&1 || true
[ -s "$DL/licences.txt" ] || { echo "could not read the licences from Google's repository XML" >&2; exit 1; }

while read -r ref lsha; do
  if [ "$(cat "$SDK_DIR/licenses/$ref" 2>/dev/null || true)" = "$lsha" ]; then
    echo "already accepted: $ref ($lsha)"
    continue
  fi
  if [ -n "${ANDROID_SDK_ACCEPT_LICENCE_SHA1:-}" ]; then
    case " $ANDROID_SDK_ACCEPT_LICENCE_SHA1 " in
      *" $lsha "*) printf '%s\n' "$lsha" > "$SDK_DIR/licenses/$ref"; echo "accepted $ref ($lsha)"; continue ;;
      *) echo "$ref: its text has SHA-1 $lsha, not in ANDROID_SDK_ACCEPT_LICENCE_SHA1; read it first" >&2; exit 1 ;;
    esac
  fi
  [ -t 0 ] || { echo "$ref (SHA-1 $lsha) is not accepted: read $DL/licence-$ref.txt, then run this script in a terminal or with ANDROID_SDK_ACCEPT_LICENCE_SHA1=$lsha" >&2; exit 1; }
  echo "==== $ref (SHA-1 $lsha) ===="
  ${PAGER:-less} "$DL/licence-$ref.txt" </dev/tty || cat "$DL/licence-$ref.txt"
  printf 'Type "accept" to accept the licence "%s" above, anything else to stop: ' "$ref"
  read -r answer </dev/tty
  [ "$answer" = accept ] || { echo "not accepted; nothing will be downloaded" >&2; exit 1; }
  printf '%s\n' "$lsha" > "$SDK_DIR/licenses/$ref"
  echo "accepted $ref ($lsha)"
done < "$DL/licences.txt"
