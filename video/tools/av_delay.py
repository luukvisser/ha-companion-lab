"""av_delay.py <dir>: glass-to-glass video delay, audio delay and A/V offset from one av-delay.sh run.

Inputs in <dir> (written by av-delay.sh):
  meta.json   rects (device px), the device-minus-host clock offset and its uncertainty, rough times
  band.raw    per recorded frame: the video's code band, scaled to 160x6 gray
  body.raw    per recorded frame: the middle of the picture, 16x8 gray (white = a sync flash)
  clock.raw   per recorded frame: the page clock bar, (bits*19)x4 gray
  audio.raw   the emulator's sound output, s16le mono 48 kHz;  audio.t0: host time of its 1st sample

The `sync` test stream (video/teststream/mediamtx.yml) draws on every frame the wall-clock time it
was made (frames of 1/30 s, modulo 65536), and a white frame plus a click of 700/900/1100/1300 Hz
(second 0-3 modulo 4) every second. The page clock (page-clock.js) draws the device time each frame
was drawn. So:
  video delay = page time (device clock, made host time) - code time   (first frame of each code)
  audio delay = click arrival in the emulator output (host clock) - code time of its white frame
Standard library only. `--self-test` checks the decoding on synthetic data.
"""
import json
import math
import os
import statistics
import struct
import sys

FREQS = [700, 900, 1100, 1300]


def decode_bits(row, centers, threshold):
    return sum(1 << k for k, x in enumerate(centers) if row[x] > threshold)


def unwrap(value, modulo, near):
    """The value + k*modulo closest to `near`."""
    k = round((near - value) / modulo)
    return value + k * modulo


def frames(path, size):
    data = open(path, 'rb').read()
    return [data[i:i + size] for i in range(0, len(data) - size + 1, size)]


