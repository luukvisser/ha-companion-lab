"""feed-tone.py <fifo> <hz> <on_s> <off_s> <dbfs>: writes a test tone (on, then silence, repeated)
in real time as raw mono s16le 48 kHz into <fifo>, the lab microphone's Pulse pipe source. Paced to
the clock, so the source never runs dry or far ahead. Standard library only."""
import math
import struct
import sys
import time

fifo, hz, on_s, off_s, dbfs = sys.argv[1], float(sys.argv[2]), float(sys.argv[3]), float(sys.argv[4]), float(sys.argv[5])
rate, chunk = 48000, 960  # 20 ms
amp = int(32767 * 10 ** (dbfs / 20))
period = int(rate * (on_s + off_s))
on = int(rate * on_s)
cycle = bytearray()
for n in range(period):
    cycle += struct.pack('<h', int(amp * math.sin(2 * math.pi * hz * n / rate)) if n < on else 0)
import os
import stat

# Only ever into the Pulse source's FIFO: opening a missing path would create a regular file, which
# then keeps module-pipe-source from loading (a silent microphone).
# PulseAudio's pipe source creates the FIFO; wait for it (up to 10 s), never create it here.
for _ in range(100):
    if os.path.exists(fifo):
        break
    time.sleep(0.1)
if not os.path.exists(fifo) or not stat.S_ISFIFO(os.stat(fifo).st_mode):
    sys.exit(f'{fifo} is not a FIFO (the lab microphone source did not create it)')
with open(fifo, 'wb', buffering=0) as out:
    pos, start, sent = 0, time.monotonic(), 0
    while True:
        end = pos + chunk * 2
        block = cycle[pos:end] if end <= len(cycle) else cycle[pos:] + cycle[: end - len(cycle)]
        out.write(block)
        pos = end % len(cycle)
        sent += chunk
        delay = start + sent / rate - time.monotonic()
        if delay > 0:
            time.sleep(delay)
