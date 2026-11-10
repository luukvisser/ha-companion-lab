"""First start of the lab's Home Assistant: onboarding and a token; with the Avent add-on (a fourth
argument `avent`) also the Avent integration against the fake Tuya API.

Run by stack.sh in the stack image (host network, against the proxy on 127.0.0.1). Steps, each
skipped when already done:

1. Onboarding: an owner with a random password (written to /data/owner-password, mode 600),
   then the core-config, analytics and integration steps.
2. A long-lived access token for the lab's scripts (/data/token, mode 600).
3. The Philips Avent integration through its own config flow, against the fake Tuya API (any
   e-mail, password and MFA code work there), then its options: the camera stream from the
   simulated bridge, talkback on, LAN streaming off (no camera on any LAN).

Prints nothing secret: no password, no token, no session.

  onboard.py <HA URL> <bridge host> <bridge port>
"""
import asyncio
import json
import os
import secrets
import sys

import aiohttp

HA, BRIDGE_HOST, BRIDGE_PORT = sys.argv[1].rstrip("/"), sys.argv[2], int(sys.argv[3])
AVENT = sys.argv[4:5] == ["avent"]
CLIENT_ID = HA + "/"
DATA = "/data"


def save(name: str, value: str) -> None:
    path = os.path.join(DATA, name)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as f:
        f.write(value + "\n")


def load(name: str) -> str | None:
    try:
        with open(os.path.join(DATA, name)) as f:
            return f.read().strip() or None
    except FileNotFoundError:
        return None


async def wait_for_ha(s: aiohttp.ClientSession) -> list:
    for _ in range(180):
        try:
            async with s.get(f"{HA}/api/onboarding") as r:
                if r.status == 200:
                    return await r.json()
                if r.status == 404:
                    # HA drops the onboarding view once onboarding is complete.
                    return [{"step": "user", "done": True}]
        except aiohttp.ClientError:
            pass
        await asyncio.sleep(2)
    raise SystemExit("Home Assistant did not come up within 6 minutes")


async def onboard(s: aiohttp.ClientSession, steps: list) -> str | None:
    done = {step["step"]: step["done"] for step in steps}
    if done.get("user"):
        return None
    password = secrets.token_hex(16)
    async with s.post(
        f"{HA}/api/onboarding/users",
        json={"client_id": CLIENT_ID, "name": "Lab owner", "username": "lab-owner",
              "password": password, "language": "en"},
    ) as r:
        r.raise_for_status()
        auth_code = (await r.json())["auth_code"]
    save("owner-password", password)
    async with s.post(
        f"{HA}/auth/token",
        data={"grant_type": "authorization_code", "code": auth_code, "client_id": CLIENT_ID},
    ) as r:
        r.raise_for_status()
        access = (await r.json())["access_token"]
    headers = {"Authorization": f"Bearer {access}"}
    for step, body in (
        ("core_config", {}),
        ("analytics", {}),
        ("integration", {"client_id": CLIENT_ID, "redirect_uri": CLIENT_ID}),
    ):
        async with s.post(f"{HA}/api/onboarding/{step}", json=body, headers=headers) as r:
            if r.status not in (200, 403):  # 403: that step was already done
                raise SystemExit(f"onboarding step {step} failed: HTTP {r.status}")
    print("onboarding done: owner 'lab-owner' (password in the data folder)")
    return access


async def long_lived_token(s: aiohttp.ClientSession, access: str) -> str:
    async with s.ws_connect(f"{HA.replace('http', 'ws', 1)}/api/websocket") as ws:
        await ws.receive_json()
        await ws.send_json({"type": "auth", "access_token": access})
        assert (await ws.receive_json())["type"] == "auth_ok"
        await ws.send_json({"id": 1, "type": "auth/long_lived_access_token",
                            "client_name": "ha-companion-lab", "lifespan": 3650})
        r = await ws.receive_json()
        if not r.get("success"):
            raise SystemExit(f"could not create a token: {r.get('error')}")
        return r["result"]


async def flow_step(s, headers, url, body) -> dict:
    async with s.post(url, json=body, headers=headers) as r:
        result = await r.json(content_type=None)
        if r.status >= 400:
            raise SystemExit(f"config flow failed: HTTP {r.status} {json.dumps(result)[:300]}")
        return result


