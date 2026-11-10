"""app_login_cdp.py: fills Home Assistant's login form in the app's WebView over DevTools and submits
it, then waits until the page has left the login. Username from $TEST_USER, password from /secret
(mounted read-only, never printed). Prints only what happened, never a credential.

Exit codes: 0 logged in (the page left /auth/authorize), 2 no login form found, 3 the login did not
go through (the password field is cleared again before exiting, so a later UI dump cannot read it).
"""
import asyncio
import json
import os
import sys
import time
import urllib.request

import websockets

PORT = int(os.environ.get("CDP_PORT", "9333"))
USER = os.environ["TEST_USER"]
PASSWORD = open("/secret").read().strip()

# Finds the form's username and password inputs through the shadow DOM, sets them as a person typing
# would (input and change events, so Lit picks the values up) and submits with Enter on the
# password field. Returns which steps it could do.
FILL = """
(([user, password]) => {
  const all = [];
  const walk = (root) => { for (const el of root.querySelectorAll('*')) { if (el.tagName === 'INPUT') all.push(el); if (el.shadowRoot) walk(el.shadowRoot); } };
  walk(document);
  const name = all.find((i) => i.autocomplete === 'username' || i.name === 'username' || (i.type === 'text' && !i.disabled));
  const pass = all.find((i) => i.type === 'password');
  if (!name || !pass) return { found: false, inputs: all.length };
  const set = (el, v) => { el.focus(); el.value = v; el.dispatchEvent(new Event('input', { bubbles: true, composed: true })); el.dispatchEvent(new Event('change', { bubbles: true, composed: true })); };
  set(name, user);
  set(pass, password);
  pass.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', code: 'Enter', keyCode: 13, bubbles: true, composed: true }));
  // Also press the form's own button, for versions that ignore Enter.
  const buttons = [];
  const walk2 = (root) => { for (const el of root.querySelectorAll('*')) { if (/^(MWC-BUTTON|HA-BUTTON|HA-PROGRESS-BUTTON|BUTTON)$/.test(el.tagName)) buttons.push(el); if (el.shadowRoot) walk2(el.shadowRoot); } };
  walk2(document);
  const login = buttons.find((b) => /log ?in|next/i.test(b.textContent || ''));
  if (login) login.click();
  return { found: true, button: !!login };
})
"""

CLEAR = """
(() => {
  const walk = (root) => { for (const el of root.querySelectorAll('*')) { if (el.tagName === 'INPUT' && el.type === 'password') { el.value = ''; el.dispatchEvent(new Event('input', { bubbles: true, composed: true })); } if (el.shadowRoot) walk(el.shadowRoot); } };
  walk(document);
  return true;
})()
"""


def page_ws():
    pages = json.load(urllib.request.urlopen(f"http://localhost:{PORT}/json", timeout=5))
    pages = [p for p in pages if p.get("type") == "page"]
    # The login is its own page target; an about:blank page may come first.
    login = [p for p in pages if "/auth/authorize" in p.get("url", "")]
    real = [p for p in pages if p.get("url", "").startswith("http")]
    # Newest first: a login page left from an earlier attempt can still be listed.
    return [p["webSocketDebuggerUrl"] for p in reversed(login or real or pages)]


async def evaluate(ws, expression, n):
    await ws.send(json.dumps({"id": n, "method": "Runtime.evaluate", "params": {"expression": expression, "returnByValue": True, "awaitPromise": True}}))
    while True:
        r = json.loads(await ws.recv())
        if r.get("id") == n:
            return r.get("result", {}).get("result", {}).get("value")


async def main():
    deadline = time.monotonic() + 90
    while time.monotonic() < deadline:
        urls = []
        try:
            urls = page_ws()
        except Exception:
            pass
        visible = None
        for candidate in urls:
            try:
                async with websockets.connect(candidate, max_size=None) as probe:
                    if await evaluate(probe, "document.visibilityState", 9) == "visible":
                        visible = candidate
                        break
            except Exception:
                continue
        url = visible
        if url:
            async with websockets.connect(url, max_size=None) as ws:
                href = await evaluate(ws, "location.protocol.startsWith('http') ? location.pathname : ''", 1)
                if href and "/auth/authorize" in href:
                    result = await evaluate(ws, FILL + "(" + json.dumps([USER, PASSWORD]) + ")", 2)
                    if result and result.get("found"):
                        print(f"login form filled and submitted (button: {result.get('button')})")
                        for _ in range(30):
                            await asyncio.sleep(1)
                            try:
                                pages = json.load(urllib.request.urlopen(f"http://localhost:{PORT}/json", timeout=5))
                                if not any("/auth/authorize" in p.get("url", "") for p in pages):
                                    print("logged in: the login page closed")
                                    return 0
                                href = await evaluate(ws, "location.pathname", 3)
                            except Exception:
                                print("logged in: the login page closed")
                                return 0
                            if not href or "/auth/authorize" not in href:
                                print("logged in: the page left the login")
                                return 0
                            # The app takes the login over natively (its next screen asks for the
                            # device name) while this page may stay on the login URL: the form is
                            # then gone from the page.
                            gone = await evaluate(ws, "(() => { const f = []; const w = (r) => { for (const e of r.querySelectorAll('*')) { if (e.tagName === 'INPUT' && e.type === 'password') f.push(e); if (e.shadowRoot) w(e.shadowRoot); } }; w(document); return f.length === 0; })()", 5)
                            if gone:
                                print("logged in: the login form is gone")
                                return 0
                        await evaluate(ws, CLEAR, 4)
                        print("the page did not leave the login (the app may have taken over natively); the password field is cleared")
                        return 3
                elif href and "/auth/" not in href and href != "/" and not href.startswith("/onboarding"):
                    print(f"already past the login (page {href})")
                    return 0
        await asyncio.sleep(2)
    print("no login form appeared in 90 s", file=sys.stderr)
    return 2


sys.exit(asyncio.run(main()))
