"""call.py <label> [seconds]: a two-way-audio call from the test dashboard's card, over plain CDP.

Opens TEST_PATH in the app (in-app navigation), waits for video, starts a call with the card's
`call_start` action (as a user gesture: the microphone needs one), unmutes the microphone
(`microphone_unmute`: a call starts muted), keeps it for <seconds> (default 8), ends it with
`call_end`, and reports what the page saw: whether getUserMedia was asked and answered, the microphone track's state, and an audio sender on a peer connection. What reached the
camera is read on the other side: `stack/stack.sh talk` (the simulated bridge's
recording). With the lab microphone (LAB_MIC=1) the call carries a 1 kHz tone, 2 s on, 1 s off.

Needs a card build with two-way audio for the `ha` provider (PR #2854 or later), Home Assistant's
Labs feature camera.two_way_audio on (stack.sh up does that), and a camera that offers it.
"""
import asyncio, json, os, sys

sys.path.insert(0, "/lab/tools/cdp")
from lablib import Cdp, TEST_PATH, card_js, connect, save_result  # noqa: E402

# Page-side watch: getUserMedia calls and their outcome, and audio senders on peer connections.
WATCH = r"""
(() => {
  if (window.__call) return 'already';
  const c = (window.__call = { t0: performance.now(), gum: [], pcs: [] });
  const t = () => Math.round(performance.now() - c.t0);
  const orig = navigator.mediaDevices.getUserMedia.bind(navigator.mediaDevices);
  navigator.mediaDevices.getUserMedia = (cons) => {
    const rec = { t: t(), audio: !!(cons && cons.audio), result: 'pending' };
    c.gum.push(rec);
    return orig(cons).then((s) => { rec.result = 'ok'; rec.tracks = s.getAudioTracks().map((x) => x.readyState); c.stream = s; return s; },
                          (e) => { rec.result = 'error ' + e.name; throw e; });
  };
  const Orig = window.RTCPeerConnection;
  window.RTCPeerConnection = function (...a) { const pc = new Orig(...a); c.pcs.push(pc); return pc; };
  window.RTCPeerConnection.prototype = Orig.prototype;
  return 'ok';
})()
"""
STATE = r"""
(() => {
  const c = window.__call;
  const pcs = (c.pcs || []).map((pc) => ({ state: pc.connectionState,
    audioSenders: pc.getSenders().filter((s) => s.track && s.track.kind === 'audio').map((s) => s.track.readyState + (s.track.muted ? ' muted' : '') + (s.track.enabled ? '' : ' disabled')) }));
  const mic = c.stream ? c.stream.getAudioTracks().map((x) => x.readyState + (x.muted ? ' muted' : '')) : [];
  const ha = document.querySelector('home-assistant');
  const ws = ha && ha.hass && ha.hass.connection ? ha.hass.connection.connected : null;
  // The card's own view: its call state and its microphone manager.
  let card = null;
  try {
    const w = (r) => { for (const el of r.querySelectorAll('*')) { if (el.tagName.toLowerCase() === 'advanced-camera-card') return el; if (el.shadowRoot) { const f = w(el.shadowRoot); if (f) return f; } } return null; };
    const cc = w(document)._controller;
    const m = cc.getMicrophoneManager();
    card = { call: cc.getConditionStateManager().getState().call ?? null, micConnected: m.isConnected(), micMuted: m.isMuted() };
  } catch (e) { card = { error: String(e).slice(0, 80) }; }
  return JSON.stringify({ gum: c.gum, mic, pcs, ws, card });
})()
"""


async def main(label, seconds):
    async with await connect() as ws:
        cdp = Cdp(ws)
        print(label, "watch:", await cdp.ev(WATCH))
        await cdp.goto(TEST_PATH)
        print(label, "playing:", await cdp.wait_playing())
        await asyncio.sleep(2)
        action = "card._controller.getActionsManager().executeActions({ actions: { action: 'fire-dom-event', advanced_camera_card_action: '%s' } }); return 1;"
        await cdp.ev(card_js(action % "call_start"), gesture=True, wait=False)
        # A call starts with the microphone muted (its track disabled; measured 10-11-2026): unmute,
        # as a user would.
        await asyncio.sleep(1.5)
        await cdp.ev(card_js(action % "microphone_unmute"), gesture=True, wait=False)
        # The call's state every 2 s while it is held, stamped with the wall clock (Date.now(), ms),
        # so host actions during the call (card.sh call-cut) can be lined up with it.
        timeline = []
        for _ in range(max(1, int(seconds // 2))):
            await asyncio.sleep(2)
            try:
                st = json.loads(await cdp.ev(STATE))
                timeline.append([await cdp.ev("Date.now()"), [p["state"] for p in st["pcs"]], st["mic"], st["ws"], st["card"]])
            except Exception as e:  # the page may be busy while its connection drops
                timeline.append([None, "error " + str(e)[:80], None])
        during = json.loads(await cdp.ev(STATE))
        await cdp.ev(card_js(action % "call_end"), gesture=True, wait=False)
        await asyncio.sleep(2)
        after = json.loads(await cdp.ev(STATE))
        save_result(f"call-{label}", {"seconds": seconds, "timeline": timeline, "during": during, "after": after})
        for row in timeline:
            print(label, "t", row[0], "pcs", row[1], "mic", row[2], "ha-ws", row[3] if len(row) > 3 else None, "card", json.dumps(row[4]) if len(row) > 4 else None)
        print(label, "during the call:", json.dumps(during))
        print(label, "after call_end:", json.dumps({"mic": after["mic"], "pcs": after["pcs"]}))


if __name__ == "__main__":
    asyncio.run(main(sys.argv[1], float(sys.argv[2]) if len(sys.argv) > 2 else 8))
