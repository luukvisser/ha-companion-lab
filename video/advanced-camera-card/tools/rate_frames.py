"""rate_frames.py <raw gray file> <width> <height> [fps] [offset ms]: rates each frame of a raw 8-bit
gray stream (ffmpeg -f rawvideo -pix_fmt gray) as W (mostly near-white) or P (picture) and prints
the segments as `S@<ms>`, with the times shifted by <offset ms> (the relaunch moment within the
recording; negative times are before it). With fps 0 the file is a single frame: prints W or P.

  rate_frames.py --self-test
"""
import sys

WHITE_LEVEL = 235
WHITE_SHARE = 0.6


def rate(frame: bytes) -> str:
    return "W" if sum(1 for b in frame if b > WHITE_LEVEL) / max(len(frame), 1) > WHITE_SHARE else "P"


def segments(data: bytes, w: int, h: int, fps: float, offset_ms: int) -> list:
    n = w * h
    out = []
    for k in range(len(data) // n):
        s = rate(data[k * n:(k + 1) * n])
        if not out or out[-1][1] != s:
            out.append([round(k * 1000 / fps) - offset_ms, s])
    return out


def self_test() -> None:
    white, dark = bytes([250]) * 4, bytes([10]) * 4
    assert rate(white) == "W" and rate(dark) == "P"
    assert segments(dark + dark + white + dark, 2, 2, 10, 0) == [[0, "P"], [200, "W"], [300, "P"]]
    assert segments(dark + white, 2, 2, 10, 1000) == [[-1000, "P"], [-900, "W"]]
    print("rate_frames self-test: ok")


if __name__ == "__main__":
    if sys.argv[1:] == ["--self-test"]:
        self_test()
        sys.exit()
    path, w, h = sys.argv[1], int(sys.argv[2]), int(sys.argv[3])
    fps = float(sys.argv[4]) if len(sys.argv) > 4 else 30
    offset = int(sys.argv[5]) if len(sys.argv) > 5 else 0
    data = open(path, "rb").read()
    if fps == 0:
        print(rate(data))
    else:
        print(" ".join(f"{s}@{t}" for t, s in segments(data, w, h, fps, offset)))
