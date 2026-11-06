# Lab Indicator SMC Zone Visuals — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the EFloud Lab indicator draw OB, Breaker (BB), Mitigation Block (MB), FVG, liquidity pools and a fixed-range OTE zone, display-only, with Python reference expectations for every layer.

**Architecture:** All new state and drawing live in `pine/lab/tail_indicator.pine` (built into `pine/efloud_lab.pine`); it reads the core pools (`swingObs`, `intObs`, `fvgs`, `equals`, `shPiv`, `slPiv`, `breaks`) and the core ring buffers (`bufHi/bufLo/bufOpen/bufClose/bufTime`), never the history operator. A new `scripts/pine_lab_visuals.py` computes the expected zones from `lx.analyze()` for TradingView-vs-Python checks, wired as `pine_lab_parity.py visuals`.

**Tech Stack:** Pine Script v6 (TradingView Desktop + tradingview-mcp CLI for compile), Python 3.14 / pandas / numpy / pytest, `engine.smc_v2.luxalgo`.

Spec: `docs/superpowers/specs/2026-11-06-lab-indicator-visuals-design.md`.

## Global Constraints

- `pine/lab/core.pine`, `pine/lab/tail_strategy.pine`, `pine/lab/head_*.pine` are **not modified**; `pine/efloud_lab_strategy.pine` must stay byte-identical (`git diff --exit-code`).
- Never edit `pine/efloud_lab.pine` by hand: edit `pine/lab/tail_indicator.pine`, run `python scripts/build_pine_lab.py`.
- Pine v6 only. In any tail function body: **no history operator `x[...]`, no `ta.*`**. Bar history comes only from ring buffers.
- Drawing budget: `indicator()` has `max_lines_count = 500, max_labels_count = 500, max_boxes_count = 500`.
- Zone state changes only inside `if barstate.isconfirmed`; drawings are rebuilt inside `if barstate.islast`.
- Signals, alert JSON, `fired`/`cands` handling unchanged. LuxAlgo licence: script stays private; no code copied from other scripts.
- Compile check without a chart: `node C:/Users/utkuc/tradingview-mcp/src/cli/index.js pine check --file <abs path>` (TradingView Desktop must run with `--remote-debugging-port=9222`; see `C:\tmp\tv_restart.ps1`). Expected `"error_count": 0`.
- Commits: conventional (`feat(pine-lab): …`, `test(pine-lab): …`), one per task.

## Ring-buffer index contract (used by every task)

Core pushes `bufHi/bufLo/bufOpen/bufClose/bufTime` once per confirmed bar, inside its `barstate.isconfirmed` block, *before* the tail runs. So in the tail's `isconfirmed` block the newest element is the **current closed bar**. The tail records `bufLastBar := bar_index` there; any later read (including inside `barstate.islast` while a realtime bar is open) maps bar `i` to index `size − 1 − (bufLastBar − i)`.

---

### Task 1: Budget fix, dashboard rows, inputs, static guard test

**Files:**
- Modify: `pine/lab/tail_indicator.pine:2-7` (inputs), `:60` (table size), `:90-96` (dashboard rows)
- Modify: `tests/test_pine_lab_build.py:16-17` (`INDICATOR_ONLY_INPUTS`), append tests
- Regenerate: `pine/efloud_lab.pine` (via build)

**Interfaces:**
- Produces inputs used by later tasks: `showBreakers`, `showFvg`, `showLiq`, `showOte`, `showHistory` (bool), `obBodyOnly`, `liqVolumeConfirm` (bool), `maxZonesPerSide` (int), `colBull`, `colBear`, `colNeutral` (color), `zoneAlpha` (int 0–100).
- Produces `dash` table with 9 rows; rows 7 and 8 filled by Tasks 5/6 via `f_cell`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_pine_lab_build.py`:

```python
TAIL = ROOT / "pine" / "lab" / "tail_indicator.pine"
HISTORY_RE = re.compile(r"\b[A-Za-z_]\w*\s*\[\s*[A-Za-z0-9_]")   # ident[ expr  (array.get is a call, not this)
TA_RE = re.compile(r"\bta\.")


def _tail_function_bodies(text: str) -> dict:
    out = {}
    for m in re.finditer(r"^(f_\w+)\([^\n]*\)\s*=>\n((?:[ \t]+[^\n]*\n|\n)+)", text, re.M):
        out[m.group(1)] = "\n".join(ln.split("//")[0] for ln in m.group(2).splitlines())
    return out


def test_tail_functions_use_no_history_operator_or_ta():
    """Tail functions run conditionally (loops, islast): `x[off]`/`ta.*` there read call history, not bar history."""
    bodies = _tail_function_bodies(TAIL.read_text(encoding="utf-8"))
    assert bodies, "tail defines no f_* functions"
    for name, body in bodies.items():
        assert not HISTORY_RE.search(body), f"{name}: history operator"
        assert not TA_RE.search(body), f"{name}: ta.* call"


def test_signal_line_budget_fits_line_limit():
    """4 lines per kept signal; maxDrawings.maxval * 4 must stay under max_lines_count=500."""
    text = TAIL.read_text(encoding="utf-8")
    m = re.search(r"maxDrawings\s*=\s*input\.int\([^)]*maxval\s*=\s*(\d+)", text)
    assert m and int(m.group(1)) * 4 <= 500, "maxDrawings.maxval * 4 exceeds the 500-line budget"


def test_indicator_declares_visual_layer_inputs():
    text = TAIL.read_text(encoding="utf-8")
    for name in ("showBreakers", "showFvg", "showLiq", "showOte", "showHistory", "obBodyOnly",
                 "liqVolumeConfirm", "maxZonesPerSide", "colBull", "colBear", "colNeutral", "zoneAlpha"):
        assert re.search(rf"^{name}\s*=\s*input\.", text, re.M), name
    assert re.search(r"table\.new\(position\.top_right,\s*2,\s*9", text), "dashboard must have 9 rows"
```

Also change `INDICATOR_ONLY_INPUTS` at the top of the file to:

```python
INDICATOR_ONLY_INPUTS = {"showObs", "showZones", "showLevels", "showDash", "maxDrawings",
                         "showBreakers", "showFvg", "showLiq", "showOte", "showHistory", "obBodyOnly",
                         "liqVolumeConfirm", "maxZonesPerSide", "colBull", "colBear", "colNeutral", "zoneAlpha"}
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest -q tests/test_pine_lab_build.py -k "tail_functions or line_budget or visual_layer_inputs" -p no:cacheprovider`
Expected: 2 FAIL (`line_budget`: maxval 150; `visual_layer_inputs`: inputs missing), `tail_functions` PASS (current functions are clean).

- [ ] **Step 3: Edit inputs and dashboard in `pine/lab/tail_indicator.pine`**

Replace lines 2–7 with:

```pine
grpVis = "Görsel"
showObs     = input.bool(true, "Active OB boxes", group = grpVis)
showZones   = input.bool(true, "Pending candidate zones", group = grpVis)
showLevels  = input.bool(true, "Entry/SL/TP lines", group = grpVis)
showDash    = input.bool(true, "Dashboard", group = grpVis)
maxDrawings = input.int(60, "Kept signal drawings", minval = 4, maxval = 100, group = grpVis)   // 4 lines each: 100 × 4 = 400 < 500

grpZones = "SMC bölgeleri (yalnız görüntü)"
showBreakers     = input.bool(true,  "Breaker / Mitigation blocks (BB/MB)", group = grpZones)
showFvg          = input.bool(true,  "FVG boxes",                           group = grpZones)
showLiq          = input.bool(true,  "Liquidity levels (EQH/EQL/BSL/SSL)",  group = grpZones)
showOte          = input.bool(true,  "OTE range (0.618–0.786, 0.705, EQ)",  group = grpZones)
showHistory      = input.bool(false, "History: mitigated OBs, swept levels (faded)", group = grpZones)
obBodyOnly       = input.bool(false, "OB/BB/MB boxes from candle body",     group = grpZones)
liqVolumeConfirm = input.bool(true,  "Volume-confirmed liquidity (★)",      group = grpZones)
maxZonesPerSide  = input.int(8, "Nearest zones per side (per layer)", minval = 1, maxval = 200, group = grpZones)
colBull          = input.color(color.teal,   "Bull colour",    group = grpZones)
colBear          = input.color(color.maroon, "Bear colour",    group = grpZones)
colNeutral       = input.color(color.orange, "Liquidity colour", group = grpZones)
zoneAlpha        = input.int(85, "Zone fill transparency", minval = 0, maxval = 100, group = grpZones)
```

Change line 60 to `var table dash = table.new(position.top_right, 2, 9, border_width = 1)` and append after the `f_cell(6, …)` line:

```pine
    f_cell(7, "Zones s/i·BB·MB·FVG·Liq", "-")
    f_cell(8, "OTE", "-")
