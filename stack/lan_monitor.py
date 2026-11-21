"""A fake Philips Avent baby monitor on the Tuya LAN protocol (3.3, 3.4 or 3.5), for the lab only.

It plays the device side of the protocol as tinytuya (the Avent integration's LAN client) speaks it,
so the integration's LAN handling can be measured in the lab's Home Assistant without a real camera:
discovery broadcasts on UDP 6667, sessions on TCP 6668 (the 3.4/3.5 session-key handshake
included), heartbeats, status queries, writes and pushed data points, and faults on command. It
proves how the integration handles these frames, not how real firmware behaves: where the real
monitors were measured, the defaults follow those measurements (below); the rest is assumed.

Measured on real monitors and copied here:
- an SCD951 (3.4) accepts at most 3 sessions on 6668 (02-11-2026): LAN_MONITOR_MAX_SESSIONS=3;
- a wrong-key handshake holds its session about 10 s before the SCD951 drops it (02-11-2026):
  LAN_MONITOR_WRONG_KEY_HOLD=10;
- an SCD923 on 3.3 answers DP_QUERY with the text "json obj data unvalid" (07-11-2026):
  LAN_MONITOR_QUERY33=unvalid.
Assumed (not measured): how a 4th session is refused (LAN_MONITOR_REFUSE: `close` accepts and
closes at once, `reset` answers with a TCP reset); that a held wrong-key session counts toward the
session limit, and that the drop after the hold is a normal close (FIN), not a reset; that a 3.3
frame under a wrong key is ignored without a hold; the return code of the "data unvalid" frame (1),
and that it is sent encrypted like any 3.3 answer; empty heartbeat and write acks; that a write is
echoed as a push to every session; and that UPDATEDPS (command 18, which "crashes this firmware" per
the integration's lan.py) drops the session.

Settings (environment):
  LAN_MONITOR_KEYS_FILE   JSON {"monitors": [{"id", "key", "name", "product"}, ...]} (stack.sh writes it)
  LAN_MONITOR_ID          which entry of that file this monitor is
  LAN_MONITOR_VERSION     3.3, 3.4 or 3.5 (default 3.4)
  LAN_MONITOR_DISCOVERY   on|off (default on): broadcasts every LAN_MONITOR_DISCOVERY_INTERVAL s (5)
                          to LAN_MONITOR_DISCOVERY_TO (default 172.31.240.255, the lab network)
  LAN_MONITOR_MAX_SESSIONS, LAN_MONITOR_WRONG_KEY_HOLD, LAN_MONITOR_REFUSE, LAN_MONITOR_QUERY33
                          (unvalid|state|silent), LAN_MONITOR_TCP_PORT (6668),
                          LAN_MONITOR_CONTROL_PORT (8080)

Control (plain HTTP inside the lab network; stack.sh lan ... wraps it):
  GET  /lab/state                         version, faults, sessions, data points
  POST /lab/dps        {"207": 2450}      merge and push to every session
  POST /lab/fault      {"fault": F}       silent (keep TCP, answer nothing), refuse (no new
                                          sessions), close (close every session now), normal
  POST /lab/version    {"version": "3.5"} a firmware update: every session closes, the new one speaks it
  POST /lab/discovery  {"on": false}      stop or start the broadcasts

  --self-test   tinytuya as the client against this fake on 127.0.0.1: frames per version, the
                discovery announcement's encoding (no UDP is sent), the session limit, the
                wrong-key hold and the faults (needs tinytuya, as in the lab's Home Assistant
                image; CI runs it in images.yml)
"""
import asyncio
import hmac
import json
import logging
import os
import socket
import struct
import sys
import time
from hashlib import sha256

import tinytuya
from tinytuya import AESCipher, TuyaMessage, pack_message, parse_header, unpack_message

