"""echo "<js>" | cdp.sh: evaluates a JavaScript expression in the first page of the forwarded WebView
(DevTools on localhost:$CDP_PORT, default 9333) and prints the JSON result. Plain CDP, no Playwright:
use it for anything that depends on visibilitychange."""
import asyncio, json, os, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from lablib import Cdp, connect  # noqa: E402


async def main():
    async with await connect() as ws:
        cdp = Cdp(ws)
        js = sys.stdin.read()
        r = await cdp.call("Runtime.evaluate", expression=js, awaitPromise=True, returnByValue=True, userGesture=True)
        if "exceptionDetails" in r:
            print("EXC", json.dumps(r["exceptionDetails"])[:800])
        else:
            print(json.dumps(r.get("result", {}).get("value"), indent=None)[:20000])


asyncio.run(main())
