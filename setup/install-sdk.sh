#!/bin/bash
# install-sdk.sh: downloads the Android emulator and platform-tools (adb) for this host (Linux x64,
# macOS x64 or Apple Silicon) and the google_apis system image for $API_LEVEL in the host's native
# ABI ($SDK_ABI: x86_64, or arm64-v8a on Apple Silicon) straight from Google's repository, checks
# each zip's SHA-1 against Google's repository XML, and unpacks them into $SDK_DIR in the SDK's own
# layout. No Java, no sdkmanager, no sudo. Re-running skips a package that is already installed in
# that exact version (a marker per package records the zip's SHA-1); a new version replaces the
# old package folder as a whole, so no files of an older version stay mixed in.
set -euo pipefail
. "$(dirname "${BASH_SOURCE[0]}")/../lib.sh"
[ "$HOST_OS" != unsupported ] && [ "$HOST_ARCH" != unsupported ] ||
  { echo "unsupported host $(uname -s)/$(uname -m); see README (Windows: WSL2 or the SDK's own tools)" >&2; exit 1; }

# install_zip <zip> <sha1> <dest>: unpack a verified package zip into $SDK_DIR/<dest>, replacing
# each top-level folder it contains (emulator/, platform-tools/, x86_64/ ...) as a whole. Skips it
# when the marker says this exact zip is installed and its folders are there.
install_zip() {
  local zip=$1 sha=$2 dest=$3 marker tops top tmp
  marker="$SDK_DIR/.installed/$(basename "$zip").sha1"
  tops=$(unzip -Z1 "$zip" | cut -d/ -f1 | sort -u)
  for top in $tops; do
    case "$top" in
      "" | . | .. | *[!A-Za-z0-9_.-]*) echo "unexpected entry '$top' in $zip" >&2; return 1 ;;
    esac
  done
  if [ -f "$marker" ] && [ "$(cat "$marker")" = "$sha" ]; then
    local missing=""
    for top in $tops; do [ -d "$SDK_DIR/$dest/$top" ] || missing=1; done
    if [ -z "$missing" ]; then
      echo "already installed: $(basename "$zip")"
      return 0
    fi
  fi
  tmp="$SDK_DIR/.unpack-$$"
  rm -rf "$tmp"
  mkdir -p "$tmp" "$SDK_DIR/$dest" "$SDK_DIR/.installed"
  unzip -q "$zip" -d "$tmp"
  for top in $tops; do
    rm -rf "${SDK_DIR:?}/$dest/$top"
    mv "$tmp/$top" "$SDK_DIR/$dest/$top"
  done
  rm -rf "$tmp"
  printf '%s\n' "$sha" > "$marker"
  echo "installed $(basename "$zip") into ${dest}"
}

[ -n "${INSTALL_SDK_FUNCTIONS_ONLY:-}" ] && return 0 2>/dev/null

REPO=https://dl.google.com/android/repository
DL="$SDK_DIR/dl"
mkdir -p "$DL"
curl -fsS -o "$DL/repository2-3.xml" "$REPO/repository2-3.xml"
curl -fsS -o "$DL/sys-img2-3.xml" "$REPO/sys-img/google_apis/sys-img2-3.xml"

# Prints "<url> <sha1> <dest>" for each package to install.
python3 - "$DL" "$API_LEVEL" "$HOST_OS" "$HOST_ARCH" "$SDK_ABI" <<'PY' > "$DL/plan.txt"
import re, sys
dl, api, host_os, host_arch, abi = sys.argv[1:6]
repo = open(f"{dl}/repository2-3.xml").read()
img = open(f"{dl}/sys-img2-3.xml").read()

def packages(xml, path_re):
    for m in re.finditer(r'<remotePackage path="([^"]+)">(.*?)</remotePackage>', xml, re.S):
        if re.fullmatch(path_re, m.group(1)):
            yield m.group(1), m.group(2)