LOG = logging.getLogger("lan-monitor")
P55, P66 = tinytuya.PREFIX_55AA_VALUE, tinytuya.PREFIX_6699_VALUE
NAMES = {getattr(tinytuya, n): n for n in ("CONTROL", "HEART_BEAT", "DP_QUERY", "CONTROL_NEW", "DP_QUERY_NEW",
                                           "UPDATEDPS")}
VERSIONS = (3.3, 3.4, 3.5)
UNVALID = b"json obj data unvalid"

# Data points as the integration's const.py names them; values typical for a quiet monitor
# (the same as fake_tuya.py's cloud copy, which this fake does not share: LAN and cloud are separate).
DEFAULT_DPS = {"138": False, "158": 50, "207": 2150, "208": 7070, "134": True, "106": "1", "139": True,
               "140": "1", "201": "stop", "209": 30, "246": "stop", "237": False, "205": "usb_power", "102": False}


def env(name, default):
    return os.environ.get(name, default)


class Session:
    def __init__(self, monitor, reader, writer):
        self.monitor, self.reader, self.writer = monitor, reader, writer
        self.version = monitor.version
        self.key = monitor.key  # the session key once negotiated (3.4 and up)
        self.keyed = self.version < 3.4  # 3.3 has no handshake
        self.nonce = b""
        self.seq = 0
        self.peer = "%s:%s" % writer.get_extra_info("peername")[:2]
        self.since = time.monotonic()

    def frame(self, cmd, payload=b"", seq=None, retcode=0, header=False):
        """A device-to-client frame, as tinytuya's _receive and _decode_payload read it."""
        if seq is None:
            self.seq += 1
            seq = self.seq
        version = self.version
        if header and payload:
            payload = str(version).encode() + b"\0" * 12 + payload
        if version >= 3.5:
            msg = TuyaMessage(seq, cmd, retcode, payload, 0, True, P66, os.urandom(12))
            return pack_message(msg, hmac_key=self.key)
        # 55AA: a 4-byte return code, then the payload encrypted with the key (3.3: the version
        # header outside the encryption, 3.4: inside it), CRC (3.3) or HMAC (3.4).
        if payload:
            if version >= 3.4:
                payload = AESCipher(self.key).encrypt(payload, False)
            else:
                plain = payload[15:] if header else payload
                payload = (payload[:15] if header else b"") + AESCipher(self.key).encrypt(plain, False)
        msg = TuyaMessage(seq, cmd, 0, struct.pack(">I", retcode) + payload, 0, True, P55, None)
        return pack_message(msg, hmac_key=self.key if version >= 3.4 else None)

    def send(self, data):
        if not self.writer.is_closing():
            self.writer.write(data)

    def push(self, dps):
        body = {"protocol": 4, "t": int(time.time()), "data": {"dps": dps}} if self.version >= 3.4 else \
            {"devId": self.monitor.id, "dps": dps, "t": int(time.time())}
        self.send(self.frame(tinytuya.STATUS, json.dumps(body, separators=(",", ":")).encode(), header=True))

    def payload(self, msg):
        """The client's JSON payload in clear (its version header removed)."""
        data = msg.payload
        if self.version < 3.5:
            if self.version < 3.4 and data.startswith(b"3.3"):
                data = data[15:]
            data = AESCipher(self.key).decrypt(data, False, decode_text=False)
        if data[:3] in (b"3.3", b"3.4", b"3.5"):
            data = data[15:]
        return json.loads(data) if data else {}


