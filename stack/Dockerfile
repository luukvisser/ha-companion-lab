# The isolated test stack's Home Assistant: the pinned upstream image plus the Philips Avent
# integration's one missing requirement, baked in at build time so the running stack needs no
# internet (it runs on an internal network). The same image runs the fake Tuya API and the edge
# proxy (it already has Python, aiohttp and cryptography), so the stack builds only this image.
#
# HA_IMAGE is pinned by digest in compose.yml; keep it at the release the lab is tested with.
ARG HA_IMAGE
FROM ${HA_IMAGE}

# The integration's manifest asks for pycryptodome>=3.20.0 (already in the image) and
# tinytuya>=1.15.0 (not in it). Pinned by version and wheel hash (requirements.txt).
COPY requirements.txt /tmp/avent-requirements.txt
RUN pip install --no-cache-dir --require-hashes --no-deps -r /tmp/avent-requirements.txt \
 && rm /tmp/avent-requirements.txt \
 && python3 -c "import tinytuya, Crypto; print('tinytuya', tinytuya.__version__)"

# `tc` for netem.sh, which runs this image in another container's network namespace to shape or
# break its traffic. Pinned to the version in the base image's Alpine 3.24 release repository; a
# newer release of the base needs this pin raised.
# `nft` for stack.sh's lockdown: a firewall loaded into each stack container's network
# namespace (outbound only to the stack's own network and replies to inbound connections).
RUN apk add --no-cache iproute2=7.0.0-r0 nftables=1.1.6-r1 && tc -V && nft --version
