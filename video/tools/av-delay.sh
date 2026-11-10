#!/bin/bash
# av-delay.sh [seconds] [name]: one measurement of glass-to-glass video delay, audio delay and A/V
# offset in the Companion app, from the `sync` test stream (video/teststream/mediamtx.yml).
#
# Needs: the Docker route running with LAB_MIC=1 (its Pulse server takes the emulator's sound output,
# docker/entrypoint.sh), and the app showing a card that plays a camera fed by the `sync` path (e.g.
# the lab's Home Assistant with the Avent add-on and AVENT_LAB_SIM_SOURCE=rtsp://172.31.240.5:8554/sync, or a Generic
# camera on that path). Results in $OUT_DIR/av-delay-<name>/ (result.json) and on stdout.
#
# How: page-clock.js draws the device clock in the page every frame; a screen recording then holds,
# per frame, the stream's send time (its code band) and the device time it was drawn. The emulator's
# sound output is recorded in the container with host time stamps. av_delay.py does the analysis.
# The device-host clock offset is measured over adb (smallest round trip of 9 tries, +/- half of it).
# Not included: the display pipeline after the page draws (about one or two refreshes).
set -euo pipefail
. "$(dirname "$0")/../../lib.sh"
secs=${1:-20}
name=${2:-$(date +%H%M%S)}
dir="$OUT_DIR/av-delay-$name"
mkdir -p "$dir"
compose="docker compose -f $LAB_ROOT/docker/compose.yml"
cid=$($compose ps -q emulator 2>/dev/null || true)
[ -n "$cid" ] || { echo "the Docker route's emulator container does not run" >&2; exit 1; }
if ! docker exec -e PULSE_SERVER=unix:/tmp/lab-pulse/native "$cid" pactl list short sinks 2>/dev/null | grep -q labsink; then
  echo "no lab Pulse server in the container: start the Docker route with LAB_MIC=1" >&2
  exit 1
fi

forward_devtools >/dev/null
rects=$("$LAB_ROOT/tools/cdp.sh" <"$LAB_ROOT/video/tools/page-clock.js" | python3 -c 'import json,sys; print(json.loads(sys.stdin.read()))')
echo "$rects" | python3 -c 'import json,sys; d=json.load(sys.stdin); assert "video" in d, "no playing video in the page"' \
  || { echo "no playing video in the app's page: open a dashboard with the sync camera first" >&2; exit 1; }

# The card starts live video muted: unmute the playing video, or no sound reaches the output.
"$LAB_ROOT/tools/cdp.sh" <<'JS' >/dev/null
(() => { const v = []; const w = (r) => { for (const e of r.querySelectorAll('*')) { if (e.tagName === 'VIDEO') v.push(e); if (e.shadowRoot) w(e.shadowRoot); } }; w(document);
  v.filter((x) => x.videoWidth > 0).forEach((x) => { x.muted = false; x.volume = 1; }); return v.length; })()
JS

# Android's media volume (stream 3) at its maximum for the recording (the default 5 of 15 left the
# clicks near -38 dBFS); the previous value is put back at the end.
vol_before=$("$ADB" shell dumpsys audio </dev/null | awk '/^- STREAM_MUSIC:/{m=1} m && /streamVolume:/{sub(/.*streamVolume:/,""); print; exit}' | tr -d '\r')
"$ADB" shell cmd audio set-volume 3 15 </dev/null >/dev/null 2>&1 || true
trap '[ -n "$vol_before" ] && "$ADB" shell cmd audio set-volume 3 "$vol_before" </dev/null >/dev/null 2>&1' EXIT