class Monitor:
    def __init__(self, entry, version):
        self.id, self.name, self.product = entry["id"], entry.get("name", ""), entry.get("product", "")
        self.key = entry["key"].encode()
        self.version = version
        self.dps = dict(DEFAULT_DPS)
        self.sessions = set()
        self.fault = "normal"  # normal | silent | refuse
        self.discovery = env("LAN_MONITOR_DISCOVERY", "on") == "on"
        self.discovery_to = env("LAN_MONITOR_DISCOVERY_TO", "172.31.240.255")
        self.discovery_interval = float(env("LAN_MONITOR_DISCOVERY_INTERVAL", "5"))
        self.max_sessions = int(env("LAN_MONITOR_MAX_SESSIONS", "3"))
        self.hold = float(env("LAN_MONITOR_WRONG_KEY_HOLD", "10"))
        self.refuse = env("LAN_MONITOR_REFUSE", "close")
        self.query33 = env("LAN_MONITOR_QUERY33", "unvalid")
        self.refused = 0

    # --- TCP 6668 -------------------------------------------------------------------------------
    async def handle(self, reader, writer):
        peer = "%s:%s" % writer.get_extra_info("peername")[:2]
        if self.fault == "refuse" or len(self.sessions) >= self.max_sessions:
            self.refused += 1
            LOG.info("session from %s refused (%d open, fault %s, %s)", peer, len(self.sessions), self.fault,
                     self.refuse)
            if self.refuse == "reset":
                writer.get_extra_info("socket").setsockopt(socket.SOL_SOCKET, socket.SO_LINGER,
                                                           struct.pack("ii", 1, 0))
            writer.close()
            return
        s = Session(self, reader, writer)
        self.sessions.add(s)
        LOG.info("session from %s opened at %s (%d open)", peer, s.version, len(self.sessions))
        reason = "closed by the client"
        try:
            while True:
                try:
                    raw = await read_frame(reader)
                except (asyncio.IncompleteReadError, ConnectionError):
                    break
                except ValueError as ex:
                    reason = "unreadable stream (%s)" % ex
                    break
                if self.fault == "silent":
                    continue
                if not await self.answer(s, raw):
                    reason = "wrong key or version; held %.0f s" % self.hold
                    await drain_for(reader, self.hold)
                    break
                if s.writer.is_closing():
                    reason = "closed by the monitor"
                    break
        finally:
            self.sessions.discard(s)
            writer.close()
            LOG.info("session from %s ended after %.1f s: %s (%d open)", peer, time.monotonic() - s.since,
                     reason, len(self.sessions))

    async def answer(self, s, raw):
        """Answer one client frame; False when it fails the key (the session is then held)."""
        try:
            header = parse_header(raw)
            if (header.prefix == P66) != (s.version >= 3.5):
                return False
            hmac_key = s.key if s.version >= 3.4 else None
            msg = unpack_message(raw, hmac_key=hmac_key, header=header, no_retcode=True)
        except Exception:  # noqa: BLE001 - any frame we cannot read under this key and version
            return False
        if not msg.crc_good:
            return False
        cmd = msg.cmd
        if s.version >= 3.4 and not s.keyed:
            return self.negotiate(s, msg)
        try:
            body = s.payload(msg)
        except Exception:  # noqa: BLE001 - a wrong 3.3 key decrypts to garbage: ignored, like a bad frame
            LOG.info("%s: command %s did not decrypt, ignored", s.peer, cmd)
            return True
        LOG.info("%s: %s", s.peer, NAMES.get(cmd, cmd))
        reply = msg.seqno if s.version < 3.5 else None
        if cmd == tinytuya.HEART_BEAT:
            s.send(s.frame(cmd, seq=reply))
        elif cmd in (tinytuya.DP_QUERY, tinytuya.DP_QUERY_NEW) and s.version < 3.4:
            if self.query33 == "unvalid":
                s.send(s.frame(cmd, UNVALID, seq=reply, retcode=1))
            elif self.query33 == "state":
                s.send(s.frame(cmd, self.state_json(), seq=reply))
        elif cmd in (tinytuya.DP_QUERY, tinytuya.DP_QUERY_NEW):
            s.send(s.frame(cmd, self.state_json(), seq=reply))
        elif cmd in (tinytuya.CONTROL, tinytuya.CONTROL_NEW):
            dps = body.get("dps") or (body.get("data") or {}).get("dps") or {}
            changed = {k: v for k, v in dps.items() if v is not None}
            s.send(s.frame(cmd, seq=reply))
            if changed:
                self.set_dps(changed)
        elif cmd == tinytuya.UPDATEDPS:
            LOG.info("%s: UPDATEDPS drops the session (assumed from the integration's notes)", s.peer)
            s.writer.close()
        return True

    def negotiate(self, s, msg):
        cipher = AESCipher(self.key)
        payload = msg.payload
        if s.version == 3.4:
            payload = cipher.decrypt(payload, False, decode_text=False)
        if msg.cmd == tinytuya.SESS_KEY_NEG_START and len(payload) >= 16:
            s.client_nonce, s.nonce = payload[:16], os.urandom(16)
            answer = s.nonce + hmac.new(self.key, s.client_nonce, sha256).digest()
            # Under the local key: the session key does not exist yet (s.key is still the local key).
            s.send(s.frame(tinytuya.SESS_KEY_NEG_RESP, answer, seq=msg.seqno if s.version == 3.4 else None))
            return True
        if msg.cmd == tinytuya.SESS_KEY_NEG_FINISH and s.nonce:
            if not hmac.compare_digest(payload[:32], hmac.new(self.key, s.nonce, sha256).digest()):
                return False
            mixed = bytes(a ^ b for a, b in zip(s.client_nonce, s.nonce))
            if s.version == 3.4:
                s.key = cipher.encrypt(mixed, False, pad=False)
            else:
                s.key = cipher.encrypt(mixed, False, pad=False, iv=s.client_nonce[:12])[12:28]
            s.keyed = True
            LOG.info("%s: session key negotiated (%s)", s.peer, s.version)
            return True
        return False

    def state_json(self):
        return json.dumps({"devId": self.id, "dps": self.dps, "t": int(time.time())}, separators=(",", ":")).encode()

    def set_dps(self, dps):
        self.dps.update(dps)
        keyed = [s for s in self.sessions if s.keyed]
        if self.fault != "silent":
            for s in keyed:
                s.push(dps)
        LOG.info("data points %s pushed to %d session(s)", sorted(dps), 0 if self.fault == "silent" else len(keyed))

    def close_all(self):
        for s in list(self.sessions):
            s.writer.close()
        return len(self.sessions)

    # --- UDP 6667 (and 7000 for 3.5) -------------------------------------------------------------
    def announcement(self, ip):
        body = {"ip": ip, "gwId": self.id, "active": 2, "ability": 0, "mode": 0, "encrypt": True,
                "productKey": self.product, "version": str(self.version)}
        if self.version >= 3.5:
            body["token"] = True
            msg = TuyaMessage(0, tinytuya.UDP_NEW, 0, json.dumps(body).encode(), 0, True, P66, os.urandom(12))
            return pack_message(msg, hmac_key=tinytuya.udpkey)
        enc = AESCipher(tinytuya.udpkey).encrypt(json.dumps(body).encode(), False)
        return pack_message(TuyaMessage(0, tinytuya.UDP_NEW, 0, b"\0\0\0\0" + enc, 0, True, P55, None))

    async def broadcast(self, port=6667):
        while True:
            if self.discovery:
                # A new socket each time: a connected one stays bound to the address it first had,
                # and after an address change (stack.sh lan ip) it could no longer send.
                try:
                    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
                        sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
                        sock.connect((self.discovery_to, port))
                        sock.send(self.announcement(sock.getsockname()[0]))
                except OSError as ex:
                    LOG.info("discovery broadcast failed: %s", ex)
            await asyncio.sleep(self.discovery_interval)

    # --- control ---------------------------------------------------------------------------------
    def state(self):
        now = time.monotonic()
        return {"id": self.id, "name": self.name, "version": str(self.version), "fault": self.fault,
                "discovery": self.discovery, "refused": self.refused, "dps": self.dps,
                "sessions": [{"peer": s.peer, "version": str(s.version), "keyed": s.keyed,
                              "seconds": round(now - s.since, 1)} for s in self.sessions]}

    def control(self, action, body):
        if action == "dps":
            self.set_dps(body)
        elif action == "fault":
            fault = body.get("fault")
            if fault == "close":
                LOG.info("fault: closing %d session(s)", self.close_all())
            elif fault in ("silent", "refuse", "normal"):
                self.fault = fault
                LOG.info("fault: %s", fault)
            else:
                raise ValueError("fault must be silent, refuse, close or normal")
        elif action == "version":
            version = float(body.get("version", 0))
            if version not in VERSIONS:
                raise ValueError("version must be 3.3, 3.4 or 3.5")
            self.version = version
            LOG.info("firmware update: now %s, closing %d session(s)", version, self.close_all())
        elif action == "discovery":
            self.discovery = bool(body.get("on"))
            LOG.info("discovery %s", "on" if self.discovery else "off")
        else:
            raise KeyError(action)
        return self.state()


