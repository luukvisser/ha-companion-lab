"""config_check.py <label>: does the card on the test dashboard load without a configuration error,
and what does its menu show? Opens the test dashboard and reports, 0.4 s and 6 s after the card
appears: Home Assistant error cards (hui-error-card), the card's own messages
(advanced-camera-card-message: a configuration or camera error), and the menu's buttons (`*` =
inert). card.sh `config` puts each card of a dashboard YAML file on the test dashboard in turn."""
import asyncio, json, sys

sys.path.insert(0, "/lab/tools/cdp")
from lablib import Cdp, TEST_PATH, connect, save_result  # noqa: E402

DEEP = ("const deep = (r, t, o = []) => { for (const el of r.querySelectorAll('*')) { "
        "if (el.tagName.toLowerCase() === t) o.push(el); if (el.shadowRoot) deep(el.shadowRoot, t, o); } return o; };")
STATE = "(() => { " + DEEP + r"""
  const text = (e) => { const parts = []; const walk = (n) => { for (const c of n.childNodes) {
    if (c.nodeType === 3) parts.push(c.textContent); else { if (c.shadowRoot) walk(c.shadowRoot); walk(c); } } };
    walk(e.shadowRoot || e); walk(e); return parts.join(' ').replace(/\s+/g, ' ').trim().slice(0, 200); };
  const menu = deep(document, 'advanced-camera-card-menu')[0];
  return JSON.stringify({
    cards: deep(document, 'advanced-camera-card').length,
    // Home Assistant keeps the error message in the error card's config, not always as text.
    errorCards: deep(document, 'hui-error-card').map((e) => String(e._config?.message ?? e._config?.error ?? '').slice(0, 200) || text(e)),
    cardMessages: deep(document, 'advanced-camera-card-message').map(text),
    menu: menu && menu.shadowRoot ? [...menu.shadowRoot.querySelectorAll('ha-icon-button')].map((b) => b.label + (b.disabled ? '*' : '')) : null,
  });
})()"""


async def main(label):
    async with await connect() as ws:
        cdp = Cdp(ws)
        await cdp.goto(TEST_PATH)
        for _ in range(100):
            s = json.loads(await cdp.ev(STATE))
            if s["cards"] or s["errorCards"]:
                break
            await asyncio.sleep(0.1)
        out = {}
        for wait in (0.4, 6):
            await asyncio.sleep(wait if wait < 1 else wait - 0.4)
            out[f"{wait}s"] = json.loads(await cdp.ev(STATE))
            print(f"{label} after {wait} s: {json.dumps(out[f'{wait}s'])}", flush=True)
        ok = not out["6s"]["errorCards"] and not out["6s"]["cardMessages"] and out["6s"]["cards"] > 0
        print(f"{label}: {'loads without an error' if ok else 'ERROR'}", flush=True)
        save_result(f"config-{label}", out)
        return ok


if __name__ == "__main__":
    sys.exit(0 if asyncio.run(main(sys.argv[1])) else 1)
