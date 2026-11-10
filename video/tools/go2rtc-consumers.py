"""Watch who uses go2rtc's streams: per stream, its producers and its consumers' kinds and media
directions, printed each time something changes. Useful to see when a card opens or closes a
stream, a second viewer joins, or talk-back (a "sendonly" audio consumer) starts.

  go2rtc-consumers.py [--url URL] [--match TEXT] [--anon] [seconds]

  --url     go2rtc's API (default $GO2RTC_URL or http://127.0.0.1:1984)
  --match   only streams whose name contains TEXT
  --anon    print a short hash instead of each stream name (stream names can carry camera or
            room names)
  seconds   how long to watch (default: one snapshot)

Credentials, if go2rtc wants them: $GO2RTC_USER and the password in the file $GO2RTC_PASSWORD_FILE
(never on the command line). Nothing printed contains a URL, an address or a credential: go2rtc's
own answers can carry source URLs with passwords, so only kinds and directions are printed, and
any text that still looks like a URL with credentials is masked.
"""
import argparse
import base64
import datetime
import hashlib
import json
import os
import re
import sys
import time
import urllib.request

CRED = re.compile(r"(\w+://)[^/@\s]*@")

parser = argparse.ArgumentParser()
parser.add_argument("--url", default=os.environ.get("GO2RTC_URL", "http://127.0.0.1:1984"))
parser.add_argument("--match", default="")
parser.add_argument("--anon", action="store_true")
parser.add_argument("--self-test", action="store_true", help="check the credential masking and exit")
parser.add_argument("seconds", nargs="?", type=float, default=0)
args = parser.parse_args()

headers = {}
if os.environ.get("GO2RTC_USER") and os.environ.get("GO2RTC_PASSWORD_FILE"):
    with open(os.environ["GO2RTC_PASSWORD_FILE"]) as f:
        token = base64.b64encode(f"{os.environ['GO2RTC_USER']}:{f.read().strip()}".encode()).decode()
    headers["Authorization"] = f"Basic {token}"


def mask(text: str) -> str:
    return CRED.sub(r"\1***@", text)


if args.self_test:
    for raw, want in [
        ("rtsp://user:secret@10.0.0.5:554/s", "rtsp://***@10.0.0.5:554/s"),
        ("ffmpeg:rtsp://a:b@h/x#video=copy", "ffmpeg:rtsp://***@h/x#video=copy"),
        ("rtsp://10.0.0.5:554/s", "rtsp://10.0.0.5:554/s"),
    ]:
        got = mask(raw)
        assert got == want and "secret" not in got, (raw, got)
    print("go2rtc-consumers mask self-test: ok")
    sys.exit(0)


def label(name: str) -> str:
    return "stream-" + hashlib.sha256(name.encode()).hexdigest()[:8] if args.anon else mask(name)


def snapshot() -> dict:
    req = urllib.request.Request(args.url.rstrip("/") + "/api/streams", headers=headers)
    streams = json.load(urllib.request.urlopen(req, timeout=5))
    out = {}
    for name, info in sorted((streams or {}).items()):
        if args.match and args.match not in name:
            continue
        consumers = []
        for c in (info or {}).get("consumers") or []:
            medias = [":".join(p.strip() for p in str(m).split(",")[:2]) for m in c.get("medias") or []]
            kind = c.get("format_name") or c.get("type") or "?"
            consumers.append(mask(f"{kind}[{','.join(medias)}]"))
        producers = len((info or {}).get("producers") or [])
        out[label(name)] = f"{producers} producer(s); {len(consumers)} consumer(s): " + " | ".join(consumers)
    return out


last = None
end = time.time() + args.seconds
while True:
    try:
        now = snapshot()
    except Exception as err:  # noqa: BLE001 - report and go on watching
        now = {"error": type(err).__name__}
    if now != last:
        print(datetime.datetime.now().strftime("%H:%M:%S"), json.dumps(now, indent=1), flush=True)
        last = now
    if time.time() >= end:
        break
    time.sleep(1)
sys.exit(0)