async def read_frame(reader):
    """One client frame from the stream, whole (55AA or 6699)."""
    head = await reader.readexactly(4)
    if head == tinytuya.PREFIX_55AA_BIN:
        rest = await reader.readexactly(12)
        length = struct.unpack(">I", rest[8:12])[0]
        tail = 0
    elif head == tinytuya.PREFIX_6699_BIN:
        rest = await reader.readexactly(14)
        length = struct.unpack(">I", rest[10:14])[0]
        tail = 4
    else:
        raise ValueError("no frame prefix")
    if length > 4096:
        raise ValueError("frame of %d bytes" % length)
    return head + rest + await reader.readexactly(length + tail)


async def drain_for(reader, seconds):
    """Keep the connection open and unanswered for `seconds` (the SCD951's wrong-key hold)."""
    end = time.monotonic() + seconds
    while (left := end - time.monotonic()) > 0:
        try:
            if not await asyncio.wait_for(reader.read(4096), left):
                return
        except (asyncio.TimeoutError, ConnectionError):
            return


def load_entry():
    with open(env("LAN_MONITOR_KEYS_FILE", "/lan/monitors.json")) as f:
        monitors = json.load(f)["monitors"]
    wanted = env("LAN_MONITOR_ID", "")
    for entry in monitors:
        if entry["id"] == wanted:
            return entry
    raise SystemExit("no monitor %r in the keys file" % wanted)