```

- [ ] **Step 4: Build, run tests, compile**

Run: `python scripts/build_pine_lab.py && python -m pytest -q tests/test_pine_lab_build.py tests/test_pine_lab_parity.py -p no:cacheprovider`
Expected: all PASS (3 new tests included).
Run: `node C:/Users/utkuc/tradingview-mcp/src/cli/index.js pine check --file C:/Users/utkuc/Downloads/efloud-bot/pine/efloud_lab.pine`
Expected: `"error_count": 0`.
Run: `git diff --exit-code pine/lab/core.pine pine/efloud_lab_strategy.pine`
Expected: no output, exit 0 (the strategy build is unchanged because only the indicator tail changed).

- [ ] **Step 5: Commit**

```bash
git add pine/lab/tail_indicator.pine pine/efloud_lab.pine tests/test_pine_lab_build.py
git commit -m "feat(pine-lab): zone-layer inputs, 9-row dashboard, signal line budget within 500"
```

---

### Task 2: Tail buffer helpers, Zone type, FVG layer

**Files:**
- Modify: `pine/lab/tail_indicator.pine` (insert after the `f_fmt` function; extend the `barstate.islast` block)
- Modify: `tests/test_pine_lab_build.py` (append test)

**Interfaces:**
- Produces (used by Tasks 3–6):
  - `var int bufLastBar` — bar_index of the newest ring-buffer element; set in the tail's confirmed block.
  - `f_bufAt(array<float> buf, int barIdx) => float` — value of `buf` at bar `barIdx`, `na` if outside.
  - `type Zone { float top, float bot, int x1, int dir, string txt, int kind, bool faded }` — kind: 0 OB, 1 iOB, 2 BB, 3 MB, 4 FVG.
  - `f_zoneColor(int dir) => color`, `f_pushZone(array<Zone> z, float top, float bot, int x1, int dir, string txt, int kind, bool faded)`.
  - `f_drawNearest(array<Zone> z, int n)` — draws the `n` zones nearest to `close` above and the `n` nearest below (two-pass, no full sort) into `zoneLayerBoxes`.
  - `var array<box> zoneLayerBoxes` cleared and rebuilt each `islast`.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_pine_lab_build.py`:

```python
def test_tail_defines_zone_helpers_and_fvg_layer():
    text = TAIL.read_text(encoding="utf-8")
    for needle in ("type Zone", "f_bufAt(", "f_drawNearest(", "var int bufLastBar", "zoneLayerBoxes", "if showFvg"):
        assert needle in text, needle
    body = _tail_function_bodies(text)["f_drawNearest"]
    assert "array.get" in body and "f_boxZone" in body
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest -q tests/test_pine_lab_build.py -k zone_helpers -p no:cacheprovider`
Expected: FAIL (`type Zone` missing).

- [ ] **Step 3: Add helpers and the FVG layer**

Insert after `f_fmt` (line 20) in `pine/lab/tail_indicator.pine`:

```pine
// ─── Zone layers (display only; spec docs/superpowers/specs/2026-11-06-lab-indicator-visuals-design.md) ───
// Ring-buffer contract: core pushes bufHi/bufLo/bufOpen/bufClose/bufTime once per confirmed bar before the tail runs,
// so in the tail's confirmed block the newest element is the current closed bar. bufLastBar remembers that bar.
var int bufLastBar = -1
if barstate.isconfirmed
    bufLastBar := bar_index

f_bufAt(array<float> buf, int barIdx) =>
    int j = array.size(buf) - 1 - (bufLastBar - barIdx)
    j >= 0 and j < array.size(buf) ? array.get(buf, j) : na

type Zone
    float  top
    float  bot
    int    x1
    int    dir            // 1 bull / -1 bear (current role)
    string txt            // "OB" | "iOB" | "BB" | "MB" | "FVG" | "OB ✓"
    int    kind           // 0 OB, 1 iOB, 2 BB, 3 MB, 4 FVG
    bool   faded

var array<box> zoneLayerBoxes = array.new<box>()

f_zoneColor(int dir) =>
    dir == 1 ? colBull : colBear

f_pushZone(array<Zone> z, float top, float bot, int x1, int dir, string txt, int kind, bool faded) =>
    array.push(z, Zone.new(top = top, bot = bot, x1 = x1, dir = dir, txt = txt, kind = kind, faded = faded))

f_boxZone(Zone z) =>
    color base = f_zoneColor(z.dir)
    int fillA   = z.faded ? math.min(100, zoneAlpha + 10) : zoneAlpha
    int borderA = z.faded ? 70 : (z.kind == 1 ? 60 : 30)
    string sty  = z.kind == 2 ? line.style_dashed : z.kind == 3 ? line.style_dotted : line.style_solid
    array.push(zoneLayerBoxes, box.new(z.x1, z.top, bar_index + 5, z.bot, border_color = color.new(base, borderA), border_style = sty, bgcolor = color.new(base, fillA), text = z.txt, text_size = size.tiny, text_color = color.new(base, 0), text_halign = text.align_right))

// Nearest n zones above and below close, per layer. Two passes per side: mark the n smallest distances
// (O(n × P), no full sort). Distance = near edge − close (zones straddling close count as distance 0, below side).
f_drawNearest(array<Zone> z, int n) =>
    int p = array.size(z)
    if p > 0
        array<float> dist = array.new<float>(p, 0.0)
        array<bool>  used = array.new<bool>(p, false)
        for i = 0 to p - 1
            Zone zi = array.get(z, i)
            array.set(dist, i, zi.bot > close ? zi.bot - close : zi.top < close ? close - zi.top : 0.0)
        for side = 0 to 1                                           // 0 above, 1 below/straddling
            for k = 1 to n
                int   best  = -1
                float bestD = na
                for i = 0 to p - 1
                    Zone zi = array.get(z, i)
                    bool above = zi.bot > close
                    if not array.get(used, i) and (side == 0 ? above : not above)
                        float d = array.get(dist, i)
                        if na(bestD) or d < bestD
                            bestD := d
                            best  := i
                if best >= 0
                    array.set(used, best, true)
                    f_boxZone(array.get(z, best))
    true
```

Replace the existing `if barstate.islast` block (lines 49–58) with:

```pine
if barstate.islast
    f_clearBoxes(zoneLayerBoxes)
    // z-order (bottom → top): OTE → FVG → OB/iOB → BB/MB → liquidity → pending zones → signal lines
    if showFvg
        array<Zone> zf = array.new<Zone>()
        for f in fvgs
            if f.mitigatedIdx < 0
                f_pushZone(zf, f.top, f.bot, f.idx, f.bias, "FVG", 4, false)
        f_drawNearest(zf, maxZonesPerSide)
    f_clearBoxes(obBoxes)
    if showObs
        f_drawObs(swingObs, 30, 80)
        f_drawObs(intObs, 60, 92)
    f_clearBoxes(zoneBoxes)
    if showZones
        for c in cands
            if f_isActive(c)
                array.push(zoneBoxes, box.new(c.trigIdx, c.zHigh, bar_index + 10, c.zLow, border_color = color.orange, bgcolor = color.new(color.orange, 80), text = c.state + (oteEntry and not na(c.limitPx) ? " @" + f_fmt(c.limitPx) : ""), text_size = size.tiny, text_color = color.orange))
```

(OB drawing still uses `f_drawObs` here; Task 4 replaces it with the Zone pipeline.)

- [ ] **Step 4: Build, test, compile**

