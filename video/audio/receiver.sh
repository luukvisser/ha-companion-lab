#!/bin/sh
# receiver.sh <name>: the "camera speaker" of a lab camera. go2rtc starts it for a stream's
# backchannel (`#backchannel=1#audio=alaw/8000`) and writes the talk-back audio (G.711 A-law,
# 8 kHz, mono, raw) to its stdin. Each session is kept as /status/<name>-talk.alaw (replaced at the
# next one), with its start and end in /status/<name>-talk.sessions. check-talk.sh measures it.
name=${1:-camera}
echo "start $(date -u +%Y-%m-%dT%H:%M:%SZ)" >> "/status/${name}-talk.sessions"
cat > "/status/${name}-talk.alaw"
echo "end $(date -u +%Y-%m-%dT%H:%M:%SZ) bytes $(wc -c < "/status/${name}-talk.alaw")" >> "/status/${name}-talk.sessions"
