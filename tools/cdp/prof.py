"""prof.py <cov|cpu|mem|listeners|trace|act> [options]: profilers for the app's page over plain CDP (DevTools on
localhost:$CDP_PORT). Run it through tools/prof.sh, which also has the instruction counter.

  cov    V8 precise coverage: exact call counts per function, per window. Counts are of calls, so
         they do not depend on CPU speed; they do depend on what the page did in the window.
  trace  a Chrome trace (DevTools timeline categories) saved to $OUT_DIR, plus a summary of the
         renderer's main thread: wall time and thread CPU time of its tasks, top events by CPU time.
  cpu    V8 sampling CPU profiler: self and total time per JavaScript function (statistical;
         native work shows as "(program)", garbage collection as "(garbage collector)"). Each
         window is saved as a .cpuprofile (DevTools opens it as a flame chart).
  mem    memory around the action: JavaScript heap used and DOM counters (documents, nodes,
         listeners) after a garbage collection before and after each round, and the bytes
         allocated per function during the window (V8 allocation sampling).
  listeners  every event listener on window, document and all elements (shadow trees included),
         with its target and the script position of its handler, before and after -r rounds of
         action + undo; prints the listeners that were added or removed.
  act    only evaluate the action (used by prof.sh instr).

Options: -s seconds per window (5), -r rounds (3), -b a baseline window without the action
first, -j JS action evaluated with a user gesture at the start of each window, -f URL substring
of the scripts to count or list (cov, cpu, mem; default: all with a URL), -n top functions to list (15), -l label,
-x JS undoing the action after each action window (e.g. leaving fullscreen), outside the window.
"""
import argparse, asyncio, json, os, sys
from collections import Counter, defaultdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import lablib  # noqa: E402
from lablib import connect  # noqa: E402

OUT = lablib.OUT


class Cdp(lablib.Cdp):
    async def act(self, js):
        """Start an action (a user gesture, the returned promise not awaited)."""
        if not js:
            return None
        try:
            return await self.ev(js, gesture=True, wait=False)
        except RuntimeError as e:
            raise SystemExit(f"action failed: {e}")


def cov_counts(result, filt):
    c = Counter()
    for script in result["result"]:
        url = script["url"]
        if not url or (filt and filt not in url):
            continue
        name = url.split("?")[0].rsplit("/", 1)[-1]
        for fn in script["functions"]:
            n = fn["ranges"][0]["count"]
            if n:
                c[f"{name}:{fn['functionName'] or '(anon)'}"] += n
    return c


async def cov(cdp, a):
    await cdp.call("Profiler.enable")
    await cdp.call("Profiler.startPreciseCoverage", callCount=True, detailed=False)
    rounds = []
    for _ in range(a.r):
        r = {}
        for phase in (["baseline"] if a.b else []) + ["action"]:
            await cdp.call("Profiler.takePreciseCoverage")  # resets the counters
            if phase == "action":
                await cdp.act(a.j)
            await asyncio.sleep(a.s)
            r[phase] = cov_counts(await cdp.call("Profiler.takePreciseCoverage"), a.f)
            if phase == "action" and a.x:
                await cdp.act(a.x)
                await asyncio.sleep(2)
        rounds.append(r)
    await cdp.call("Profiler.stopPreciseCoverage")
    lablib.save_result(f"prof-cov-{a.l}", rounds)
    print(f"calls per {a.s} s window" + (f" (scripts matching '{a.f}')" if a.f else ""))
    print("round | baseline calls | action calls | functions run")
    for i, r in enumerate(rounds):
        b = r.get("baseline")
        print(f"{a.l} {i + 1} | {sum(b.values()) if b else '-'} | {sum(r['action'].values())} | {len(r['action'])}")
    tot = Counter()
    for r in rounds:
        for k, v in r["action"].items():
            tot[k] += v - r.get("baseline", {}).get(k, 0)
    print(f"top functions (sum over rounds{', action minus baseline' if a.b else ''}):")
    for k, v in tot.most_common(a.n):
        print(f"  {v:9} {k}")


