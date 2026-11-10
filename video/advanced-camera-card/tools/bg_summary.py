"""Summarise a page log of bg-rounds.sh (lf-setup.js / lf-read.js output) per return to the page.

  bg_summary.py <log.json>     one line per return: what the first paint showed and when, the
                               captured-frame images and their decode times, and how long the card
                               showed nothing (no playing video, no loaded frame image, no canvas)
  bg_summary.py --check-variant <log.json>
                               only the build check: exits 1 when the page loaded card files that
                               are not in the variant's build (lf-read.js `variant_check`)
  bg_summary.py --self-test    checks the classifier and the window arithmetic

A show-log key looks like `v<n> i<n> c<n> <h|v> [...]` (older logs: no `c` field): counts of visible
playing videos, loaded frame images and drawn-frame canvases, then the page visibility.
"""
import json
import re
import sys

_COUNTS = re.compile(r"^v(\d+) i(\d+)(?: c(\d+))? ")


def is_blank(key: str) -> bool:
    """Nothing on screen from the card: no video, no image and no canvas."""
    m = _COUNTS.match(key)
    if not m:
        return False
    v, i, c = (int(x) if x is not None else 0 for x in m.groups())
    return v == 0 and i == 0 and c == 0


def windows(vis, now):
    """(start, end) of each visible spell: from a `visible` event to the next `hidden` (or `now`)."""
    out = []
    for n, (t, state) in enumerate(vis):
        if state != "visible":
            continue
        end = next((t2 for t2, s2 in vis[n + 1:] if s2 == "hidden"), now)
        out.append((t, end))
    return out


def blank_ms(show, start, end) -> int:
    """How long the card showed nothing between start and end, counting a state that was already in
    force at start and one that lasts until end."""
    before = [s for s in show if s[0] < start]
    inside = [s for s in show if start <= s[0] < end]
    states = ([(start, before[-1][1])] if before else []) + [(t, k) for t, k in inside]
    total = 0
    for n, (t, key) in enumerate(states):
        stop = states[n + 1][0] if n + 1 < len(states) else end
        if is_blank(key):
            total += max(0, stop - t)
    return total


def summarise(d) -> list:
    vis = d.get("vis") or []
    show = d.get("show") or []
    dec = d.get("dec") or []
    now = d.get("now") or (show[-1][0] if show else 0)
    lines = ["return | first paint after visible: state @ms | frame image seen @ms, decode ms | nothing shown ms"]
    for n, (start, end) in enumerate(windows(vis, now), 1):
        st = [s for s in show if start <= s[0] < end]
        first = st[0] if st else None
        ds = [x for x in dec if start - 50 <= x[0] < end]
        lines.append(
            f"{n} | {first[1] if first else '-'} @{first[0] - start if first else '-'} | "
            + ", ".join(f"@{x[0] - start} {x[1]}{'' if x[2] == 'ok' else ' ' + x[2]}" for x in ds)
            + f" | {blank_ms(show, start, end)}"
        )
    return lines


def check_variant(d) -> bool:
    """False (and why) when the page ran card files that are not the variant's build."""
    c = d.get("variant_check") or {}
    if c.get("ok") is False:
        print(f"VARIANT CHECK FAILED: the page loaded card files that are not in build "
              f"'{c.get('variant')}': {', '.join(c.get('foreign') or []) or 'no card files at all'}")
        return False
    if c.get("ok") is None:
        print(f"variant check: not applicable ({c.get('variant') or 'no variant given'}); "
              f"card files loaded: {len(c.get('loaded') or [])}")
    else:
        print(f"variant check: all {len(c['loaded'])} card files loaded are build '{c['variant']}'")
    return True


def self_test() -> None:
    assert is_blank("v0 i0 c0 v [..]")
    assert is_blank("v0 i0 v")  # older log without a canvas field
    assert not is_blank("v0 i0 c1 v [8,64 396x223]")  # a canvas is something on screen
    assert not is_blank("v0 i1 c0 v")
    assert not is_blank("v1 i0 c0 v")
    assert not is_blank("garbage")
    vis = [[100, "hidden"], [200, "visible"], [900, "hidden"], [1000, "visible"]]
    assert windows(vis, 1500) == [(200, 900), (1000, 1500)]
    # Blank from 300 until the window ends (no later state): counted to the end, not as 0.
    show = [[0, "v1 i0 c0 v"], [300, "v0 i0 c0 v"]]
    assert blank_ms(show, 200, 900) == 600, blank_ms(show, 200, 900)
    # A blank state already in force when the window starts counts from the start.
    assert blank_ms([[50, "v0 i0 c0 v"], [400, "v1 i0 c0 v"]], 200, 900) == 200
    # A canvas spell is not blank.
    assert blank_ms([[200, "v0 i0 c1 v"], [500, "v1 i0 c0 v"]], 200, 900) == 0
    assert check_variant({"variant_check": {"variant": "x", "loaded": ["a.js"], "foreign": [], "ok": True}})
    assert not check_variant({"variant_check": {"variant": "x", "loaded": ["b-HASH.js"], "foreign": ["b-HASH.js"], "ok": False}})
    assert check_variant({"variant_check": {"variant": "deployed", "loaded": [], "ok": None}})
    print("bg_summary self-test: ok")


if __name__ == "__main__":
    if sys.argv[1:] == ["--self-test"]:
        self_test()
    elif sys.argv[1] == "--check-variant":
        sys.exit(0 if check_variant(json.load(open(sys.argv[2]))) else 1)
    else:
        log = json.load(open(sys.argv[1]))
        print("\n".join(summarise(log)))
        sys.exit(0 if check_variant(log) else 1)
