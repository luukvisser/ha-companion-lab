# Python with a websocket client, for the CDP tools (tools/cdp/*.py) and the Home Assistant API
# scripts (setup/*.py, video/*.py). Built by setup/build-images.sh as `ha-companion-lab-py`.
# The base is pinned by digest (a multi-arch index); the one package by version and wheel hash.
FROM python:3.13-alpine@sha256:1e1f6334529d1fb26a2ef619d7cffb30a7c7d7cc1cc7338ebee283a58d1aeaca
COPY requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir --require-hashes --no-deps -r /tmp/requirements.txt && rm /tmp/requirements.txt