async def serve(monitor, host="0.0.0.0", tcp_port=6668, control_port=8080):
    from aiohttp import web

    async def control(request):
        try:
            body = await request.json() if request.method == "POST" else {}
            state = monitor.control(request.match_info["action"], body) if request.method == "POST" \
                else monitor.state()
        except KeyError:
            return web.json_response({"error": "unknown action"}, status=404)
        except (ValueError, TypeError, AttributeError) as ex:
            return web.json_response({"error": str(ex)}, status=400)
        return web.json_response(state)

    app = web.Application()
    app.router.add_get("/lab/state", control)
    app.router.add_post("/lab/{action}", control)
    runner = web.AppRunner(app, access_log=None)
    await runner.setup()
    await web.TCPSite(runner, host, control_port).start()
    server = await asyncio.start_server(monitor.handle, host, tcp_port)
    # The discovery request listener runs whatever the version: a firmware update can bring 3.5.
    tasks = [asyncio.create_task(monitor.broadcast()), asyncio.create_task(answer_devinfo(monitor, host))]
    return server, runner, tasks


async def answer_devinfo(monitor, host, port=7000):
    """A 3.5 monitor answers tinytuya's discovery request (REQ_DEVINFO to UDP 7000) at once."""
    loop = asyncio.get_running_loop()

    class Proto(asyncio.DatagramProtocol):
        def connection_made(self, transport):
            self.transport = transport

        def datagram_received(self, data, addr):
            if monitor.version < 3.5 or not monitor.discovery:
                return
            try:
                msg = unpack_message(data, hmac_key=tinytuya.udpkey, no_retcode=True)
                ip = json.loads(msg.payload.rstrip(b"\0")).get("ip") or addr[0]
            except Exception:  # noqa: BLE001 - anything else on 7000 is not ours to answer
                return
            if msg.cmd == tinytuya.REQ_DEVINFO:
                with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
                    sock.connect((ip, port))
                    sock.send(monitor.announcement(sock.getsockname()[0]))

    await loop.create_datagram_endpoint(Proto, local_addr=(host, port), allow_broadcast=True)


