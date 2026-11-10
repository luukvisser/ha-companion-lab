"""A limited Home Assistant user for the lab's Companion app, through HA's websocket API.

  ha_test_user.py create   creates the user (not an admin, local network only) with a random hex
                           password written to /secret (mode 600 on the host); does nothing if it
                           already exists.
  ha_test_user.py remove   deletes the user (and with it its sessions and devices' logins).
  ha_test_user.py status   says whether it exists and how it is set up.

Needs an admin user's long-lived token (/token). Only Home Assistant's owner may change another
user's password, so to rotate it: remove, then create. Never prints the token or the password.
"""
import asyncio
import json
import os
import secrets
import sys

import websockets

HA_URL = os.environ["HA_URL"].rstrip("/")
NAME = os.environ.get("TEST_USER_NAME", "Companion lab")
USERNAME = os.environ.get("TEST_USER", "companion-lab")
TOKEN = open("/token").read().strip()


class CallError(Exception):
    """A websocket command Home Assistant answered with an error."""


WS_URL = HA_URL.replace("http", "ws", 1) + "/api/websocket"


async def connect():
    ws = await websockets.connect(WS_URL, max_size=None)
    await ws.recv()
    await ws.send(json.dumps({"type": "auth", "access_token": TOKEN}))
    if json.loads(await ws.recv())["type"] != "auth_ok":
        await ws.close()
        raise SystemExit("authentication failed")
    n = 0

    async def call(**msg):
        nonlocal n
        n += 1
        await ws.send(json.dumps({"id": n, **msg}))
        while True:
            r = json.loads(await ws.recv())
            if r.get("id") == n:
                if not r.get("success"):
                    raise CallError(f"{msg['type']} failed: {r.get('error')}")
                return r.get("result")

    return ws, call


async def delete_user(call, user_id: str) -> None:
    """Delete a user this script made; on a broken connection, through a fresh one."""
    try:
        await call(type="config/auth/delete", user_id=user_id)
    except (CallError, websockets.WebSocketException, OSError):
        ws, fresh = await connect()
        try:
            await fresh(type="config/auth/delete", user_id=user_id)
        finally:
            await ws.close()


async def main(action: str) -> None:
    ws, call = await connect()
    try:
        await run(action, call)
    finally:
        await ws.close()


async def run(action: str, call) -> None:
    if True:

        users = await call(type="config/auth/list")
        # The test user by its display name or its login name: a login taken by a user with another
        # display name is the same login, and creating it again would fail halfway.
        existing = [u for u in users if u.get("name") == NAME or u.get("username") == USERNAME]

        def limited(u) -> list[str]:
            """What is wrong with a user meant to have limited rights (empty: nothing)."""
            problems = []
            if u.get("is_owner"):
                problems.append("is the owner")
            if u.get("group_ids") != ["system-users"]:
                problems.append(f"groups {u.get('group_ids')} instead of only system-users")
            if not u.get("local_only"):
                problems.append("can log in from outside the local network")
            if u.get("system_generated"):
                problems.append("is a system user")
            return problems

        if action == "status":
            for u in existing:
                print({k: u.get(k) for k in ("name", "username", "is_owner", "is_active", "local_only", "group_ids")})
                problems = limited(u)
                print("rights: limited as intended" if not problems else "rights NOT limited: " + "; ".join(problems))
                if not u.get("username"):
                    print("BROKEN: no login (an interrupted create); `create` replaces it")
            if not existing:
                print("no test user")
        elif action == "remove":
            for u in existing:
                problems = limited(u)
                if problems:
                    raise SystemExit(f"'{u['name']}' has more rights than a test user (" + "; ".join(problems)
                                     + "): not deleting it; this script only removes the limited user it made")
                await call(type="config/auth/delete", user_id=u["id"])
                print("removed", u["name"])
            if not existing:
                print("no test user to remove")
        elif action == "create":
            if existing:
                problems = [p for u in existing for p in limited(u)]
                if problems:
                    raise SystemExit(f"a user named '{NAME}' or with login '{USERNAME}' exists with more rights than a test user: "
                                     + "; ".join(problems) + ". Not touching it; pick another TEST_USER_NAME.")
                broken = [u for u in existing if not u.get("username")]
                if not broken:
                    print("test user exists, with limited rights; to get a new password: remove, then create")
                    return
                # A limited user without a login (left by an interrupted earlier run): the app could
                # never log in with it, so it is ours to replace.
                for u in broken:
                    await delete_user(call, u["id"])
                    print(f"removed '{u['name']}': a limited user without a login (an interrupted earlier create)")
            password = secrets.token_hex(16)
            user = (await call(type="config/auth/create", name=NAME, group_ids=["system-users"], local_only=True))["user"]
            done = False
            try:
                await call(type="config/auth_provider/homeassistant/create", user_id=user["id"], username=USERNAME,
                           password=password)
                if os.environ.get("LAB_TEST_FAIL_AFTER_CREATE"):
                    raise RuntimeError("injected failure (LAB_TEST_FAIL_AFTER_CREATE)")
                # Check the rights as Home Assistant reports them, not as asked for.
                made = [u for u in await call(type="config/auth/list") if u["id"] == user["id"]]
                problems = limited(made[0]) if made else ["not found after creating"]
                if problems or not made[0].get("is_active") or made[0].get("username") != USERNAME:
                    raise SystemExit("the new user did not end up with limited rights and its login ("
                                     + "; ".join(problems or ["inactive or no login"]) + "); it was deleted again")
                with open("/secret", "w") as f:
                    f.write(password + "\n")
                done = True
            finally:
                # Whatever stopped it (an error, a dropped connection, Ctrl-C, a failed write):
                # never leave a half-made user behind, a later `create` would trust it.
                if not done:
                    await delete_user(call, user["id"])
                    print(f"the half-made user '{NAME}' was deleted again", file=sys.stderr)
            print(f"created '{NAME}' (username {USERNAME}); checked: not the owner, only group system-users "
                  "(not an admin), local network only, active, login set; password written to the password file")
        else:
            raise SystemExit(__doc__)


try:
    asyncio.run(main(sys.argv[1] if len(sys.argv) > 1 else ""))
except CallError as err:
    raise SystemExit(str(err)) from None
