"""sim_talk.py <dir> <id>: what the simulated Avent bridge received as talk-back, per session.

Reads <dir>/<id>-talk.sessions (lines `start <time> offset <n>` and `end <time> offset <n> bytes <b>
seconds <s> rms_dbfs <r> peak_dbfs <p>`, written by the simulator) and the raw audio
<dir>/<id>-talk.ulaw (G.711 mu-law, 8 kHz mono). Per session: duration, the simulator's own levels,
the dominant frequency (Goertzel filters 200-3400 Hz in 50 Hz steps, over 0.25 s blocks) and the
share of blocks whose dominant frequency is the lab microphone's 1 kHz tone (setup/feed-tone.py:
1 kHz, 2 s on, 1 s off), so a call carrying the lab tone shows about 67%.

  --self-test   checks the decoder and the frequency estimate on a synthetic tone
Standard library only.
"""
import math, os, sys

RATE = 8000
BLOCK = RATE // 4


def ulaw_to_linear(b):
    b = ~b & 0xFF
    sign = b & 0x80
    exponent = (b >> 4) & 0x07
    mantissa = b & 0x0F
    sample = ((mantissa << 3) + 0x84) << exponent
    sample -= 0x84
    return -sample if sign else sample


TABLE = [ulaw_to_linear(i) for i in range(256)]


def linear_to_ulaw(s):  # for the self-test only
    bias, clip = 0x84, 32635
    sign = 0x80 if s < 0 else 0
    s = min(abs(s), clip) + bias
    exponent = 7
    for e in range(7, -1, -1):
        if s & (0x4000 >> (7 - e)):
            exponent = e
            break
    mantissa = (s >> (exponent + 3)) & 0x0F
    return ~(sign | (exponent << 4) | mantissa) & 0xFF


def goertzel(samples, freq):
    k = 2 * math.cos(2 * math.pi * freq / RATE)
    s1 = s2 = 0.0
    for x in samples:
        s1, s2 = x + k * s1 - s2, s1
    return s1 * s1 + s2 * s2 - k * s1 * s2


def dominant(samples):
    rms = math.sqrt(sum(x * x for x in samples) / len(samples)) if samples else 0
    if rms < 30:  # about -60 dBFS: silence
        return None
    return max(range(200, 3401, 50), key=lambda f: goertzel(samples, f))


def analyse(pcm):
    blocks = [pcm[i:i + BLOCK] for i in range(0, len(pcm) - BLOCK + 1, BLOCK)]
    doms = [dominant(b) for b in blocks]
    voiced = [d for d in doms if d is not None]
    tone = sum(1 for d in doms if d is not None and abs(d - 1000) <= 50)
    top = max(set(voiced), key=voiced.count) if voiced else None
    return {"blocks": len(blocks), "dominant_hz": top, "tone_share": tone / len(blocks) if blocks else 0.0}


def sessions(path):
    out, cur = [], None
    for line in open(path):
        w = line.split()
        if not w:
            continue
        if w[0] == "start":
            cur = {"start": w[1], "offset": int(w[3])}
        elif w[0] == "end" and cur is not None:
            kv = dict(zip(w[2::2], w[3::2]))
            cur.update(end=w[1], bytes=int(kv["bytes"]), seconds=float(kv["seconds"]),
                       rms_dbfs=float(kv["rms_dbfs"]), peak_dbfs=float(kv["peak_dbfs"]))
            out.append(cur)
            cur = None
    return out


def main(d, ident):
    raw = open(os.path.join(d, f"{ident}-talk.ulaw"), "rb").read()
    ss = sessions(os.path.join(d, f"{ident}-talk.sessions"))
    if not ss:
        print("no finished talk sessions")
        return
    print("session | start (UTC) | seconds | rms dBFS | peak dBFS | dominant Hz | share of 0.25 s blocks with the 1 kHz tone")
    for i, s in enumerate(ss, 1):
        pcm = [TABLE[b] for b in raw[s["offset"]:s["offset"] + s["bytes"]]]
        a = analyse(pcm)
        print(f"{i} | {s['start']} | {s['seconds']:.2f} | {s['rms_dbfs']:.1f} | {s['peak_dbfs']:.1f} | "
              f"{a['dominant_hz'] or '-'} | {a['tone_share']:.0%}")


def self_test():
    # 3 s: 2 s of 1 kHz at -20 dBFS, 1 s of silence (the lab tone's pattern).
    amp = 32767 * 10 ** (-20 / 20)
    lin = [int(amp * math.sin(2 * math.pi * 1000 * n / RATE)) for n in range(2 * RATE)] + [0] * RATE
    dec = [TABLE[linear_to_ulaw(x)] for x in lin]
    err = max(abs(a - b) for a, b in zip(lin, dec))
    assert err < 1100, f"mu-law round trip error {err}"
    a = analyse(dec)
    assert a["dominant_hz"] == 1000, a
    assert 0.6 <= a["tone_share"] <= 0.7, a
    print("self-test ok:", a)


if __name__ == "__main__":
    if sys.argv[1:] == ["--self-test"]:
        self_test()
    else:
        main(sys.argv[1], sys.argv[2])
