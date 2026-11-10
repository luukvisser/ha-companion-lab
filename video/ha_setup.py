"""Home Assistant side of the test camera, through HA's own API (no restart, no files edited).

  ha_setup.py camera <rtsp url>        adds a Generic Camera on the stream ("Test pattern",
                                       camera.test_pattern), through the config flow.
  ha_setup.py dashboard '<camera JSON>' ['<card extras JSON>']
                                       creates (once) a storage dashboard `test-dashboard`, hidden
                                       from the sidebar and not admin-only, and sets its one
                                       advanced-camera-card to that camera entry plus extras.
  ha_setup.py dashboard-card '<card JSON>'
                                       the same dashboard with exactly this card (e.g. Home
                                       Assistant's own `picture-entity` before a card build is
                                       installed).
  ha_setup.py resource <url>           adds or updates the dashboard resource (JavaScript module)
                                       whose path matches <url> up to its query string, e.g.
                                       /local/community/advanced-camera-card/advanced-camera-card.js?v=7
  ha_setup.py labs [<domain> <feature> on|off]
                                       lists Home Assistant's Labs preview features and their state,
                                       or switches one (e.g. `labs camera two_way_audio on`: the
                                       camera's two-way audio, which the card's `ha` provider needs).
  ha_setup.py show                     prints, as JSON, the test dashboard's card configuration and
                                       the card's dashboard resource (for a result's meta.json).
  ha_setup.py remove [--dashboard]     removes the camera entry again; with --dashboard also the
                                       test dashboard (which another layer, e.g. stack,
                                       may own: it is kept unless asked for).

Reads HA_URL from the environment and the token from /token (a file mounted read-only by
video/ha-setup.sh). Never prints the token.
"""
import asyncio
import json
import os
import sys
import urllib.error
import urllib.request

import websockets

HA_URL = os.environ["HA_URL"].rstrip("/")
TOKEN = open("/token").read().strip()
TITLE = "Test pattern"