def host_archive(body):
    # An archive for this host: no host-os (system images), or this host-os and, where given, this
    # host-arch (the emulator has separate x64 and aarch64 builds for macOS).
    for a in re.findall(r"<archive>(.*?)</archive>", body, re.S):
        host = re.search(r"<host-os>(\w+)</host-os>", a)
        arch = re.search(r"<host-arch>(\w+)</host-arch>", a)
        if host and host.group(1) != host_os:
            continue
        if arch and arch.group(1) != host_arch:
            continue
        url = re.search(r"<url>([^<]+)</url>", a).group(1)
        sha = re.search(r'<checksum type="sha1">([^<]+)</checksum>', a).group(1)
        return url, sha
    return None

def stable_latest(name):
    best = None
    for _, body in packages(repo, re.escape(name)):
        if 'ref="channel-0"' not in body:
            continue
        rev = tuple(int(x) for x in re.findall(r"<(?:major|minor|micro)>(\d+)</", body)[:3])
        arch = host_archive(body)
        if arch and (best is None or rev > best[0]):
            best = (rev, arch + (body,))
    if best is None:
        sys.exit(f"no stable {name} for {host_os}/{host_arch}")
    return best[1]

# The licences the chosen packages say they are under (their <uses-license ref=...>), with their
# text from the repository XML, for the acceptance check below.
import hashlib, html
licences = {}
def note_licences(xml, body):
    for ref in re.findall(r'<uses-license ref="([^"]+)"', body):
        m = re.search(r'<license id="' + re.escape(ref) + r'"[^>]*>(.*?)</license>', xml, re.S)
        if m:
            licences[ref] = html.unescape(m.group(1)).strip()

url, sha, body = stable_latest("emulator")
note_licences(repo, body)
print(f"https://dl.google.com/android/repository/{url} {sha} .")
url, sha, body = stable_latest("platform-tools")
note_licences(repo, body)
print(f"https://dl.google.com/android/repository/{url} {sha} .")
for path in (f"system-images;android-{api}.0;google_apis;{abi}", f"system-images;android-{api};google_apis;{abi}"):
    found = list(packages(img, re.escape(path)))
    if found:
        url, sha = host_archive(found[0][1])
        note_licences(img, found[0][1])
        dest = "system-images/" + path.split(";")[1] + "/google_apis"
        print(f"https://dl.google.com/android/repository/sys-img/google_apis/{url} {sha} {dest}")
        break
else:
    sys.exit(f"no google_apis {abi} image for API {api}")
with open(f"{dl}/licences.txt", "w") as out:
    for ref, text in sorted(licences.items()):
        open(f"{dl}/licence-{ref}.txt", "w").write(text + "\n")
        out.write(f"{ref} {hashlib.sha1(text.encode()).hexdigest()}\n")
PY

# Nothing is downloaded until each licence the packages are under has been accepted, by a person,
# with setup/accept-sdk-licenses.sh (it shows the text and records its SHA-1 in $SDK_DIR/licenses/).
# A changed licence text has a new SHA-1 and must be accepted again.
missing=""
while read -r ref lsha; do
  [ "$(cat "$SDK_DIR/licenses/$ref" 2>/dev/null || true)" = "$lsha" ] || missing="$missing $ref"
done < "$DL/licences.txt"
[ -n "${INSTALL_SDK_PLAN_ONLY:-}" ] && exit 0
if [ -n "$missing" ]; then
  echo "Not accepted yet:$missing. Read and accept Google's terms first: setup/accept-sdk-licenses.sh" >&2
  exit 3
fi


while read -r url sha dest; do
  zip="$DL/$(basename "$url")"
  if [ ! -f "$zip" ] || [ "$(sha1_of "$zip")" != "$sha" ]; then
    echo "downloading $(basename "$url")"
    curl -fsS -o "$zip" "$url"
  fi
  [ "$(sha1_of "$zip")" = "$sha" ] || { echo "SHA-1 mismatch: $zip" >&2; exit 1; }
  echo "verified $(basename "$zip") ($sha)"
  install_zip "$zip" "$sha" "$dest"
done < "$DL/plan.txt"

"$ADB" version | head -1
ls "$SDK_DIR/system-images"/*/google_apis/