async def trace(cdp, a):
    cats = ["devtools.timeline", "disabled-by-default-devtools.timeline", "v8.execute", "toplevel", "blink"]
    await cdp.call("Tracing.start", transferMode="ReturnAsStream", traceConfig={"includedCategories": cats, "recordMode": "recordAsMuchAsPossible"})
    await cdp.act(a.j)
    await asyncio.sleep(a.s)
    await cdp.call("Tracing.end")
    if a.x:
        await cdp.act(a.x)
    done = await cdp.wait_event("Tracing.tracingComplete")
    handle, chunks = done["params"]["stream"], []
    while True:
        r = await cdp.call("IO.read", handle=handle, size=1 << 20)
        chunks.append(r["data"])
        if r.get("eof"):
            break
    await cdp.call("IO.close", handle=handle)
    raw = "".join(chunks)
    path = f"{OUT}/prof-trace-{a.l}.json"
    open(path, "w").write(raw)
    data = json.loads(raw)
    events = data["traceEvents"] if isinstance(data, dict) else data
    names = {(e["pid"], e["tid"]): e["args"]["name"] for e in events if e.get("ph") == "M" and e.get("name") == "thread_name"}
    main = {k for k, v in names.items() if v == "CrRendererMain"}
    wall = cpu = 0
    by = defaultdict(lambda: [0, 0, 0])
    for e in events:
        if e.get("ph") != "X" or (e["pid"], e["tid"]) not in main:
            continue
        if e.get("name") == "ThreadControllerImpl::RunTask":  # top level (RunTask nests in it)
            wall += e.get("dur", 0)
            cpu += e.get("tdur", 0)
        s = by[e["name"]]
        s[0] += 1; s[1] += e.get("dur", 0); s[2] += e.get("tdur", 0)
    print(f"trace saved: {path} (open it in DevTools' Performance panel or ui.perfetto.dev)")
    print(f"renderer main thread, top-level tasks: wall {wall / 1000:.1f} ms, thread CPU {cpu / 1000:.1f} ms in {a.s} s")
    print("top events by thread CPU time (count, wall ms, CPU ms; nested events overlap):")
    for name, (c, d, t) in sorted(by.items(), key=lambda x: -x[1][2])[: a.n]:
        print(f"  {c:6} {d / 1000:9.1f} {t / 1000:9.1f}  {name}")


def fn_name(cf):
    url = cf.get("url", "")
    name = url.split("?")[0].rsplit("/", 1)[-1] if url else ""
    return (f"{name}:" if name else "") + (cf.get("functionName") or "(anon)")


def keep(cf, filt):
    if cf.get("functionName", "").startswith("("):  # (program), (idle), (garbage collector), (root)
        return True
    return not filt or filt in cf.get("url", "")


