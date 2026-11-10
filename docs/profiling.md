# Profiling

Durations in the emulator depend on its load and are not those of a phone; `tools/prof.sh` gives
measures that do not, or that say where the time goes. Each takes an optional action (`-j`, JavaScript
run in the page with a user gesture at the start of each window), an undo after it (`-x`, outside the
window), a baseline window without the action (`-b`), the window length (`-s`, 5 s) and rounds (`-r`, 3).

| Mode | Measures | Repeatability (measured 10-11-2026) | Use it for |
|---|---|---|---|
| `cov` | calls per JavaScript function in the window (V8 precise coverage), `-f` to keep one script set, e.g. `advanced-camera-card` | entering fullscreen on the test card: 4,479-4,581 calls (PR #2875) against 32,945-33,081 (its base), 3 rounds each | comparing builds: how much code an action runs |
| `cpu` | self time per JavaScript function (V8 sampling profiler, every 0.1 ms), split from "(program)" (native work: style, layout, paint) and "(garbage collector)"; each window saved as a `.cpuprofile` (a flame chart in DevTools) | statistical: one 5 s window can hold a 70 ms function the next one lacks; use rounds and `-b` | which function the JavaScript time goes to |
| `mem` | after a forced garbage collection, before and after each round: JavaScript heap used, documents, DOM nodes, JS event listeners; bytes allocated per function in the window (sampled every 16 KB); each process's PSS (`dumpsys meminfo`) before and after the run | fullscreen enter + leave on the test card, 6 rounds: heap 28.74-28.76 MB, DOM nodes ±3, listeners +2 every round (0 in 4 idle rounds) | leaks (counts that grow per round), what an action allocates |
| `listeners` | every event listener on window, document and all elements (shadow trees included), with its target and the script position of its handler, before and after `-r` rounds of action and undo; prints what was added or removed | exact | which code leaves listeners behind |
| `instr` | hardware instructions and cycles of the app, the WebView renderer (the page's JavaScript) and `media.swcodec` (video decoding); simpleperf as root | a fixed command: 0.002% spread in instructions (cycles about 10%, time about 35%); **with live video playing, the renderer's 5 s background varied 190-659 million**, more than a fullscreen enter adds | a fixed piece of work repeated without video (e.g. a capture benchmark); not small differences on a live page |
| `trace` | a Chrome trace saved to `$OUT_DIR` (open it in DevTools' Performance panel or ui.perfetto.dev), with the renderer main thread's wall and CPU time and its top events | wall time like any duration; thread CPU time excludes waiting | where the time of a slow step goes |

The action runs in the first page of the WebView; with `instr` it starts about 1 s into the window
(through a container). Counts include everything else the page did in the window: compare like with
like, and look at `-b`.