Run: `python scripts/build_pine_lab.py && python -m pytest -q tests/test_pine_lab_build.py -p no:cacheprovider`
Expected: PASS.
Run: `node C:/Users/utkuc/tradingview-mcp/src/cli/index.js pine check --file C:/Users/utkuc/Downloads/efloud-bot/pine/efloud_lab.pine`
Expected: `"error_count": 0`. If the compiler rejects `border_style = sty` with a string variable, declare `sty` via `string sty = …` as shown; `line.style_*` constants are strings in v6.

- [ ] **Step 5: Commit**

```bash
git add pine/lab/tail_indicator.pine pine/efloud_lab.pine tests/test_pine_lab_build.py
git commit -m "feat(pine-lab): zone helpers (ring-buffer index, nearest-N per side) and FVG layer"
```

---

### Task 3: Liquidity layer with volume confirmation

**Files:**
- Modify: `pine/lab/tail_indicator.pine` (after Task 2 helpers; extend `islast` block)
- Modify: `tests/test_pine_lab_build.py` (append test)

**Interfaces:**
- Produces: `var array<float> bufVol`, `var array<float> bufVolMa` (pushed in the tail's confirmed block, capped at `bufCap`), `f_sweepBar(bool isHigh, float price, int fromBar) => int` (first bar after `fromBar` whose high > price / low < price, −1 if none), `f_volConfirmed(bool isHigh, int barIdx) => bool`, `var array<line> liqLines`, `var array<label> liqLabels`, `var int dashLiq` (dashboard counter).

- [ ] **Step 1: Write the failing test**

```python
def test_tail_liquidity_layer_uses_tail_volume_buffers():
    text = TAIL.read_text(encoding="utf-8")
    for needle in ("var array<float> bufVol", "var array<float> bufVolMa", "f_sweepBar(", "f_volConfirmed(", "if showLiq", "liqLines"):
        assert needle in text, needle
    # ta.sma(volume, 60) must be a global (unconditional) line, never inside a function
    assert re.search(r"^volMa60\s*=\s*ta\.sma\(volume,\s*60\)", text, re.M)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest -q tests/test_pine_lab_build.py -k liquidity_layer -p no:cacheprovider`
Expected: FAIL.

- [ ] **Step 3: Add the volume buffers and the liquidity layer**

Insert after `f_drawNearest` in `pine/lab/tail_indicator.pine`:

```pine
// ─── Liquidity (EQH/EQL from `equals`, BSL/SSL from shPiv/slPiv); volume confirmation per DGT-style rule ───
volMa60 = ta.sma(volume, 60)                        // global, every bar (never inside a function)
var array<float> bufVol   = array.new<float>()
var array<float> bufVolMa = array.new<float>()
if barstate.isconfirmed
    array.push(bufVol, volume)
    array.push(bufVolMa, volMa60)
    if array.size(bufVol) > bufCap
        array.shift(bufVol)
        array.shift(bufVolMa)

var array<line>  liqLines  = array.new<line>()
var array<label> liqLabels = array.new<label>()
var int dashLiq = 0

// First bar after fromBar that trades through `price` (wick), or -1. Scans the ring buffers only.
f_sweepBar(bool isHigh, float price, int fromBar) =>
    int found = -1
    int lo = math.max(fromBar + 1, bufLastBar - array.size(bufHi) + 1)
    if lo <= bufLastBar
        for b = lo to bufLastBar
            if found < 0
                float v = isHigh ? f_bufAt(bufHi, b) : f_bufAt(bufLo, b)
                if not na(v) and (isHigh ? v > price : v < price)
                    found := b
    found

// Level formed at barIdx is "volume confirmed" when the 3 bars ending there make rising highs (falling lows for a low),
// volume rises on each bar and the last bar's volume is above its 60-bar SMA. All reads from ring buffers.
f_volConfirmed(bool isHigh, int barIdx) =>
    float v0 = f_bufAt(bufVol, barIdx - 2)
    float v1 = f_bufAt(bufVol, barIdx - 1)
    float v2 = f_bufAt(bufVol, barIdx)
    float m2 = f_bufAt(bufVolMa, barIdx)
    float p0 = isHigh ? f_bufAt(bufHi, barIdx - 2) : f_bufAt(bufLo, barIdx - 2)
    float p1 = isHigh ? f_bufAt(bufHi, barIdx - 1) : f_bufAt(bufLo, barIdx - 1)
    float p2 = isHigh ? f_bufAt(bufHi, barIdx)     : f_bufAt(bufLo, barIdx)
    bool ok = not na(v0) and not na(v1) and not na(v2) and not na(m2) and not na(p0) and not na(p1) and not na(p2)
    ok and v0 < v1 and v1 < v2 and v2 > m2 and (isHigh ? (p0 < p1 and p1 < p2) : (p0 > p1 and p1 > p2))

f_drawLiq(bool isHigh, float price, int fromBar, bool swept, string tag) =>
    bool conf = liqVolumeConfirm and f_volConfirmed(isHigh, fromBar)
    int  x2   = swept ? f_sweepBar(isHigh, price, fromBar) : bar_index + 5
    if x2 < 0
        x2 := bar_index + 5
    array.push(liqLines, line.new(fromBar, price, x2, price, color = color.new(colNeutral, swept ? 70 : 0), style = swept ? line.style_dashed : line.style_solid, width = conf ? 2 : 1))
    if not swept
        array.push(liqLabels, label.new(x2, price, tag + (conf ? " ★" : ""), style = label.style_label_left, color = color.new(colNeutral, 100), textcolor = colNeutral, size = size.tiny))
    true
```

Add to the `islast` block, right after the pending-zone (`showZones`) section:

```pine
    for l in liqLines
        line.delete(l)
    array.clear(liqLines)
    for l in liqLabels
        label.delete(l)
    array.clear(liqLabels)
    dashLiq := 0
    if showLiq
        // unswept: nearest 10 to close (two-pass over a scratch list); swept: last 5, only with showHistory
        array<float>  lp = array.new<float>()
        array<bool>   lh = array.new<bool>()
        array<int>    lb = array.new<int>()
        array<string> lt = array.new<string>()
        for e in equals
            if not e.swept
                array.push(lp, e.priceB)
                array.push(lh, e.isHigh)
                array.push(lb, e.idxB)
                array.push(lt, e.isHigh ? "EQH" : "EQL")
        for p in shPiv
            if not p.swept
                array.push(lp, p.price)
                array.push(lh, true)
                array.push(lb, p.bar)
                array.push(lt, "BSL")
        for p in slPiv
            if not p.swept
                array.push(lp, p.price)
                array.push(lh, false)
                array.push(lb, p.bar)
                array.push(lt, "SSL")
        int np = array.size(lp)
        if np > 0
            array<bool> used = array.new<bool>(np, false)
            for k = 1 to math.min(10, np)
                int best = -1
                float bestD = na
                for i = 0 to np - 1
                    if not array.get(used, i)
                        float d = math.abs(array.get(lp, i) - close)
                        if na(bestD) or d < bestD
                            bestD := d
                            best  := i
                if best >= 0
                    array.set(used, best, true)
                    f_drawLiq(array.get(lh, best), array.get(lp, best), array.get(lb, best), false, array.get(lt, best))
                    dashLiq += 1
        if showHistory
            int shownSwept = 0
            if array.size(equals) > 0
                for i = array.size(equals) - 1 to 0
                    Equal e = array.get(equals, i)
                    if e.swept and shownSwept < 5
                        f_drawLiq(e.isHigh, e.priceB, e.idxB, true, e.isHigh ? "EQH" : "EQL")
                        shownSwept += 1
```

- [ ] **Step 4: Build, test, compile**

Run: `python scripts/build_pine_lab.py && python -m pytest -q tests/test_pine_lab_build.py -p no:cacheprovider`
Expected: PASS.
Run: `node C:/Users/utkuc/tradingview-mcp/src/cli/index.js pine check --file C:/Users/utkuc/Downloads/efloud-bot/pine/efloud_lab.pine`
Expected: `"error_count": 0`.

- [ ] **Step 5: Commit**

```bash
git add pine/lab/tail_indicator.pine pine/efloud_lab.pine tests/test_pine_lab_build.py
git commit -m "feat(pine-lab): liquidity layer (EQH/EQL/BSL/SSL, swept history, volume-confirmed levels)"
```

---

### Task 4: OB layer through the Zone pipeline (body toggle, faded mitigated, T2 copy guard)

**Files:**
- Modify: `pine/lab/tail_indicator.pine` (replace `f_drawObs` and its call sites)
- Modify: `tests/test_pine_lab_build.py` (append test)

**Interfaces:**
- Produces: `f_obEdges(OB o) => [float top, float bot]` (body or parsed range), `f_isBreakerCopy(OB o, array<OB> pool) => bool` (T2 guard), `f_collectObs(array<OB> pool, bool internal, array<Zone> z)`, `var int dashObS`, `var int dashObI`; `f_drawObs` and `obBoxes` are removed.

- [ ] **Step 1: Write the failing test**

```python
def test_tail_ob_layer_uses_zone_pipeline():
    text = TAIL.read_text(encoding="utf-8")
    assert "f_drawObs(" not in text and "obBoxes" not in text
    for needle in ("f_obEdges(", "f_isBreakerCopy(", "f_collectObs(", "obBodyOnly"):
        assert needle in text, needle
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest -q tests/test_pine_lab_build.py -k ob_layer -p no:cacheprovider`
Expected: FAIL (`f_drawObs(` still present).

- [ ] **Step 3: Replace the OB drawing**

Delete `var array<box> obBoxes = array.new<box>()` (line 9) and the whole `f_drawObs` function. Insert after `f_drawLiq`:

```pine
// ─── OB layer ───
var int dashObS = 0
var int dashObI = 0

f_obEdges(OB o) =>
    float top = o.top()
    float bot = o.bot()
    if obBodyOnly
        float oo = f_bufAt(bufOpen, o.idx)
        float cc = f_bufAt(bufClose, o.idx)
        if not na(oo) and not na(cc)
            top := math.max(oo, cc)
            bot := math.min(oo, cc)
    [top, bot]

// T2 (obInvalidate) pushes the flipped breaker as a new OB with the same candle idx and opposite bias.
// Such a copy is neither drawn as an OB nor tracked for BB/MB (the tracker classifies the source OB instead).
f_isBreakerCopy(OB o, array<OB> pool) =>
    bool copy = false
    for q in pool
        if not copy and q.idx == o.idx and q.bias == -o.bias and q.createdIdx < o.createdIdx
            copy := true
    copy

f_collectObs(array<OB> pool, bool internal, array<Zone> z) =>
    int active = 0
    for o in pool
        if not f_isBreakerCopy(o, pool)
            [top, bot] = f_obEdges(o)
            if o.mitigatedIdx < 0
                f_pushZone(z, top, bot, o.idx, o.bias, internal ? "iOB" : "OB", internal ? 1 : 0, false)
                active += 1
            else if showHistory
                f_pushZone(z, top, bot, o.idx, o.bias, (internal ? "iOB" : "OB") + " ✓", internal ? 1 : 0, true)
    active
```

In the `islast` block replace

```pine
    f_clearBoxes(obBoxes)
    if showObs
        f_drawObs(swingObs, 30, 80)
        f_drawObs(intObs, 60, 92)
```

with

```pine
    dashObS := 0
    dashObI := 0
    if showObs
        array<Zone> zo = array.new<Zone>()
        dashObS := f_collectObs(swingObs, false, zo)
        dashObI := f_collectObs(intObs, true, zo)
        f_drawNearest(zo, maxZonesPerSide)
```

(Faded "OB ✓" zones only appear while `showHistory` is on; a mitigated OB that later flips is handled by Task 5 and is then drawn as BB/MB instead.)

- [ ] **Step 4: Build, test, compile**

Run: `python scripts/build_pine_lab.py && python -m pytest -q tests/test_pine_lab_build.py -p no:cacheprovider`
Expected: PASS.
Run: `node C:/Users/utkuc/tradingview-mcp/src/cli/index.js pine check --file C:/Users/utkuc/Downloads/efloud-bot/pine/efloud_lab.pine`
Expected: `"error_count": 0`.

- [ ] **Step 5: Commit**

```bash
git add pine/lab/tail_indicator.pine pine/efloud_lab.pine tests/test_pine_lab_build.py
git commit -m "feat(pine-lab): OB layer via nearest-N zones, body toggle, faded mitigated OBs, T2 copy guard"
```

---

### Task 5: Flip tracker — Breaker vs Mitigation Block

**Files:**
- Modify: `pine/lab/tail_indicator.pine` (state block before `islast`; `islast` drawing; dashboard row 7)
- Modify: `tests/test_pine_lab_build.py` (append test)

**Interfaces:**
- Produces: `type Flip { OB ob, float refA, float legExt, int flipBar = -1, int cls = 0, bool dead = false }`, `var array<Flip> flips`, `f_lastPivotBefore(array<Piv> pivs, int barIdx) => float` (price of the last pivot with `bar < barIdx`, `na` if none), `f_legExtInit(OB o) => float`, `f_recordNewObs(array<OB> pool)`, `f_trackFlips()` (once per confirmed bar), `var int dashBb`, `var int dashMb`, `var int dashFvg`.
- Consumes: `f_obEdges`, `f_isBreakerCopy`, `f_pushZone`, `f_drawNearest`, `f_bufAt`, `dashObS/dashObI/dashLiq` (Tasks 2–4).

Rule (spec §3.2), bear OB → bullish BB/MB; bull OB mirrored:
- record when `createdIdx == bar_index`; `refA` = last swing-low pivot price with `bar < ob.idx` (frozen); none → `cls = 3`.
- `legExt` starts as min low over `(ob.idx, createdIdx]`, then is updated each confirmed bar **after** the flip check (so it covers `(ob.idx, flipBar)`).
- flip: first confirmed bar after `createdIdx` with `close > ob.top()`; class: `legExt < refA` → BB (1) else MB (2).
- dead: after the flip, first bar with `close < ob.bot()`.

- [ ] **Step 1: Write the failing test**

```python
def test_tail_flip_tracker_present_and_buffer_only():
    text = TAIL.read_text(encoding="utf-8")
    for needle in ("type Flip", "var array<Flip> flips", "f_lastPivotBefore(", "f_legExtInit(", "f_trackFlips(", "if showBreakers"):
        assert needle in text, needle
    bodies = _tail_function_bodies(text)
    assert "f_bufAt" in bodies["f_legExtInit"]
    assert "mitigatedIdx" not in bodies["f_trackFlips"], "flip tracking must not filter on mitigatedIdx (every flip happens on a mitigated OB)"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest -q tests/test_pine_lab_build.py -k flip_tracker -p no:cacheprovider`
Expected: FAIL.

- [ ] **Step 3: Add the tracker**

Insert after `f_collectObs`:

```pine
// ─── Flip tracker: closed-through OB → Breaker (BB) or Mitigation Block (MB); two-scale rule (spec §3.2) ───
type Flip
    OB    ob
    float refA            // frozen last swing pivot before the OB candle (bear OB: swing low; bull OB: swing high)
    float legExt          // bear OB: min low over (ob.idx, flipBar); bull OB: max high
    int   flipBar = -1
    int   cls = 0         // 0 pending · 1 BB · 2 MB · 3 NONE (no reference pivot → never drawn)
    bool  dead = false

var array<Flip> flips = array.new<Flip>()
var int dashBb  = 0
var int dashMb  = 0
var int dashFvg = 0

f_lastPivotBefore(array<Piv> pivs, int barIdx) =>
    float px = na
    for p in pivs
        if p.bar < barIdx
            px := p.price
    px

f_legExtInit(OB o) =>
    float ext = na
    if o.createdIdx > o.idx
        for b = o.idx + 1 to o.createdIdx
            float v = o.bias == -1 ? f_bufAt(bufLo, b) : f_bufAt(bufHi, b)
            if not na(v)
                ext := na(ext) ? v : (o.bias == -1 ? math.min(ext, v) : math.max(ext, v))
    ext

f_recordNewObs(array<OB> pool) =>
    int n = array.size(pool)
    if n > 0
        bool stop = false
        for i = n - 1 to 0
            if not stop
                OB o = array.get(pool, i)
                if o.createdIdx != bar_index
                    stop := true
                else if not f_isBreakerCopy(o, pool)
                    float refA = o.bias == -1 ? f_lastPivotBefore(slPiv, o.idx) : f_lastPivotBefore(shPiv, o.idx)
                    array.push(flips, Flip.new(ob = o, refA = refA, legExt = f_legExtInit(o), cls = na(refA) ? 3 : 0))
    true

f_trackFlips() =>
    for fl in flips
        OB o = fl.ob
        if not fl.dead and fl.cls != 3
            if fl.flipBar < 0
                if bar_index > o.createdIdx
                    bool flipped = o.bias == -1 ? close > o.top() : close < o.bot()
                    if flipped
                        fl.flipBar := bar_index
                        bool swept = o.bias == -1 ? fl.legExt < fl.refA : fl.legExt > fl.refA
                        fl.cls := swept ? 1 : 2
                if fl.flipBar < 0                               // extend the leg only while still pending (excludes the flip bar)
                    float v = o.bias == -1 ? low : high
                    fl.legExt := na(fl.legExt) ? v : (o.bias == -1 ? math.min(fl.legExt, v) : math.max(fl.legExt, v))
            else
                fl.dead := o.bias == -1 ? close < o.bot() : close > o.top()
    if array.size(flips) > 0
        for i = array.size(flips) - 1 to 0
            if array.get(flips, i).ob.createdIdx < bar_index - liveWindowBars
                array.remove(flips, i)
    true

if barstate.isconfirmed
    f_recordNewObs(swingObs)
    f_recordNewObs(intObs)
    f_trackFlips()
```

`f_trackFlips` reads `close`, `low`, `high`, `bar_index` directly (current bar, no history) — allowed; only `[off]` and `ta.*` are forbidden.

In the `islast` block, right after the OB section (so BB/MB sit above OBs), add:

```pine
    dashBb := 0
    dashMb := 0
    if showBreakers
        array<Zone> zb = array.new<Zone>()
        for fl in flips
            if fl.flipBar >= 0 and not fl.dead and (fl.cls == 1 or fl.cls == 2)
                [top, bot] = f_obEdges(fl.ob)
                f_pushZone(zb, top, bot, fl.ob.idx, -fl.ob.bias, fl.cls == 1 ? "BB" : "MB", fl.cls == 1 ? 2 : 3, false)
                if fl.cls == 1
                    dashBb += 1
                else
                    dashMb += 1
        f_drawNearest(zb, maxZonesPerSide)
```

Also set `dashFvg := array.size(zf)` inside the `if showFvg` block (Task 2) right after `zf` is filled, and `dashFvg := 0` before it. Dashboard row 7 (replace the Task 1 placeholder):

```pine
    f_cell(7, "Zones s/i·BB·MB·FVG·Liq", str.tostring(dashObS) + "/" + str.tostring(dashObI) + "·" + str.tostring(dashBb) + "·" + str.tostring(dashMb) + "·" + str.tostring(dashFvg) + "·" + str.tostring(dashLiq))
```

- [ ] **Step 4: Build, test, compile**

Run: `python scripts/build_pine_lab.py && python -m pytest -q tests/test_pine_lab_build.py -p no:cacheprovider`
Expected: PASS.
Run: `node C:/Users/utkuc/tradingview-mcp/src/cli/index.js pine check --file C:/Users/utkuc/Downloads/efloud-bot/pine/efloud_lab.pine`
Expected: `"error_count": 0`.

- [ ] **Step 5: Commit**

```bash
git add pine/lab/tail_indicator.pine pine/efloud_lab.pine tests/test_pine_lab_build.py
git commit -m "feat(pine-lab): breaker/mitigation block tracker (two-scale sweep rule) and zone counters"
```

---

### Task 6: Fixed-range OTE

**Files:**
- Modify: `pine/lab/tail_indicator.pine` (state block; `islast` drawing; dashboard row 8)
- Modify: `tests/test_pine_lab_build.py` (append test)

**Interfaces:**
- Produces: `var float rngH, rngL`, `var int rngHBar, rngLBar, rngDir` (0 undefined / 1 LONG / −1 SHORT), `f_barOfExtreme(bool isHigh, float price, int fromBar, int toBar) => int`, `f_updateRange()`, `var array<line> oteLines`, `var box oteBox`, `var string dashOte`.

Rule (spec §3.5): new range on a swing break bar (`Brk.internal == false and b.idx == bar_index`): `L = min(ob.rawLow, low)`, `H = max(ob.rawHigh, high)`; `b.ob` na → `L = swingLow.level`, `H = swingHigh.level`. Extend on wick (`high > H`, `low < L`) on confirmed bars only. Direction: `hBar > lBar → 1`, `hBar < lBar → −1`, equal → keep previous. Levels: LONG band `[H − 0.786R, H − 0.618R]`, 0.705 at `H − 0.705R`; SHORT band `[L + 0.618R, L + 0.786R]`, 0.705 at `L + 0.705R`; EQ `L + 0.5R`; skip when `R < 2 × syminfo.mintick`.

- [ ] **Step 1: Write the failing test**

```python
def test_tail_ote_range_state_and_drawing():
    text = TAIL.read_text(encoding="utf-8")
    for needle in ("var float rngH", "var float rngL", "var int rngDir", "f_updateRange(", "f_barOfExtreme(", "if showOte", "0.705"):
        assert needle in text, needle
    body = _tail_function_bodies(text)["f_updateRange"]
    assert "b.internal" in body and "rawLow" in body and "rawHigh" in body
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest -q tests/test_pine_lab_build.py -k ote_range -p no:cacheprovider`
Expected: FAIL.

- [ ] **Step 3: Add the range state and drawing**

Insert after the flip tracker's confirmed block:

```pine
// ─── OTE on a fixed swing range (spec §3.5): changes only when price exceeds H/L or a swing break starts a new range ───
var float  rngH    = na
var float  rngL    = na
var int    rngHBar = -1
var int    rngLBar = -1
var int    rngDir  = 0
var string dashOte = "-"

// Bar in [fromBar, toBar] whose high (or low) equals `price`; last match wins. Ring buffers only.
f_barOfExtreme(bool isHigh, float price, int fromBar, int toBar) =>
    int found = -1
    int lo = math.max(fromBar, bufLastBar - array.size(bufHi) + 1)
    if lo <= toBar
        for b = lo to toBar
            float v = isHigh ? f_bufAt(bufHi, b) : f_bufAt(bufLo, b)
            if not na(v) and v == price
                found := b
    found

f_updateRange() =>
    int prevDir = rngDir
    for b in breaks
        if not b.internal and b.idx == bar_index                  // swing BOS/CHoCH this bar: new range = impulse leg incl. the break bar
            if na(b.ob)
                rngL := swingLow.level
                rngH := swingHigh.level
                rngLBar := swingLow.bar
                rngHBar := swingHigh.bar
            else
                rngL := math.min(b.ob.rawLow, low)
                rngH := math.max(b.ob.rawHigh, high)
                rngLBar := rngL == low  ? bar_index : f_barOfExtreme(false, rngL, b.pivotBar, bar_index)
                rngHBar := rngH == high ? bar_index : f_barOfExtreme(true,  rngH, b.pivotBar, bar_index)
    if not na(rngH) and not na(rngL)
        if high > rngH
            rngH := high
            rngHBar := bar_index
        if low < rngL
            rngL := low
            rngLBar := bar_index
        rngDir := rngHBar > rngLBar ? 1 : rngHBar < rngLBar ? -1 : prevDir
    true

if barstate.isconfirmed
    f_updateRange()

var array<line> oteLines = array.new<line>()
var box oteBox = na
```

In the `islast` block, **at the very top** (before the FVG layer, so OTE sits at the bottom of the z-order) add:

```pine
    for l in oteLines
        line.delete(l)
    array.clear(oteLines)
    if not na(oteBox)
        box.delete(oteBox)
        oteBox := na
    dashOte := "-"
    if showOte and rngDir != 0 and not na(rngH) and not na(rngL) and (rngH - rngL) >= 2 * syminfo.mintick
        float r    = rngH - rngL
        float b618 = rngDir == 1 ? rngH - 0.618 * r : rngL + 0.618 * r
        float b786 = rngDir == 1 ? rngH - 0.786 * r : rngL + 0.786 * r
        float p705 = rngDir == 1 ? rngH - 0.705 * r : rngL + 0.705 * r
        float eq   = rngL + 0.5 * r
        int   x1   = math.min(rngHBar, rngLBar)
        color oc   = f_zoneColor(rngDir)
        oteBox := box.new(x1, math.max(b618, b786), bar_index + 5, math.min(b618, b786), border_color = color.new(oc, 60), bgcolor = color.new(oc, math.min(100, zoneAlpha + 8)), text = rngDir == 1 ? "OTE LONG" : "OTE SHORT", text_size = size.tiny, text_color = color.new(oc, 0), text_halign = text.align_right)
        array.push(oteLines, line.new(x1, p705, bar_index + 5, p705, color = oc, width = 2))
        array.push(oteLines, line.new(x1, eq,   bar_index + 5, eq,   color = color.new(oc, 40), style = line.style_dotted))
        array.push(oteLines, line.new(x1, rngH, bar_index + 5, rngH, color = color.new(oc, 70)))
        array.push(oteLines, line.new(x1, rngL, bar_index + 5, rngL, color = color.new(oc, 70)))
        dashOte := (rngDir == 1 ? "LONG" : "SHORT") + " H=" + f_fmt(rngH) + " L=" + f_fmt(rngL) + " 0.705=" + f_fmt(p705)
```

Dashboard row 8 (replace the Task 1 placeholder): `f_cell(8, "OTE", dashOte)`.

- [ ] **Step 4: Build, test, compile**

Run: `python scripts/build_pine_lab.py && python -m pytest -q tests/test_pine_lab_build.py tests/test_pine_lab_parity.py -p no:cacheprovider`
Expected: PASS.
Run: `node C:/Users/utkuc/tradingview-mcp/src/cli/index.js pine check --file C:/Users/utkuc/Downloads/efloud-bot/pine/efloud_lab.pine`
Expected: `"error_count": 0`.
Run: `git diff --exit-code pine/lab/core.pine pine/efloud_lab_strategy.pine` → exit 0.

- [ ] **Step 5: Commit**

```bash
git add pine/lab/tail_indicator.pine pine/efloud_lab.pine tests/test_pine_lab_build.py
git commit -m "feat(pine-lab): fixed-range OTE zone (0.618-0.786 band, 0.705 and EQ lines) with dashboard row"
```

---

### Task 7: Python reference expectations — `pine_lab_visuals.py` + `visuals` subcommand

**Files:**
- Create: `scripts/pine_lab_visuals.py`
- Create: `tests/test_pine_lab_visuals.py`
- Modify: `scripts/pine_lab_parity.py:573-600` (`main`: register the `visuals` subparser)

**Interfaces:**
- Produces (pure functions, numpy arrays `h, l, c, v` of the analysed frame):
  - `swept_pivots(pivots: list[tuple[int, float]], is_high: bool, h, l, swing_len: int) -> list[bool]`
  - `swept_equals(equals, h, l, eq_len: int) -> list[bool]`
  - `volume_confirmed(idx: int, is_high: bool, h, l, v, vma) -> bool`
  - `classify_flips(result, h, l, c, swing_len: int, window: int) -> list[dict]` — dicts `{top, bot, idx, created, flip, cls, dead, dir}` with `cls ∈ {"BB","MB","NONE"}`.
  - `ote_range(result, h, l, c) -> dict | None` — `{h, l, hBar, lBar, dir, b618, b786, p705, eq}`.
  - `expected_visuals(df, cfg, warmup: int) -> dict` — JSON-ready sets for OB (swing/internal), FVG, liquidity, BB/MB, OTE.
- Consumes: `engine.smc_v2.luxalgo.analyze`, `LuxResult.{active_obs, active_fvgs, equals, swing_high_pivots, swing_low_pivots, breaks}`, `pine_lab_parity.load_ohlcv_csv`, `load_config`.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_pine_lab_visuals.py`:

```python
"""Pure-function references for the indicator's display-only layers (spec §6.4)."""
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts import pine_lab_visuals as vis  # noqa: E402


def test_swept_pivots_requires_wick_after_confirmation_window():
    h = np.array([10, 11, 12, 11, 10, 10, 13, 10], dtype=float)
    l = h - 1
    # pivot high 12 at bar 2; swing_len 2 → sweep only counts from bar 5 on; bar 6 high 13 > 12 → swept
    assert vis.swept_pivots([(2, 12.0)], True, h, l, 2) == [True]
    assert vis.swept_pivots([(2, 14.0)], True, h, l, 2) == [False]


def test_volume_confirmed_rule():
    h = np.array([1, 2, 3, 4], dtype=float); l = h - 1
    v = np.array([5, 6, 7, 8], dtype=float); vma = np.array([7, 7, 7, 7], dtype=float)
    assert vis.volume_confirmed(3, True, h, l, v, vma) is True          # rising highs, rising vol, 8 > 7
    assert vis.volume_confirmed(2, True, h, l, v, vma) is False         # 7 > 7 fails
    assert vis.volume_confirmed(3, False, h, l, v, vma) is False        # lows are rising, not falling


def test_classify_flips_bb_vs_mb_on_bear_ob():
    # bear OB candle idx=5 top=20 bot=18, created at 7 (break), swing low pivot at bar 1 price 10 (ref A)
    from engine.smc_v2.luxalgo import LuxBreak, LuxOrderBlock
    ob = LuxOrderBlock(bar_high=20.0, bar_low=18.0, idx=5, ts="t5", bias="BEAR", internal=True, created_idx=7)
    brk = LuxBreak(kind="CHoCH", direction="BEAR", level=15.0, pivot_idx=4, idx=7, ts="t7", internal=True, order_block=ob)
    res = type("R", (), {})()
    res.breaks = [brk]; res.swing_low_pivots = [(1, 10.0)]; res.swing_high_pivots = []
    n = 12
    h = np.full(n, 19.0); l = np.full(n, 17.0); c = np.full(n, 18.5)
    l[8] = 9.0                                  # sweeps A=10 before the flip
    c[10] = 21.0                                # flip: close > top at bar 10
    out = vis.classify_flips(res, h, l, c, swing_len=1, window=750)
    assert out[0]["cls"] == "BB" and out[0]["flip"] == 10 and out[0]["dir"] == 1
    l[8] = 17.0                                 # no sweep → MB
    out = vis.classify_flips(res, h, l, c, swing_len=1, window=750)
    assert out[0]["cls"] == "MB"


def test_ote_range_direction_and_levels():
    from engine.smc_v2.luxalgo import LuxBreak, LuxOrderBlock
    ob = LuxOrderBlock(bar_high=104.0, bar_low=102.0, idx=3, ts="t3", bias="BULL", internal=False, created_idx=6)
    brk = LuxBreak(kind="BOS", direction="BULL", level=105.0, pivot_idx=2, idx=6, ts="t6", internal=False, order_block=ob)
    res = type("R", (), {})(); res.breaks = [brk]
    h = np.array([101, 102, 103, 104, 105, 106, 110, 108, 109], dtype=float)
    l = h - 2.0
    c = h - 1.0
    r = vis.ote_range(res, h, l, c)
    assert r["dir"] == 1 and r["h"] == 110.0 and r["l"] == 101.0       # L = min low over [pivot=2 .. break=6] = 103-2
    assert r["p705"] == pytest.approx(110 - 0.705 * 9)
    assert r["eq"] == pytest.approx(101 + 0.5 * 9)


def test_expected_visuals_keys():
    idx = pd.date_range("2026-01-01", periods=900, freq="15min")
    rng = np.random.default_rng(1)
    close = 100 + np.cumsum(rng.normal(0, 0.5, 900))
    df = pd.DataFrame({"open": close, "high": close + 0.3, "low": close - 0.3, "close": close, "volume": 1.0}, index=idx)
    cfg = {"smc_v2": {"luxalgo": {"swing_length": 50, "internal_length": 5, "eq_length": 3, "eq_threshold": 0.1,
                                  "ob_filter": "ATR", "ob_mitigation": "HIGHLOW", "fvg_auto_threshold": True}}}
    out = vis.expected_visuals(df, cfg, warmup=100)
    assert set(out) == {"ob_swing", "ob_internal", "fvg", "liquidity", "flips", "ote", "meta"}
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest -q tests/test_pine_lab_visuals.py -p no:cacheprovider`
Expected: FAIL with `ModuleNotFoundError: scripts.pine_lab_visuals`.

- [ ] **Step 3: Create `scripts/pine_lab_visuals.py`**

```python
#!/usr/bin/env python3
"""Reference expectations for the EFloud Lab indicator's display-only zone layers.

Mirrors pine/lab/tail_indicator.pine rules (spec docs/superpowers/specs/2026-11-06-lab-indicator-visuals-design.md):
OB/FVG/liquidity straight from lx.analyze(); BB/MB (two-scale sweep rule) and the fixed-range OTE as pure functions.
Used by `pine_lab_parity.py visuals` to produce expected.json for TradingView comparisons.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from engine.smc_v2 import luxalgo as lx  # noqa: E402


def swept_pivots(pivots: list, is_high: bool, h: np.ndarray, l: np.ndarray, swing_len: int) -> list:
    """core.pine: swept when a bar after `bar + swing_len` trades through the level (wick)."""
    out = []
    for bar, price in pivots:
        start = bar + swing_len + 1
        seg = h[start:] if is_high else l[start:]
        out.append(bool(seg.size and ((seg > price).any() if is_high else (seg < price).any())))
    return out


def swept_equals(equals: list, h: np.ndarray, l: np.ndarray, eq_len: int) -> list:
    out = []
    for e in equals:
        is_high = e.kind == "EQH"
        start = e.idx_b + eq_len + 1
        seg = h[start:] if is_high else l[start:]
        out.append(bool(seg.size and ((seg > e.price_b).any() if is_high else (seg < e.price_b).any())))
    return out


def volume_confirmed(idx: int, is_high: bool, h: np.ndarray, l: np.ndarray, v: np.ndarray, vma: np.ndarray) -> bool:
    """3 bars ending at idx: rising highs (falling lows), rising volume, last volume above its 60-bar SMA."""
    if idx < 2 or idx >= len(v) or np.isnan(vma[idx]):
        return False
    p = h if is_high else l
    mono = (p[idx - 2] < p[idx - 1] < p[idx]) if is_high else (p[idx - 2] > p[idx - 1] > p[idx])
    return bool(mono and v[idx - 2] < v[idx - 1] < v[idx] and v[idx] > vma[idx])


def _last_pivot_before(pivots: list, bar: int) -> Optional[float]:
    px = None
    for b, p in pivots:
        if b < bar:
            px = p
    return px


def classify_flips(result, h: np.ndarray, l: np.ndarray, c: np.ndarray, swing_len: int, window: int) -> list:
    """Two-scale rule (spec §3.2). A pivot is known to the tail only once confirmed (bar + swing_len <= created)."""
    n = len(c)
    out = []
    seen = set()
    for b in result.breaks:
        ob = b.order_block
        if ob is None or id(ob) in seen:
            continue
        seen.add(id(ob))
        bear = ob.bias == "BEAR"
        top, bot = max(ob.bar_high, ob.bar_low), min(ob.bar_high, ob.bar_low)
        piv = [(pb, pp) for pb, pp in (result.swing_low_pivots if bear else result.swing_high_pivots) if pb + swing_len <= ob.created_idx]
        ref = _last_pivot_before(piv, ob.idx)
        rec = {"top": float(top), "bot": float(bot), "idx": int(ob.idx), "created": int(ob.created_idx),
               "flip": -1, "cls": "NONE", "dead": False, "dir": 1 if bear else -1}
        if ref is None:
            out.append(rec)
            continue
        leg = l[ob.idx + 1:ob.created_idx + 1].min() if bear else h[ob.idx + 1:ob.created_idx + 1].max()
        for t in range(ob.created_idx + 1, min(n, ob.created_idx + 1 + window)):
            if (c[t] > top) if bear else (c[t] < bot):
                rec["flip"] = t
                rec["cls"] = "BB" if ((leg < ref) if bear else (leg > ref)) else "MB"
                after = c[t + 1:]
                rec["dead"] = bool(after.size and ((after < bot).any() if bear else (after > top).any()))
                break
            leg = min(leg, l[t]) if bear else max(leg, h[t])
        out.append(rec)
    return out


def ote_range(result, h: np.ndarray, l: np.ndarray, c: np.ndarray) -> Optional[dict]:
    """Fixed swing range (spec §3.5) evaluated bar by bar up to the last bar."""
    n = len(c)
    swing = {}
    for b in result.breaks:
        if not b.internal:
            swing.setdefault(b.idx, []).append(b)
    H = L = None
    hb = lb = -1
    d = 0
    for t in range(n):
        for b in swing.get(t, []):                       # last swing break on the bar wins (core order)
            ob = b.order_block
            if ob is None:
                continue
            lo_seg = l[b.pivot_idx:t + 1]
            hi_seg = h[b.pivot_idx:t + 1]
            L, H = float(lo_seg.min()), float(hi_seg.max())
            lb = b.pivot_idx + int(np.flatnonzero(lo_seg == L)[-1])
            hb = b.pivot_idx + int(np.flatnonzero(hi_seg == H)[-1])
        if H is None:
            continue
        if h[t] > H:
            H, hb = float(h[t]), t
        if l[t] < L:
            L, lb = float(l[t]), t
        d = 1 if hb > lb else -1 if hb < lb else d
    if H is None or d == 0:
        return None
    r = H - L
    long_ = d == 1
    return {"h": H, "l": L, "hBar": hb, "lBar": lb, "dir": d,
            "b618": H - 0.618 * r if long_ else L + 0.618 * r,
            "b786": H - 0.786 * r if long_ else L + 0.786 * r,
            "p705": H - 0.705 * r if long_ else L + 0.705 * r,
            "eq": L + 0.5 * r}


def expected_visuals(df: pd.DataFrame, cfg: dict, warmup: int = 100) -> dict:
    lux_cfg = cfg.get("smc_v2", {}).get("luxalgo", {}) or {}
    lc = lx.LuxConfig.from_dict(lux_cfg)
    res = lx.analyze(df, lc)
    h, l, c = df.high.to_numpy(float), df.low.to_numpy(float), df.close.to_numpy(float)
    v = df["volume"].to_numpy(float) if "volume" in df else np.zeros(len(df))
    vma = pd.Series(v).rolling(60).mean().to_numpy()
    sw, eqn = int(lux_cfg.get("swing_length", 50)), int(lux_cfg.get("eq_length", 3))

    def box(o):
        return {"top": float(max(o.bar_high, o.bar_low)), "bot": float(min(o.bar_high, o.bar_low)), "idx": int(o.idx)}

    liq = []
    for is_high, pivs in ((True, res.swing_high_pivots), (False, res.swing_low_pivots)):
        for (bar, price), swept in zip(pivs, swept_pivots(pivs, is_high, h, l, sw)):
            if bar >= warmup:
                liq.append({"kind": "BSL" if is_high else "SSL", "price": float(price), "bar": int(bar), "swept": swept,
                            "vol": volume_confirmed(bar, is_high, h, l, v, vma)})
    for e, swept in zip(res.equals, swept_equals(res.equals, h, l, eqn)):
        if e.idx_b >= warmup:
            liq.append({"kind": e.kind, "price": float(e.price_b), "bar": int(e.idx_b), "swept": swept,
                        "vol": volume_confirmed(e.idx_b, e.kind == "EQH", h, l, v, vma)})
    return {
        "meta": {"bars": len(df), "warmup": warmup, "swing_len": sw},
        "ob_swing": [box(o) for o in res.active_obs(internal=False) if o.idx >= warmup],
        "ob_internal": [box(o) for o in res.active_obs(internal=True) if o.idx >= warmup],
        "fvg": [{"top": float(f.top), "bot": float(f.bot), "idx": int(f.idx)} for f in res.active_fvgs() if f.idx >= warmup],
        "liquidity": liq,
        "flips": [f for f in classify_flips(res, h, l, c, sw, 750) if f["idx"] >= warmup and f["flip"] >= 0 and not f["dead"]],
        "ote": ote_range(res, h, l, c),
    }


def cmd_visuals(a) -> int:
    from scripts.pine_lab_parity import load_config, load_ohlcv_csv
    df = load_ohlcv_csv(a.ohlcv).tail(a.window)
    out = expected_visuals(df, load_config(a.config), warmup=a.warmup)
    Path(a.out).write_text(json.dumps(out, indent=1), encoding="utf-8")
    print(f"visuals: ob {len(out['ob_swing'])}/{len(out['ob_internal'])} fvg {len(out['fvg'])} liq {len(out['liquidity'])} "
          f"flips {len(out['flips'])} ote {'-' if out['ote'] is None else out['ote']['dir']} -> {a.out}")
    return 0
```

In `scripts/pine_lab_parity.py::main`, after the `score` subparser add:

```python
    vz = sub.add_parser("visuals", help="expected zone sets for the indicator layers (spec §6.4)")
    vz.add_argument("--ohlcv", required=True)
    vz.add_argument("--config", default=str(ROOT / "configs" / "config.phase2_1k.yaml"))
    vz.add_argument("--window", type=int, default=750)
    vz.add_argument("--warmup", type=int, default=100)      # 2 × swing_len
    vz.add_argument("--out", default="expected_visuals.json")
    from scripts.pine_lab_visuals import cmd_visuals  # local import keeps the parity module import-light
    vz.set_defaults(fn=cmd_visuals)
```

- [ ] **Step 4: Run the tests**

Run: `python -m pytest -q tests/test_pine_lab_visuals.py tests/test_pine_lab_parity.py -p no:cacheprovider`
Expected: PASS. (`LuxBreak`/`LuxOrderBlock` are built with keyword arguments matching `engine/smc_v2/luxalgo.py:60-80`.)

- [ ] **Step 5: Smoke the CLI on real data**

Run: `PYTHONIOENCODING=utf-8 python scripts/pine_lab_parity.py visuals --ohlcv data/lab/BTC_15m.csv --out data/lab/BTC_visuals.json`
Expected: one summary line, file written (data/lab is git-ignored).

- [ ] **Step 6: Commit**

```bash
git add scripts/pine_lab_visuals.py scripts/pine_lab_parity.py tests/test_pine_lab_visuals.py
git commit -m "feat(pine-lab): visuals subcommand — Python reference sets for OB/FVG/liquidity/BB-MB/OTE layers"
```

---

### Task 8: TradingView verification run and docs

**Files:**
- Create: `docs/pine-lab/2026-11-06-indicator-visuals-verify.md` (results)
- Modify: `docs/pine-lab/README.md` (new §5 "Indicator görselleri"), `pine/PINE_SPEC.md` (append §21)

**Interfaces:** consumes the built indicator and `data/lab/<S>_visuals.json` from Task 7. No code changes.

- [ ] **Step 1: Load the indicator into TradingView**

TradingView Desktop running with CDP (`powershell -NoProfile -ExecutionPolicy Bypass -File C:\tmp\tv_restart.ps1`), chart BINANCE:BTCUSDT.P 15m. In the Pine Editor the saved script **"EFloud Lab"** must be the open one (ask the operator to open it from the editor's script menu; `pine_open` loads content but saves into the previously open script). Then:

```
node C:/Users/utkuc/tradingview-mcp/src/cli/index.js pine get | head -c 200      # confirm indicator("EFloud Lab"
node C:/Users/utkuc/tradingview-mcp/src/cli/index.js pine set --file C:/Users/utkuc/Downloads/efloud-bot/pine/efloud_lab.pine
```
MCP: `pine_smart_compile` → expect `has_errors: false`; `pine_get_console` → no `RE100…` runtime error; `capture_screenshot` for the visual checklist.

- [ ] **Step 2: Signal regression (spec §6.6)**

MCP `data_get_pine_labels study_filter="EFloud Lab" max_labels=500` with all new layers ON, keep only texts starting with `LONG ` / `SHORT `; then `indicator_set_inputs` turning `showBreakers/showFvg/showLiq/showOte` off and read again. Expected: identical multiset of (text, price). Record counts in the results file.

- [ ] **Step 3: Layer isolation reads (spec §6.3–6.5)**

For each layer set only that layer on (`showObs`, `showZones`, `showLevels` off too) and `maxZonesPerSide = 200`:
- OB: `data_get_pine_boxes` → set of (top, bot) vs `ob_swing + ob_internal` from `data/lab/BTC_visuals.json` (Python run on the same bars: regenerate the CSV right before with `python -I C:/tmp/fetch_klines.py BTCUSDT <start_ms> data/lab/BTC_15m.csv` so the last 750 bars match the chart).
- FVG: boxes vs `fvg`. BB/MB: boxes vs `flips` (`top/bot`). OTE: box = `[min(b618,b786), max(...)]`, `data_get_pine_lines` contains `p705`, `eq`, `h`, `l`.
- Liquidity: `data_get_pine_lines` vs `liquidity[*].price` (unswept), `★` labels vs `vol == true`.
- Match with tolerance `syminfo.mintick`; exclude objects whose `idx`/`bar` < `warmup` (first 100 bars of the 750-bar window). Report precision/recall per layer; thresholds OB/FVG/liquidity ≥ 98 %, BB/MB/OTE = 100 %.
- Dashboard: `data_get_pine_tables` row 7 counts vs the JSON list sizes (after the nearest-N cut, counts are ≤ Python's; compare with N = 200).

Repeat Steps 1–3 for ETHUSDT.P and SOLUSDT.P, and a stress run on BTCUSDT.P **1m** (compile + no runtime error + screenshot only).

- [ ] **Step 4: Write results and docs**

`docs/pine-lab/2026-11-06-indicator-visuals-verify.md`: per symbol a table (layer · Pine count · Python count · precision · recall · verdict), signal regression result, screenshots' checklist (texts readable, z-order, OTE direction = dashboard, swept lines end at the sweep bar, ★ levels bold), and any mismatch with its bar time and cause.

`docs/pine-lab/README.md` §5 (new): how to run `visuals`, the isolation procedure, and the "open EFloud Lab in the editor first" caveat.

`pine/PINE_SPEC.md` §21 (append): one paragraph per layer stating the rule and that it is display-only (link to the design spec), plus the ring-buffer index contract.

- [ ] **Step 5: Commit**

```bash
git add docs/pine-lab/2026-11-06-indicator-visuals-verify.md docs/pine-lab/README.md pine/PINE_SPEC.md
git commit -m "docs(pine-lab): indicator zone visuals — TradingView verification results, operator flow, PINE_SPEC §21"
```

---

## Self-review

- **Spec coverage:** §3.1 OB (Task 4), §3.2 BB/MB (Task 5), §3.3 FVG (Task 2), §3.4 liquidity + volume (Task 3), §3.5 OTE (Task 6), §4 budget/inputs/dashboard/z-order (Tasks 1, 2, 5, 6), §5 Pine rules + static test (Task 1 guard test applies to every later task), §6 verification (Tasks 7, 8), §7 order followed.
- **Placeholders:** none; every Pine/Python step carries its code.
- **Type consistency:** `Zone.kind` codes (0–4) match `f_boxZone`; `Flip.cls` (1 BB, 2 MB, 3 NONE) matches the drawing filter and `classify_flips` strings; `f_bufAt` signature `(array<float>, int)` used identically in Tasks 3–6; `dash*` globals (`dashLiq` Task 3, `dashObS/dashObI` Task 4, `dashBb/dashMb/dashFvg` Task 5, `dashOte` Task 6) are declared before use and read in the dashboard block; Python `classify_flips(result, h, l, c, swing_len, window)` and `ote_range(result, h, l, c)` match the tests and `expected_visuals`.