async def cpu(cdp, a):
    await cdp.call("Profiler.enable")
    await cdp.call("Profiler.setSamplingInterval", interval=100)
    rounds = []
    for i in range(a.r):
        r = {}
        for phase in (["baseline"] if a.b else []) + ["action"]:
            await cdp.call("Profiler.start")
            if phase == "action":
                await cdp.act(a.j)
            await asyncio.sleep(a.s)
            prof = (await cdp.call("Profiler.stop"))["profile"]
            json.dump(prof, open(f"{OUT}/prof-cpu-{a.l}-{i + 1}-{phase}.cpuprofile", "w"))
            nodes = {nd["id"]: nd for nd in prof["nodes"]}
            self_us = Counter()
            for sid, dt in zip(prof.get("samples", []), prof.get("timeDeltas", [])):
                cf = nodes[sid]["callFrame"]
                self_us[(fn_name(cf), keep(cf, a.f))] += dt
            r[phase] = self_us
            if phase == "action" and a.x:
                await cdp.act(a.x)
                await asyncio.sleep(2)
        rounds.append(r)
    print(f"self time per {a.s} s window, ms (sampled every 0.1 ms); saved: $OUT_DIR/prof-cpu-{a.l}-*.cpuprofile")
    print("round | phase | (program) | (garbage collector) | JavaScript" + (f" (all) | of which '{a.f}'" if a.f else ""))
    for i, r in enumerate(rounds):
        for phase, c in r.items():
            prog = sum(v for (k, _), v in c.items() if k == "(program)")
            gc = sum(v for (k, _), v in c.items() if k == "(garbage collector)")
            js = sum(v for (k, _), v in c.items() if not k.startswith("("))
            mine = sum(v for (k, kept), v in c.items() if kept and not k.startswith("("))
            print(f"{a.l} {i + 1} | {phase} | {prog / 1000:.1f} | {gc / 1000:.1f} | {js / 1000:.1f}" + (f" | {mine / 1000:.1f}" if a.f else ""))
    tot = Counter()
    for r in rounds:
        for (k, kept), v in r["action"].items():
            if kept and not k.startswith("("):
                tot[k] += v - r.get("baseline", Counter()).get((k, kept), 0)
    print(f"top functions by self time, ms (sum over rounds{', action minus baseline' if a.b else ''}):")
    for k, v in tot.most_common(a.n):
        print(f"  {v / 1000:9.1f} {k}")


async def mem_state(cdp):
    await cdp.call("HeapProfiler.collectGarbage")
    await asyncio.sleep(0.5)
    heap = await cdp.call("Runtime.getHeapUsage")
    dom = await cdp.call("Memory.getDOMCounters")
    return {"heap_used": heap["usedSize"], "heap_total": heap["totalSize"], **{k: dom[k] for k in ("documents", "nodes", "jsEventListeners")}}


async def mem(cdp, a):
    await cdp.call("HeapProfiler.enable")
    rounds = []
    for i in range(a.r):
        before = await mem_state(cdp)
        await cdp.call("HeapProfiler.startSampling", samplingInterval=16384)
        await cdp.act(a.j)
        await asyncio.sleep(a.s)
        prof = (await cdp.call("HeapProfiler.stopSampling"))["profile"]
        alloc = Counter()

        def walk(nd):
            cf = nd["callFrame"]
            if nd.get("selfSize") and keep(cf, a.f):
                alloc[fn_name(cf)] += nd["selfSize"]
            for ch in nd.get("children", []):
                walk(ch)
        walk(prof["head"])
        if a.x:
            await cdp.act(a.x)
            await asyncio.sleep(2)
        after = await mem_state(cdp)
        rounds.append({"before": before, "after": after, "alloc": alloc})
    lablib.save_result(f"prof-mem-{a.l}", rounds)
    print("after a garbage collection, before and after each round (action" + (" and undo" if a.x else "") + "):")
    print("round | heap used MB before -> after | documents | DOM nodes | JS event listeners | allocated in window MB" + (f" ('{a.f}' + natives)" if a.f else ""))
    for i, r in enumerate(rounds):
        b, f = r["before"], r["after"]
        print(f"{a.l} {i + 1} | {b['heap_used'] / 1e6:.2f} -> {f['heap_used'] / 1e6:.2f} | {b['documents']} -> {f['documents']} | {b['nodes']} -> {f['nodes']} | {b['jsEventListeners']} -> {f['jsEventListeners']} | {sum(r['alloc'].values()) / 1e6:.2f}")
    tot = Counter()
    for r in rounds:
        tot.update(r["alloc"])
    print("top allocating functions, KB (sampled every 16 KB; sum over rounds):")
    for k, v in tot.most_common(a.n):
        print(f"  {v / 1000:9.0f} {k}")


TARGETS = r"""(() => {
  const out = [window, document];
  const walk = (root) => { for (const el of root.querySelectorAll('*')) { out.push(el); if (el.shadowRoot) { out.push(el.shadowRoot); walk(el.shadowRoot); } } };
  walk(document);
  return out;
})()"""

