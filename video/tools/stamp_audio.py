"""stamp_audio.py <out prefix>: reads raw s16le mono 48 kHz audio on stdin (parecord of the
emulator's output sink, inside the emulator container) and writes <prefix>.raw, <prefix>.t0 (the
host wall-clock time, seconds, of the first sample) and <prefix>.timing (how the chunks arrived).
The container shares the host's clock. Standard library only.

A chunk reaches us after its last sample was played plus the recording latency (parecord is asked
for 20 ms, av-delay.sh), so every chunk gives an upper bound of the first sample's time:
arrival - samples so far / rate. The smallest of these over the whole recording is the estimate:
it is the chunk that waited least. The .timing file says how far the others were behind it."""
import statistics
import sys
import time

prefix = sys.argv[1]
rate = 48000
chunk = 960  # 10 ms at 48 kHz mono s16le
samples = 0
bounds = []
with open(prefix + '.raw', 'wb') as raw:
    while True:
        data = sys.stdin.buffer.read(chunk)
        if not data:
            break
        samples += len(data) // 2
        bounds.append(time.time() - samples / rate)
        raw.write(data)
if bounds:
    t0 = min(bounds)
    late = [(b - t0) * 1000 for b in bounds]
    with open(prefix + '.t0', 'w') as f:
        f.write(f'{t0:.6f}\n')
    with open(prefix + '.timing', 'w') as f:
        f.write(f'chunks {len(bounds)} late_ms median {statistics.median(late):.1f} '
                f'p90 {sorted(late)[int(len(late) * 0.9)]:.1f} max {max(late):.1f}\n')