async def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s lan-monitor %(message)s")
    entry = load_entry()
    version = float(env("LAN_MONITOR_VERSION", "3.4"))
    if version not in VERSIONS:
        raise SystemExit("LAN_MONITOR_VERSION must be 3.3, 3.4 or 3.5")
    monitor = Monitor(entry, version)
    await serve(monitor, tcp_port=int(env("LAN_MONITOR_TCP_PORT", "6668")),
                control_port=int(env("LAN_MONITOR_CONTROL_PORT", "8080")))
    LOG.info("monitor %s (%s) at protocol %s: TCP 6668, at most %d sessions, discovery %s",
             monitor.id, monitor.name, version, monitor.max_sessions, "on" if monitor.discovery else "off")
    await asyncio.Event().wait()


# --- self-test -------------------------------------------------------------------------------------
def self_test():
    """tinytuya (the integration's client library) against this fake, on 127.0.0.1."""
    import threading

    key = "0123456789abcdef"
    entry = {"id": "labselftest000000001", "key": key, "name": "self-test", "product": "labselftest"}
    os.environ.update({"LAN_MONITOR_DISCOVERY": "off", "LAN_MONITOR_WRONG_KEY_HOLD": "1.5"})
    monitor = Monitor(entry, 3.4)
    loop = asyncio.new_event_loop()
    started = threading.Event()
    ports = {}

    async def start():
        server, _runner, _tasks = await serve(monitor, "127.0.0.1", 0, 0)
        ports["tcp"] = server.sockets[0].getsockname()[1]
        started.set()

    threading.Thread(target=lambda: (loop.run_until_complete(start()), loop.run_forever()), daemon=True).start()
    if not started.wait(10):
        raise SystemExit("self-test: the fake did not start")

    def wait_until(cond, seconds=5.0):
        end = time.monotonic() + seconds
        while time.monotonic() < end:
            if cond():
                return True
            time.sleep(0.05)
        return cond()

    def client(version, local_key=key, timeout=2):
        d = tinytuya.Device(entry["id"], "127.0.0.1", local_key, version=version, port=ports["tcp"])
        d.set_socketPersistent(True)
        d.set_socketTimeout(timeout)
        d.set_socketRetryLimit(1)
        d.set_socketRetryDelay(0)
        return d

    failures = []

    def check(name, ok, detail=""):
        print("%s %s%s" % ("ok  " if ok else "FAIL", name, (": " + str(detail)) if detail and not ok else ""))
        if not ok:
            failures.append(name)

    for version in VERSIONS:
        monitor.version = version
        # Discovery: tinytuya's own UDP decoder reads the announcement.
        got = json.loads(tinytuya.decrypt_udp(monitor.announcement("127.0.0.1")))
        check("%s discovery decodes" % version, got.get("gwId") == entry["id"] and got.get("version") == str(version), got)
        d = client(version)
        check("%s session opens" % version, d._get_socket(False) is True)
        check("%s heartbeat acked" % version, d.heartbeat(nowait=False) is None)
        if version >= 3.4:
            status = d.status()
            check("%s DP_QUERY answers the state" % version, (status or {}).get("dps", {}).get("207") == monitor.dps["207"], status)
        else:
            before = d.dev_type
            d._send_receive(d.generate_payload(tinytuya.DP_QUERY), 0)
            check("3.3 DP_QUERY answers 'data unvalid'", before == "default" and d.dev_type == "device22", d.dev_type)
            d.dev_type, d.dps_to_request = "default", {}
        result = d.set_value("138", True)
        check("%s CONTROL echoes the new state" % version, (result or {}).get("dps") == {"138": True}, result)
        check("%s CONTROL changed the state" % version, monitor.dps["138"] is True)
        loop.call_soon_threadsafe(monitor.set_dps, {"207": 2450 + int(version * 10)})
        pushed = d.receive()
        check("%s push arrives" % version, (pushed or {}).get("dps") == {"207": 2450 + int(version * 10)}, pushed)
        monitor.dps["138"] = False
        d.close()
        check("%s session closed" % version, wait_until(lambda: not monitor.sessions), monitor.state()["sessions"])

    # At most 3 sessions; a 4th is refused (3.4: the handshake fails, tinytuya's 914).
    monitor.version = 3.4
    three = [client(3.4) for _ in range(3)]
    check("3 sessions open", all(d._get_socket(False) is True for d in three) and wait_until(lambda: len(monitor.sessions) == 3))
    fourth = client(3.4)
    result = fourth._get_socket(False)
    check("a 4th session is refused", result == tinytuya.ERR_KEY_OR_VER and len(monitor.sessions) == 3, result)
    for d in three:
        d.close()
    wait_until(lambda: not monitor.sessions)

    # A wrong key: tinytuya reports 914; the fake leaves the handshake unanswered and holds the
    # session for the configured time (a raw client that does not hang up itself, to time it).
    for version in (3.4, 3.5):
        monitor.version = version
        wrong = client(version, local_key="fedcba9876543210", timeout=0.3)
        result = wrong._get_socket(False)
        check("%s wrong key refused (914)" % version, result == tinytuya.ERR_KEY_OR_VER, result)
        wrong.close()
        wait_until(lambda: not monitor.sessions)
        with socket.create_connection(("127.0.0.1", ports["tcp"])) as raw:
            raw.sendall(wrong._encode_message(wrong._negotiate_session_key_generate_step_1()))
            start = time.monotonic()
            raw.settimeout(monitor.hold + 3)
            try:
                answer = raw.recv(256)
            except ConnectionError:
                answer = b""
            took = time.monotonic() - start
        check("%s wrong-key session held %.1f s, then dropped" % (version, monitor.hold),
              answer == b"" and monitor.hold - 0.2 <= took <= monitor.hold + 0.5, "%r after %.2f s" % (answer, took))

    # Faults.
    monitor.version = 3.4
    d = client(3.4, timeout=0.5)
    d._get_socket(False)
    loop.call_soon_threadsafe(monitor.control, "fault", {"fault": "silent"})
    time.sleep(0.1)
    result = d.heartbeat(nowait=False)
    # tinytuya times out (902), reopens the socket once and then fails the unanswered handshake (914).
    check("silent: a heartbeat goes unanswered", isinstance(result, dict) and result.get("Err") in ("902", "914"), result)
    loop.call_soon_threadsafe(monitor.control, "fault", {"fault": "normal"})
    d.close()
    wait_until(lambda: not monitor.sessions)
    d = client(3.4)
    d._get_socket(False)
    loop.call_soon_threadsafe(monitor.control, "version", {"version": "3.5"})
    check("firmware update closes the session", wait_until(lambda: not monitor.sessions))
    d.close()
    d = client(3.5)
    check("after the update 3.5 works", d._get_socket(False) is True and d.heartbeat(nowait=False) is None)
    d.close()
    loop.call_soon_threadsafe(monitor.control, "fault", {"fault": "refuse"})
    time.sleep(0.1)
    d = client(3.5)
    check("refuse: no new session", d._get_socket(False) == tinytuya.ERR_KEY_OR_VER and monitor.refused >= 2)
    d.close()

    print("self-test %s" % ("failed: " + ", ".join(failures) if failures else "passed"))
    return 1 if failures else 0


if __name__ == "__main__":
    if sys.argv[1:] == ["--self-test"]:
        sys.exit(self_test())
    asyncio.run(main())