DESCRIBE = r"""function () {
  if (this === window) return 'window';
  if (this === document) return 'document';
  if (this instanceof ShadowRoot) return '#shadow-root of ' + this.host.tagName.toLowerCase();
  const path = [];
  let el = this;
  while (el && path.length < 4) {
    path.unshift(el.tagName ? el.tagName.toLowerCase() + (el.id ? '#' + el.id : '') : '?');
    const root = el.getRootNode && el.getRootNode();
    el = el.parentElement || (root && root.host) || null;
  }
  return path.join(' > ');
}"""


async def listener_snapshot(cdp, scripts):
    await cdp.call("HeapProfiler.collectGarbage")
    arr = (await cdp.call("Runtime.evaluate", expression=TARGETS, objectGroup="lst"))["result"]["objectId"]
    props = (await cdp.call("Runtime.getProperties", objectId=arr, ownProperties=True, objectGroup="lst"))["result"]
    snap = Counter()
    for pr in props:
        if not pr["name"].isdigit() or "objectId" not in pr.get("value", {}):
            continue
        oid = pr["value"]["objectId"]
        ls = (await cdp.call("DOMDebugger.getEventListeners", objectId=oid, depth=0))["listeners"]
        if not ls:
            continue
        who = (await cdp.call("Runtime.callFunctionOn", objectId=oid, functionDeclaration=DESCRIBE, returnByValue=True))["result"].get("value", "?")
        for l in ls:
            url = scripts.get(l.get("scriptId"), "?").split("?")[0].rsplit("/", 1)[-1]
            snap[(who, l["type"], f"{url}:{l.get('lineNumber', 0) + 1}:{l.get('columnNumber', 0) + 1}")] += 1
    await cdp.call("Runtime.releaseObjectGroup", objectGroup="lst")
    return snap


async def listeners(cdp, a):
    await cdp.call("Debugger.enable")
    await asyncio.sleep(1)
    await cdp.call("Debugger.disable")
    scripts = {e["params"]["scriptId"]: e["params"].get("url", "") for e in cdp.events if e["method"] == "Debugger.scriptParsed"}
    cdp.events.clear()
    before = await listener_snapshot(cdp, scripts)
    for _ in range(a.r):
        await cdp.act(a.j)
        await asyncio.sleep(a.s)
        if a.x:
            await cdp.act(a.x)
            await asyncio.sleep(a.s)
    after = await listener_snapshot(cdp, scripts)
    print(f"listeners: {sum(before.values())} before, {sum(after.values())} after {a.r} rounds")
    diff = [(k, after[k] - before[k]) for k in set(before) | set(after) if after[k] != before[k]]
    print("change | target | event | handler (script:line:column)")
    for (who, typ, loc), d in sorted(diff, key=lambda x: (-abs(x[1]), x[0])):
        print(f"{d:+4} | {who} | {typ} | {loc}")


async def main():
    p = argparse.ArgumentParser()
    p.add_argument("mode", choices=["cov", "cpu", "mem", "listeners", "trace", "act"])
    p.add_argument("-s", type=float, default=5)
    p.add_argument("-r", type=int, default=3)
    p.add_argument("-b", action="store_true")
    p.add_argument("-j", default="")
    p.add_argument("-x", default="")
    p.add_argument("-f", default="")
    p.add_argument("-n", type=int, default=15)
    p.add_argument("-l", default="run")
    a = p.parse_args()
    async with await connect() as ws:
        cdp = Cdp(ws)
        if a.mode == "act":
            print(await cdp.act(a.j))
        elif a.mode == "cov":
            await cov(cdp, a)
        elif a.mode == "cpu":
            await cpu(cdp, a)
        elif a.mode == "mem":
            await mem(cdp, a)
        elif a.mode == "listeners":
            await listeners(cdp, a)
        else:
            await trace(cdp, a)


if __name__ == "__main__":
    asyncio.run(main())
