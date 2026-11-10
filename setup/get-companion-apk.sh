#!/bin/bash
# get-companion-apk.sh [version]: downloads the Home Assistant Companion app's "minimal" APK of that
# release (default $COMPANION_VERSION) from GitHub and installs it on the running emulator. Checks
# the file's SHA-256 against the digest GitHub lists for the release asset (a cached file is checked
# the same way), and refuses to install on a mismatch or when GitHub lists no digest.
set -euo pipefail
. "$(dirname "$0")/../lib.sh"
VERSION=${1:-$COMPANION_VERSION}
APK="$SDK_DIR/dl/app-minimal-release-$VERSION.apk"
API=https://api.github.com/repos/home-assistant/android/releases/tags/$VERSION

# The asset's digest as GitHub lists it ("sha256:<hex>").
DIGEST=$(curl -fsS "$API" | python3 -c '
import json, sys
asset = [a for a in json.load(sys.stdin)["assets"] if a["name"] == "app-minimal-release.apk"][0]
digest = asset.get("digest") or ""
print(digest.split(":", 1)[1] if digest.startswith("sha256:") else "")')
[ -n "$DIGEST" ] || { echo "GitHub lists no SHA-256 digest for this asset; not installing an unchecked APK" >&2; exit 1; }
mkdir -p "$(dirname "$APK")"
[ -f "$APK" ] && [ "$(sha256_of "$APK")" = "$DIGEST" ] ||
  curl -fsSL -o "$APK" "https://github.com/home-assistant/android/releases/download/$VERSION/app-minimal-release.apk"
[ "$(sha256_of "$APK")" = "$DIGEST" ] || { echo "SHA-256 mismatch for $APK" >&2; exit 1; }
echo "APK $VERSION: SHA-256 $DIGEST, as GitHub lists it"
"$ADB" install -r "$APK" | tail -1
# Android 17 asks for "nearby devices" (the local-network permission) on first use; denied, the app
# times out silently on a LAN address. Grant it up front (fails harmlessly on older Android).
"$ADB" shell pm grant "$PKG" android.permission.ACCESS_LOCAL_NETWORK 2>/dev/null &&
  echo "granted ACCESS_LOCAL_NETWORK" || echo "ACCESS_LOCAL_NETWORK not applicable on this Android"
