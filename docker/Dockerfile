# The Android emulator with the Home Assistant Companion app, headless (Docker route; see
# docker/README.md). Only the runtime the emulator needs is installed here: the SDK, the system
# image and the app are downloaded on first start into volumes, by the same setup/ scripts the
# host route uses (checksums checked against Google's repository XML).
FROM ubuntu:noble-20260930.1@sha256:68ee22004a9109b44973313b02ff7b1de250f1de0f5ecb628d73f579aaff33ac

# System libraries the emulator's binaries and bundled libraries load (checked with ldd against
# emulator 37.3 on this base), the download tools the setup scripts use, and the optional viewer
# (a virtual X display, a VNC server and noVNC in the browser).
RUN apt-get update \
 && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
      ca-certificates curl unzip python3 procps \
      libice6 libsm6 libx11-6 libxext6 libxi6 libxcb1 libxkbfile1 libbsd0 libdbus-1-3 \
      libdrm2 libexpat1 libgbm1 libnss3 libpng16-16t64 libpulse0 \
      libegl1 libgles2 libgl1-mesa-dri mesa-vulkan-drivers libvulkan1 mesa-utils \
      xvfb x11vnc novnc websockify \
      pulseaudio pulseaudio-utils \
 && rm -rf /var/lib/apt/lists/*

# VirtualGL (GLX on the GPU's render node for EMULATOR_VGL=1, docker/compose.gpu.yml), pinned by
# its release checksum. wxWindows Library Licence; installed in the image, not redistributed.
ADD --checksum=sha256:df3f7788ce41b182a47c0d298e5cd6d2d63579522cb41825970b7726e825485e \
    https://github.com/VirtualGL/virtualgl/releases/download/3.1.5/virtualgl_3.1.5_amd64.deb /tmp/virtualgl.deb
# vglfix.so (vglfix/vglfix.c): VirtualGL returns 1 instead of Success for the pbuffer-size config
# attributes, which made the emulator drop every config; built here, the compiler removed again.
COPY vglfix/vglfix.c /tmp/vglfix.c
RUN apt-get update \
 && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends /tmp/virtualgl.deb gcc libc6-dev \
 && gcc -shared -fPIC -O2 -o /opt/vglfix.so /tmp/vglfix.c -Wl,--no-as-needed -L/usr/lib -l:libvglfaker.so -ldl \
 && readelf -d /opt/vglfix.so | grep -q "libvglfaker.so" \
 && apt-get purge -y gcc libc6-dev && apt-get autoremove -y \
 && rm -rf /var/lib/apt/lists/* /tmp/virtualgl.deb /tmp/vglfix.c

ENV SDK_DIR=/opt/android-sdk \
    OUT_DIR=/data/out \
    BUILDS_DIR=/data/builds \
    HOME=/root

# The repository itself is mounted at /lab (compose.yml), so script changes need no rebuild.
ENTRYPOINT ["/lab/docker/entrypoint.sh"]