def rest(method, path, body=None):
    req = urllib.request.Request(
        HA_URL + path,
        data=json.dumps(body).encode() if body is not None else None,
        method=method,
        headers={"Authorization": "Bearer " + TOKEN, "Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req) as r:
        return json.load(r)


async def ws_calls(calls):
    url = HA_URL.replace("http", "ws", 1) + "/api/websocket"
    async with websockets.connect(url, max_size=None) as ws:
        await ws.recv()
        await ws.send(json.dumps({"type": "auth", "access_token": TOKEN}))
        assert json.loads(await ws.recv())["type"] == "auth_ok", "authentication failed"
        out = []
        for n, call in enumerate(calls, 1):
            await ws.send(json.dumps({"id": n, **call}))
            while True:
                r = json.loads(await ws.recv())
                if r.get("id") == n:
                    out.append(r)
                    break
        return out


def check(results, what):
    """Exit non-zero, naming each failed call, unless every websocket call succeeded."""
    failed = [f"{r.get('error', {}).get('message', r.get('error'))}" for r in results if not r.get("success")]
    if failed:
        sys.exit(f"{what} failed: " + "; ".join(failed))


def add_camera(rtsp):
    listed = asyncio.run(ws_calls([{"type": "config/entity_registry/list"}]))
    check(listed, "reading the entity registry")
    if any(e["entity_id"] == "camera.test_pattern" for e in listed[0]["result"]):
        print("camera.test_pattern: already there (remove it first to change its stream)")
        return
    flow = rest("POST", "/api/config/config_entries/flow", {"handler": "generic", "show_advanced_options": True})
    step = rest("POST", f"/api/config/config_entries/flow/{flow['flow_id']}", {
        "stream_source": rtsp,
        "advanced": {"framerate": 2, "verify_ssl": False, "rtsp_transport": "tcp"},
    })
    if step.get("step_id") != "user_confirm":
        sys.exit(f"the stream was not accepted: {step.get('errors')}")
    done = rest("POST", f"/api/config/config_entries/flow/{flow['flow_id']}", {"confirmed_ok": True})
    entry_id = done["result"]["entry_id"]
    # The flow names the entity after the address; rename entity, device and entry.
    listed = asyncio.run(ws_calls([{"type": "config/entity_registry/list"}]))
    check(listed, "reading the entity registry")
    ent = [e for e in listed[0]["result"] if e.get("config_entry_id") == entry_id][0]
    r = asyncio.run(ws_calls([
        {"type": "config/entity_registry/update", "entity_id": ent["entity_id"],
         "new_entity_id": "camera.test_pattern", "name": None},
        {"type": "config/device_registry/update", "device_id": ent["device_id"], "name_by_user": TITLE},
        {"type": "config_entries/update", "entry_id": entry_id, "title": TITLE},
    ]))
    check(r, "renaming the camera to camera.test_pattern (is the id taken? run `remove` first)")
    print("camera.test_pattern: added")


def set_dashboard(camera, extras, card=None):
    card = card or {"type": "custom:advanced-camera-card", "cameras": [camera], **extras}
    config = {"title": "Test", "views": [{"title": "Test", "path": "test", "cards": [card]}]}
    listed = asyncio.run(ws_calls([{"type": "lovelace/dashboards/list"}]))
    check(listed, "reading the dashboards")
    existing = listed[0]["result"]
    calls = []
    if not any(d["url_path"] == "test-dashboard" for d in existing):
        calls.append({"type": "lovelace/dashboards/create", "url_path": "test-dashboard", "title": "Test",
                      "icon": "mdi:test-tube", "show_in_sidebar": False, "require_admin": False,
                      "mode": "storage"})
    calls.append({"type": "lovelace/config/save", "url_path": "test-dashboard", "config": config})
    r = asyncio.run(ws_calls(calls))
    check(r, "saving the test dashboard")
    print("test dashboard set:", json.dumps(card)[:200])


def set_resource(url):
    """One dashboard resource per path: create it, or point the existing one at the new version."""
    path = url.split("?", 1)[0]
    existing = asyncio.run(ws_calls([{"type": "lovelace/resources"}]))[0]
    if not existing.get("success"):
        sys.exit(f"cannot read the dashboard resources: {existing.get('error')}")
    same = [r for r in existing["result"] if r["url"].split("?", 1)[0] == path]
    if same:
        call = {"type": "lovelace/resources/update", "resource_id": same[0]["id"],
                "res_type": "module", "url": url}
    else:
        call = {"type": "lovelace/resources/create", "res_type": "module", "url": url}
    r = asyncio.run(ws_calls([call]))[0]
    if not r.get("success"):
        sys.exit(f"resource not set: {r.get('error')}")
    print(f"resource {'updated' if same else 'added'}: {url}")


def show():
    r = asyncio.run(ws_calls([{"type": "lovelace/config", "url_path": "test-dashboard"},
                              {"type": "lovelace/resources"}]))
    cards = []
    if r[0].get("success"):
        cards = [c for v in r[0]["result"].get("views", []) for c in v.get("cards", [])]
    res = [x["url"] for x in r[1].get("result", []) if "advanced-camera-card" in x["url"]] if r[1].get("success") else []
    print(json.dumps({"dashboard_card": cards[0] if cards else None, "card_resource": res[0] if res else None}))


def labs(args):
    if args:
        domain, feature, state = args
        if state not in ("on", "off"):
            sys.exit("labs: the state is on or off")
        r = asyncio.run(ws_calls([{"type": "labs/update", "domain": domain, "preview_feature": feature,
                                   "enabled": state == "on"}]))
        check(r, f"switching the Labs feature {domain}.{feature}")
    r = asyncio.run(ws_calls([{"type": "labs/list"}]))
    check(r, "listing the Labs features")
    for f in r[0]["result"].get("features", []):
        print(f"{f.get('domain')}.{f.get('preview_feature')}: {'on' if f.get('enabled') else 'off'}")


def remove(dashboard=False):
    """Removes the test camera's entry (REST, as HA's own frontend does) and, when asked, the test
    dashboard; reports each result and exits non-zero if anything failed."""
    failed = 0
    # Only the test camera's entry: other Generic cameras are not ours.
    entries = [e for e in rest("GET", "/api/config/config_entries/entry?domain=generic") if e["title"] == TITLE]
    for e in entries:
        try:
            r = rest("DELETE", f"/api/config/config_entries/entry/{e['entry_id']}")
            print(f"camera entry removed (require_restart: {r.get('require_restart')})")
        except urllib.error.HTTPError as err:
            failed += 1
            print(f"camera entry NOT removed: HTTP {err.code}")
    calls = []
    if dashboard:
        listed = asyncio.run(ws_calls([{"type": "lovelace/dashboards/list"}]))
        check(listed, "reading the dashboards")
        dashboards = listed[0]["result"]
        calls = [{"type": "lovelace/dashboards/delete", "dashboard_id": d["id"]}
                 for d in dashboards if d["url_path"] == "test-dashboard"]
    for r in (asyncio.run(ws_calls(calls)) if calls else []):
        if r.get("success"):
            print("test dashboard removed")
        else:
            failed += 1
            print(f"test dashboard NOT removed: {r.get('error')}")
    if not entries and not calls:
        print("nothing to remove")
    if failed:
        sys.exit(1)


if __name__ == "__main__":
    cmd = sys.argv[1]
    if cmd == "camera":
        add_camera(sys.argv[2])
    elif cmd == "dashboard":
        set_dashboard(json.loads(sys.argv[2]), json.loads(sys.argv[3]) if len(sys.argv) > 3 else {})
    elif cmd == "dashboard-card":
        set_dashboard(None, {}, json.loads(sys.argv[2]))
    elif cmd == "resource":
        set_resource(sys.argv[2])
    elif cmd == "remove":
        remove(dashboard="--dashboard" in sys.argv[2:])
    elif cmd == "show":
        show()
    elif cmd == "labs":
        labs(sys.argv[2:])
    else:
        sys.exit(__doc__)
