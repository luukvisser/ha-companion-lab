"""fsprobe.py enter|poll: puts a plain div into element fullscreen (as a gesture), or polls the
fullscreen state for 10 s: a minimal check of how the app leaves fullscreen (back key, swipes)."""
import asyncio, os, sys, time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from lablib import Cdp, connect  # noqa: E402


async def main():
    async with await connect() as ws:
        cdp = Cdp(ws)
        if sys.argv[1] == "enter":
            print(await cdp.ev("(() => { const d = document.createElement('div'); d.id = 'fsprobe'; d.style.cssText = 'background:#08f;height:200px'; document.body.prepend(d); window.__fsl = []; document.addEventListener('fullscreenchange', () => window.__fsl.push([Math.round(performance.now()), !!document.fullscreenElement])); return d.requestFullscreen().then(() => 'fs ' + !!document.fullscreenElement, (e) => 'err ' + e.message); })()", gesture=True))
        else:
            t = time.time()
            for _ in range(20):
                print(round(time.time() - t, 1), await cdp.ev("(document.fullscreenElement ? 'FS' : 'normal') + ' ' + JSON.stringify(window.__fsl || [])"))
                await asyncio.sleep(0.5)
            await cdp.ev("document.getElementById('fsprobe')?.remove(), 1")


asyncio.run(main())
