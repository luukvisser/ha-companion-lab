"""Summarise the card's call timings from Home Assistant's recorder (read-only).

A measurement build of the card fires `advanced_camera_card_call_timing` events with
microphone_ms (call button to microphone ready), call_path_ms (microphone ready to the camera
hearing it) and total_ms, plus the camera and the path. This lists them and gives median, min and
max per camera and path.

  call-timing.py [--db PATH] [--anon] [minutes back]

  --db    the recorder database (default $HA_RECORDER_DB or /config/home-assistant_v2.db); opened
          read-only. With a Home Assistant in Docker, run it in that container (the recorder keeps
          a write-ahead log a read-only mount of the file cannot open), e.g.
          docker exec -i <ha container> python3 - --db /config/home-assistant_v2.db 60 < call-timing.py
  --anon  print a short hash instead of each camera entity (entity ids can carry names)
"""
import argparse
import datetime
import hashlib
import json
import os
import sqlite3
import statistics

parser = argparse.ArgumentParser()
parser.add_argument("--db", default=os.environ.get("HA_RECORDER_DB", "/config/home-assistant_v2.db"))
parser.add_argument("--anon", action="store_true")
parser.add_argument("minutes", nargs="?", type=float, default=60)
args = parser.parse_args()


def camera_label(camera: object) -> str:
    text = str(camera)
    return "camera-" + hashlib.sha256(text.encode()).hexdigest()[:8] if args.anon else text


db = sqlite3.connect(f"file:{args.db}?mode=ro", uri=True)
# A second cursor would be needed for any query inside the loop below: a new execute() on the
# cursor being iterated ends the loop after one row, silently.
rows = db.cursor().execute(
    """select e.time_fired_ts, d.shared_data from events e
       join event_types t on e.event_type_id = t.event_type_id
       left join event_data d on e.data_id = d.data_id
       where t.event_type = 'advanced_camera_card_call_timing'
         and e.time_fired_ts > strftime('%s','now') - ?
       order by e.time_fired_ts""",
    (args.minutes * 60,),
).fetchall()

by_path: dict[str, list[dict]] = {}
for ts, data in rows:
    d = json.loads(data or "{}")
    t = datetime.datetime.fromtimestamp(ts).strftime("%H:%M:%S")
    camera = camera_label(d.get("camera"))
    print(t, camera, d.get("path"), "microphone", d.get("microphone_ms"), "ms; call path",
          d.get("call_path_ms"), "ms; total", d.get("total_ms"), "ms")
    by_path.setdefault(f"{camera} {d.get('path')}", []).append(d)

if not rows:
    print(f"no call timings in the last {args.minutes:g} minutes")
for key, items in by_path.items():
    for field in ("microphone_ms", "call_path_ms", "total_ms"):
        values = [i[field] for i in items if isinstance(i.get(field), (int, float))]
        if values:
            print(f"{key:28} {field:14} n={len(values)} median={statistics.median(values):.0f} "
                  f"min={min(values)} max={max(values)}")