# Device clock minus host clock: the try with the smallest round trip.
offset=$(for _ in 1 2 3 4 5 6 7 8 9; do
  a=$(python3 -c 'import time; print(time.time())')
  dev=$("$ADB" shell 'date +%s.%N' </dev/null | tr -d '\r')
  b=$(python3 -c 'import time; print(time.time())')
  echo "$a $dev $b"
done | python3 -c '
import sys
best = min((float(b) - float(a), float(d) - (float(a) + float(b)) / 2) for a, d, b in (l.split() for l in sys.stdin))
print(f"{best[1]:.6f} {best[0] / 2:.6f}")')

# Sound: the emulator's output sink, stamped with host time (stamp_audio.py) inside the container.
docker exec -d -e PULSE_SERVER=unix:/tmp/lab-pulse/native "$cid" sh -c \
  "parecord -d labsink.monitor --latency-msec=20 --raw --format=s16le --rate=48000 --channels=1 | python3 /lab/video/tools/stamp_audio.py /data/out/av-delay-audio"
sleep 1
dev_start=$("$ADB" shell 'date +%s%3N' </dev/null | tr -d '\r')
host_start=$(python3 -c 'import time; print(time.time())')
"$ADB" shell "screenrecord --time-limit $secs /sdcard/av-delay.mp4" </dev/null >/dev/null 2>&1
docker exec "$cid" sh -c 'pkill -INT parecord; sleep 1' || true
"$ADB" pull /sdcard/av-delay.mp4 "$dir/screen.mp4" >/dev/null </dev/null
docker cp "$cid:/data/out/av-delay-audio.raw" "$dir/audio.raw" >/dev/null
docker cp "$cid:/data/out/av-delay-audio.t0" "$dir/audio.t0" >/dev/null
docker cp "$cid:/data/out/av-delay-audio.timing" "$dir/audio.timing" >/dev/null
echo "audio chunk timing: $(cat "$dir/audio.timing")"

# Where the page sits on the screen: the page reports its rects relative to its own viewport, which
# starts below the status bar. The magenta strip page-clock.js draws above the clock bar is found in
# a frame of the recording (a colour nothing else on screen uses; a dark navigation bar or theme can
# no longer be taken for the clock), in a thin column at its left margin.
docker run --rm -u "$(id -u):$(id -g)" -v "$dir:/w" -w /w --entrypoint ffmpeg "$LAB_MEDIAMTX_IMAGE" \
  -hide_banner -loglevel error -y -i screen.mp4 -vf "select=eq(n\\,5),crop=4:ih:4:0,format=rgb24" -frames:v 1 \
  -f rawvideo column.raw
python3 - "$dir" "$rects" "$offset" "$dev_start" "$host_start" <<'PY'
import json, sys
d, rects, offset, dev_start, host_start = sys.argv[1:]
r = json.loads(rects)
off, err = (float(x) for x in offset.split())
r.update(offset_s=off, offset_err_s=err, device_start_ms=int(dev_start), host_start_s=float(host_start))
json.dump(r, open(f'{d}/meta.json', 'w'))
col = open(f'{d}/column.raw', 'rb').read()
w = 4 * 3
magenta = [i for i in range(len(col) // w)
           if all(col[i * w + k * 3] > 180 and col[i * w + k * 3 + 1] < 80 and col[i * w + k * 3 + 2] > 180
                  for k in range(4))]
assert magenta, 'the page clock marker (magenta) is not on the screen recording'
# Its rows must form one run about as tall as the page says (a stray magenta pixel elsewhere is not it).
assert magenta[-1] - magenta[0] + 1 <= r['mark']['h'] * 1.5 + 2, f'magenta rows not one strip: {magenta[:3]}...{magenta[-3:]}'
dy = magenta[0] - r['mark']['y']
r['screen_offset_y'] = dy
json.dump(r, open(f'{d}/meta.json', 'w'))
v = dict(r['video'], y=r['video']['y'] + dy)
c = dict(r['clock'], y=r['clock']['y'] + dy)
band_h = v['h'] * 60 / v['vh']
crops = {
    'band': (v['x'], v['y'], v['w'], band_h, '160:6'),
    'body': (v['x'], v['y'] + v['h'] * 0.3, v['w'], v['h'] * 0.4, '16:8'),
    'clock': (c['x'], c['y'], c['w'], c['h'], f"{r['bits'] * 19}:4"),
}
with open(f'{d}/crops.txt', 'w') as f:
    for k, (x, y, w, h, s) in crops.items():
        f.write(f'{k} {int(w)} {int(h)} {int(x)} {int(y)} {s}\n')
PY
while read -r k w h x y s; do
  docker run --rm -u "$(id -u):$(id -g)" -v "$dir:/w" -w /w --entrypoint ffmpeg "$LAB_MEDIAMTX_IMAGE" \
    -hide_banner -loglevel error -y -i screen.mp4 -vf "crop=$w:$h:$x:$y,scale=$s:flags=area,format=gray" \
    -f rawvideo "$k.raw"
done <"$dir/crops.txt"
python3 "$LAB_ROOT/video/tools/av_delay.py" "$dir"
