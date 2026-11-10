#!/bin/bash
# create-avd.sh: writes the AVD ($AVD_NAME) by hand, so no Java/avdmanager is needed. The emulator
# reads ~/.android/avd/<name>.ini and <name>.avd/config.ini.
set -euo pipefail
. "$(dirname "$0")/../lib.sh"

# `|| true`: under pipefail a failing ls (no match) would end the script before the message below.
SYSDIR=$( (cd "$SDK_DIR" && ls -d system-images/android-"$API_LEVEL"*/google_apis/"$SDK_ABI" 2>/dev/null | head -1) || true)
[ -n "$SYSDIR" ] || { echo "no $SDK_ABI system image for API $API_LEVEL; run setup/install-sdk.sh" >&2; exit 1; }
[ "$SDK_ABI" = arm64-v8a ] && CPU_ARCH=arm64 || CPU_ARCH=x86_64

AVD="$HOME/.android/avd"
mkdir -p "$AVD/$AVD_NAME.avd"
cat > "$AVD/$AVD_NAME.ini" <<EOF
avd.ini.encoding=UTF-8
path=$AVD/$AVD_NAME.avd
target=android-$API_LEVEL
EOF
cat > "$AVD/$AVD_NAME.avd/config.ini" <<EOF
avd.ini.encoding=UTF-8
AvdId=$AVD_NAME
avd.ini.displayname=$AVD_NAME
abi.type=$SDK_ABI
hw.cpu.arch=$CPU_ARCH
hw.cpu.ncore=2
hw.ramSize=3072
disk.dataPartition.size=6G
image.sysdir.1=$SYSDIR/
tag.id=google_apis
tag.display=Google APIs
hw.lcd.width=$AVD_WIDTH
hw.lcd.height=$AVD_HEIGHT
hw.lcd.density=$AVD_DENSITY
hw.keyboard=yes
hw.gpu.enabled=yes
# The host GPU mode froze the WebView in our tests (docs/pitfalls.md).
hw.gpu.mode=swiftshader_indirect
hw.mainKeys=no
showDeviceFrame=no
fastboot.forceColdBoot=no
EOF
echo "AVD $AVD_NAME on $SYSDIR"

# Hardware virtualisation is required for usable speed: KVM on Linux; on macOS the emulator uses
# Apple's Hypervisor framework by itself.
if [ "$HOST_OS" = linux ]; then
  python3 -c 'import os; os.close(os.open("/dev/kvm", os.O_RDWR))' 2>/dev/null &&
    echo "KVM: usable" || echo "KVM: not usable by $(id -un) (add yourself to the kvm group or check the ACL)"
fi