def video_samples(band, body, clock, meta):
    bits = meta['bits']
    cw = bits * 19
    code_centers = [k * 8 + 4 for k in range(16)]
    idx_centers = [128 + k * 16 + 8 for k in range(2)]
    clock_centers = [k * 19 + 9 for k in range(bits)]
    offset = meta['offset_s']                 # device clock minus host clock
    near_dev_ms = meta['device_start_ms']     # rough device time of the recording
    near_host_s = meta['host_start_s']
    rows = []
    for b, m, c in zip(band, body, clock):
        brow = b[160 * 3:160 * 4]
        crow = c[cw * 2:cw * 3]
        flash = sum(m) / len(m) > 200
        code = decode_bits(brow, code_centers, 128)
        idx = decode_bits(brow, idx_centers, 200)
        dev_ms = unwrap(decode_bits(crow, clock_centers, 128), 1 << bits, near_dev_ms)
        sent = unwrap(code, 65536, near_host_s * 30) / 30
        rows.append((dev_ms / 1000 - offset, sent, flash, idx))
    # The source's second boundaries: every frame carries its wall-clock code c (in frames) and the
    # second index i = floor(n/30) mod 4 of its frame number n. With c = c0 + n, the c0 (modulo 120)
    # that agrees with the most frames gives every white frame's code: c0 + 30*k.
    codes = [(round(sent * 30), idx) for _, sent, _, idx in rows]
    best = max(range(120), key=lambda c0: sum(1 for c, i in codes if ((c - c0) % 120) // 30 == i))
    agree = sum(1 for c, i in codes if ((c - best) % 120) // 30 == i) / max(len(codes), 1)
    phase = (best, agree)
    samples, flashes, last = [], [], None
    for shown, sent, flash, idx in rows:
        if sent != last:                      # the first recorded frame showing this code
            delay = shown - sent
            if 0 < delay < 30:
                samples.append(delay)
                if flash:
                    flashes.append((sent, idx))
            last = sent
    return samples, flashes, phase


def clicks(raw, t0, rate=48000):
    n = len(raw) // 2
    s = struct.unpack('<%dh' % n, raw[:n * 2])
    win = rate // 200                         # 5 ms
    rms = [math.sqrt(sum(x * x for x in s[i:i + win]) / win) for i in range(0, n - win, win)]
    if not rms:
        return []
    threshold = max(max(rms) * 0.3, 300)
    out, quiet = [], 1000
    for w, r in enumerate(rms):
        if r > threshold and quiet >= 40:     # >= 200 ms quiet before an onset
            i = w * win
            seg = s[i:i + rate * 15 // 1000]
            zc = sum(1 for a, b in zip(seg, seg[1:]) if (a < 0) != (b < 0))
            freq = zc / 2 / (len(seg) / rate)
            idx = min(range(4), key=lambda k: abs(FREQS[k] - freq))
            out.append((t0 + i / rate, idx, freq))
            quiet = 0
        elif r <= threshold:
            quiet += 1
    return out


def audio_samples(click_list, phase, video_delay):
    """Each click's send time is a white frame of the same second index, known up to 4 s (the index
    repeats every 4 seconds); the candidate closest to the measured video delay is taken, which
    assumes audio and video are less than 2 s apart."""
    c0, _ = phase
    out = []
    for arrival, idx, _ in click_list:
        base = (c0 + 30 * idx) / 30            # a white frame of this index, modulo 4 s
        k = round((arrival - video_delay - base) / 4)
        sent = base + 4 * k
        if arrival - sent > 0:
            out.append(arrival - sent)
    return out


def summary(name, xs):
    if not xs:
        return f'{name}: no samples'
    xs = sorted(xs)
    q = lambda p: xs[min(len(xs) - 1, int(p * len(xs)))]
    return f'{name}: median {statistics.median(xs) * 1000:.0f} ms (p10 {q(0.1) * 1000:.0f}, p90 {q(0.9) * 1000:.0f}, n={len(xs)})'


def self_test():
    # A code band and a page clock built the way the stream and page-clock.js draw them.
    meta = {'bits': 21, 'offset_s': 0.5, 'device_start_ms': 1_000_000_500, 'host_start_s': 1_000_000.0}
    def band(code, idx):
        row = bytearray(160)
        for k in range(16):
            if code >> k & 1:
                row[k * 8 + 4] = 255
        for k in range(2):
            if idx >> k & 1:
                row[128 + k * 16 + 8] = 255
        return bytes(160 * 3) + bytes(row) + bytes(160 * 2)
    def clock(ms):
        cw = 21 * 19
        row = bytearray(cw)
        for k in range(21):
            if (ms % (1 << 21)) >> k & 1:
                row[k * 19 + 9] = 255
        return bytes(cw * 2) + bytes(row) + bytes(cw)
    sent0 = 1_000_000.0
    b, m, c = [], [], []
    for f in range(60):
        sent = sent0 + f / 30
        code = int(round(sent * 30)) % 65536
        flash = f % 30 == 0
        b.append(band(code, (f // 30) % 4))
        m.append(bytes([255] * 128) if flash else bytes(128))
        c.append(clock(int((sent + 0.250 + 0.5) * 1000)))   # shown 250 ms later, device +0.5 s
    v, fl, ph = video_samples(b, m, c, meta)
    assert len(v) == 60 and all(abs(x - 0.25) < 0.002 for x in v), v[:3]
    assert ph[1] == 1.0, ph
    assert len(fl) == 2 and fl[0][1] == 0 and fl[1][1] == 1, fl
    # Two clicks of 700 and 900 Hz, 400 ms after their flashes.
    rate = 48000
    audio = [0] * (rate * 3)
    for k, f0 in enumerate((700, 900)):
        start = int((k + 0.4) * rate)
        for i in range(rate // 50):
            audio[start + i] = int(12000 * math.sin(2 * math.pi * f0 * i / rate))
    raw = struct.pack('<%dh' % len(audio), *audio)
    cl = clicks(raw, sent0)
    assert [x[1] for x in cl] == [0, 1], cl
    a = audio_samples(cl, ph, 0.25)
    assert len(a) == 2 and all(abs(x - 0.4) < 0.006 for x in a), a
    print('self-test ok')


def main(d):
    meta = json.load(open(os.path.join(d, 'meta.json')))
    cw = meta['bits'] * 19
    band = frames(os.path.join(d, 'band.raw'), 160 * 6)
    body = frames(os.path.join(d, 'body.raw'), 16 * 8)
    clock = frames(os.path.join(d, 'clock.raw'), cw * 4)
    v, fl, ph = video_samples(band, body, clock, meta)
    a = []
    if os.path.exists(os.path.join(d, 'audio.raw')):
        t0 = float(open(os.path.join(d, 'audio.t0')).read())
        cl = clicks(open(os.path.join(d, 'audio.raw'), 'rb').read(), t0)
        a = audio_samples(cl, ph, statistics.median(v)) if v else []
        print(f'clicks heard: {len(cl)}, matched to a white frame: {len(a)}')
    print(f'recorded frames: {len(band)}, white frames seen: {len(fl)}, frames agreeing on the second boundaries: {ph[1] * 100:.0f}%')
    print(summary('video delay (glass-to-glass, page draw)', v))
    print(summary('audio delay (to the emulator output)', a))
    if v and a:
        print(f'A/V offset (audio minus video, medians): {(statistics.median(a) - statistics.median(v)) * 1000:+.0f} ms')
    print(f'clock offset device-host: {meta["offset_s"] * 1000:+.1f} ms +/- {meta["offset_err_s"] * 1000:.1f} ms')
    json.dump({'video_s': v, 'audio_s': a}, open(os.path.join(d, 'result.json'), 'w'))


if __name__ == '__main__':
    if sys.argv[1:] == ['--self-test']:
        self_test()
    else:
        main(sys.argv[1])