async def add_integration(s: aiohttp.ClientSession, token: str) -> str:
    headers = {"Authorization": f"Bearer {token}"}
    async with s.get(f"{HA}/api/config/config_entries/entry", headers=headers) as r:
        entries = [e for e in await r.json() if e["domain"] == "philips_avent"]
    if not entries:
        base = f"{HA}/api/config/config_entries/flow"
        # Right after a (re)start HA may not offer the custom integration's flow yet.
        for _ in range(60):
            async with s.post(base, json={"handler": "philips_avent"}, headers=headers) as r:
                step = await r.json(content_type=None)
                if r.status != 404:
                    break
            await asyncio.sleep(3)
        if "flow_id" not in step:
            raise SystemExit(f"the Avent config flow did not start: {json.dumps(step)[:300]}")
        if step.get("step_id") == "user":
            step = await flow_step(s, headers, f"{base}/{step['flow_id']}", {
                "email": "lab@example.invalid", "password": secrets.token_hex(8), "country": "NL"})
        if step.get("step_id") == "mfa":
            step = await flow_step(s, headers, f"{base}/{step['flow_id']}", {"mfa_code": "000000"})
        if step.get("type") != "create_entry":
            raise SystemExit(f"the Avent config flow ended at {step.get('step_id')}: "
                             f"{json.dumps(step.get('errors'))}")
        entry_id = step["result"]["entry_id"]
        print("Avent integration added (against the fake Tuya API)")
    else:
        entry_id = entries[0]["entry_id"]
    base = f"{HA}/api/config/config_entries/options/flow"
    step = await flow_step(s, headers, base, {"handler": entry_id})
    if step.get("type") == "form":
        step = await flow_step(s, headers, f"{base}/{step['flow_id']}", {
            "bridge_host": BRIDGE_HOST, "bridge_port": BRIDGE_PORT,
            "talkback": True, "lan_streaming": False})
    if step.get("type") != "create_entry":
        raise SystemExit(f"the Avent options flow ended at {step.get('step_id')} "
                         f"({step.get('type')}): {json.dumps(step.get('errors'))}")
    print(f"Avent options: bridge {BRIDGE_HOST}:{BRIDGE_PORT}, talkback on, LAN streaming off")
    return entry_id


async def wait_loaded(s: aiohttp.ClientSession, headers: dict, entry_id: str) -> None:
    """The options flow reloads the entry: wait until it is loaded again."""
    state = None
    for _ in range(60):
        async with s.get(f"{HA}/api/config/config_entries/entry", headers=headers) as r:
            state = next((e["state"] for e in await r.json() if e["entry_id"] == entry_id), None)
        if state == "loaded":
            return
        await asyncio.sleep(2)
    raise SystemExit(f"the Avent entry did not load again after its options (state {state})")


async def entry_cameras(s: aiohttp.ClientSession, token: str, entry_id: str) -> tuple[list, list]:
    """The entities of this config entry (entity registry), and its cameras."""
    async with s.ws_connect(f"{HA.replace('http', 'ws', 1)}/api/websocket") as ws:
        await ws.receive_json()
        await ws.send_json({"type": "auth", "access_token": token})
        if (await ws.receive_json()).get("type") != "auth_ok":
            raise SystemExit("websocket authentication failed")
        await ws.send_json({"id": 1, "type": "config/entity_registry/list"})
        r = await ws.receive_json()
    if not r.get("success"):
        raise SystemExit(f"could not list the entity registry: {r.get('error')}")
    mine = sorted(e["entity_id"] for e in r["result"] if e.get("config_entry_id") == entry_id)
    return mine, [e for e in mine if e.startswith("camera.")]


async def main() -> None:
    async with aiohttp.ClientSession() as s:
        steps = await wait_for_ha(s)
        access = await onboard(s, steps)
        token = load("token")
        if not token:
            if not access:
                raise SystemExit("HA is onboarded but /data/token is missing: reset the stack")
            token = await long_lived_token(s, access)
            save("token", token)
            print("long-lived token written to the data folder")
        if not AVENT:
            return
        entry_id = await add_integration(s, token)
        headers = {"Authorization": f"Bearer {token}"}
        await wait_loaded(s, headers, entry_id)
        avent, cameras = await entry_cameras(s, token, entry_id)
        if not cameras:
            raise SystemExit(f"the Avent entry has {len(avent)} entities but no camera")
        save("camera-entity", cameras[0])
        print(f"{len(avent)} Avent entities; camera: {cameras[0]}")


asyncio.run(main())
