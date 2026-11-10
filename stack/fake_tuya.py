"""A fake Tuya mobile API for the Philips Avent integration, so the test stack needs no cloud.

The integration talks to one endpoint, `POST https://<host>/api.json`, with the action in the form
field `a`. This answers the actions the integration uses (login with MFA, device discovery, device
state, data-point writes, signal strength, the P2P password) for one simulated monitor, keeps its
data points in memory, and logs every action without its parameters.

It never checks a password or a signature: any login with any MFA code succeeds, so nothing real
is ever needed. A second, plain-HTTP port (internal to the stack only) lets tests read and change
the monitor's data points, e.g. to raise a sound alert:

  GET  /lab/dps                 -> the current data points
  POST /lab/dps  {"207": 2350}  -> merge (a temperature of 23.5 C, as the integration reads it)

Settings (environment): FAKE_TUYA_CERT / FAKE_TUYA_KEY (TLS for the API port), FAKE_TUYA_DEVICE_ID,
FAKE_TUYA_DEVICE_NAME, FAKE_TUYA_API_HOST (the host the login reports as the account's API host).
"""
import base64
import json
import logging
import os
import secrets
import ssl

from aiohttp import web
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

logging.basicConfig(level=logging.INFO, format="%(asctime)s fake-tuya %(message)s")
LOG = logging.getLogger("fake-tuya")

DEVICE_ID = os.environ.get("FAKE_TUYA_DEVICE_ID", "labavent000000000001")
DEVICE_NAME = os.environ.get("FAKE_TUYA_DEVICE_NAME", "Lab baby monitor")
API_HOST = os.environ.get("FAKE_TUYA_API_HOST", "a1.tuyaeu.com")
UID = "lab" + secrets.token_hex(8)
SID = "lab" + secrets.token_hex(16)

# Data points as the integration's const.py names them; values typical for a quiet monitor.
DPS: dict[str, object] = {
    "138": False,  # night light
    "158": 50,  # night light brightness
    "207": 2150,  # temperature, hundredths of a degree C (the integration divides by 100)
    "208": 7070,  # temperature, hundredths of a degree F
    "134": True,  # motion detection switch
    "106": "1",  # motion sensitivity
    "139": True,  # sound detection switch
    "140": "1",  # sound sensitivity
    "201": "stop",  # lullaby control
    "209": 30,  # lullaby volume
    "246": "stop",  # lullaby state
    "237": False,  # privacy mode
    "205": "usb_power",  # power status
    "102": False,  # flip
}

# The RSA key the login encrypts the password with (the integration only needs a valid key).
_KEY = rsa.generate_private_key(public_exponent=65537, key_size=1024)
PB_KEY = base64.b64encode(
    _KEY.public_key().public_bytes(
        serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo
    )
).decode()

DEVICE = {
    "devId": DEVICE_ID,
    "name": DEVICE_NAME,
    "productId": "labproduct000000",
    "category": "sp",
}


def ok(result):
    return web.json_response({"success": True, "result": result, "t": 0})


def fail(code: str, msg: str):
    return web.json_response({"success": False, "errorCode": code, "errorMsg": msg})


def post_data(form) -> dict:
    try:
        return json.loads(form.get("postData") or "{}")
    except ValueError:
        return {}


async def api(request: web.Request) -> web.Response:
    form = await request.post()
    action = form.get("a", "")
    data = post_data(form)
    LOG.info("action %s", action)

    if action == "thing.m.user.username.token.get":
        return ok({"pbKey": PB_KEY, "token": secrets.token_hex(16), "exponent": "65537"})
    if action == "thing.m.user.email.password.login":
        try:
            mfa = json.loads(data.get("options") or "{}").get("mfaCode", "")
        except ValueError:
            mfa = ""
        if not mfa:
            # Like the real service: the first attempt asks for an emailed code.
            return fail("MFA_NEED_SEND_CODE", "Verification code needed")
        return ok(
            {
                "sid": SID,
                "uid": UID,
                "ecode": secrets.token_hex(8),
                "partnerIdentity": "p" + secrets.token_hex(4),
                "domain": {
                    "mobileApiUrl": f"https://{API_HOST}",
                    "mobileMqttsUrl": "m1.tuyaeu.com",
                    "regionCode": "EU",
                },
            }
        )
    if action == "thing.m.user.username.mfa.code.get":
        return ok(True)
    if action == "smartlife.m.user.info.get":
        return ok({"nickname": "Lab", "uid": UID})
    if action == "m.life.home.space.list":
        return ok([{"gid": 1001, "name": "Lab"}])
    if action == "tuya.m.location.get":
        return ok([{"name": "Lab room", "deviceList": [DEVICE]}])
    if action in ("tuya.m.my.group.device.list", "tuya.m.device.list.get"):
        return ok([DEVICE])
    if action == "tuya.m.device.get":
        if data.get("devId") != DEVICE_ID:
            return fail("DEVICE_NOT_EXIST", "No such device")
        # No localKey: the integration then skips its LAN client (no camera on any LAN).
        return ok({**DEVICE, "dps": dict(DPS), "isOnline": True})
    if action == "tuya.m.device.dp.publish":
        DPS.update(data.get("dps") or {})
        return ok(True)
    if action == "tuya.m.device.upgrade.rssi.info.query":
        return ok({"value": -48})
    if action == "smartlife.m.rtc.config.get":
        return ok({"password": "lab-p2p", "p2pConfig": {}})
    return fail("UNKNOWN_API", f"The fake does not implement {action}")


async def lab_get(_request: web.Request) -> web.Response:
    return web.json_response(DPS)


async def lab_set(request: web.Request) -> web.Response:
    DPS.update(await request.json())
    LOG.info("lab set data points %s", sorted(DPS))
    return web.json_response(DPS)


async def main() -> None:
    api_app = web.Application()
    api_app.router.add_post("/api.json", api)
    lab_app = web.Application()
    lab_app.router.add_get("/lab/dps", lab_get)
    lab_app.router.add_post("/lab/dps", lab_set)

    context = ssl.create_default_context(ssl.Purpose.CLIENT_AUTH)
    context.load_cert_chain(os.environ["FAKE_TUYA_CERT"], os.environ["FAKE_TUYA_KEY"])

    for app, port, tls in ((api_app, 443, context), (lab_app, 8080, None)):
        runner = web.AppRunner(app, access_log=None)
        await runner.setup()
        await web.TCPSite(runner, "0.0.0.0", port, ssl_context=tls).start()
    LOG.info("fake Tuya API on 443 (TLS), lab control on 8080")
    import asyncio

    await asyncio.Event().wait()


if __name__ == "__main__":
    import asyncio

    asyncio.run(main())
