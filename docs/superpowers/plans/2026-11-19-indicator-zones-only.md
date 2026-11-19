# Indicator zones-only + zone event alerts — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship "u2algo Price Action" as a zones-only indicator (no LONG/SHORT signals) with informational zone-entry and liquidity-sweep alerts.

**Architecture:** Edit only `pine/lab/tail_indicator.pine`; regenerate `pine/efloud_lab.pine` with `scripts/build_pine_lab.py`. `core.pine`, heads and `tail_strategy.pine` stay untouched, so the parity strategy is byte-identical. Static pytest guards the generated file; TradingView MCP checks runtime.

**Tech Stack:** Pine Script v6, Python 3.11 / pytest, TradingView Desktop MCP.

## Global Constraints

- Spec: `docs/superpowers/specs/2026-11-19-indicator-zones-only-design.md`.
- Pine v6 only; never edit generated `pine/efloud_lab*.pine` by hand — edit `pine/lab/*` then `python scripts/build_pine_lab.py`.
- Do not touch `pine/lab/core.pine`, `pine/lab/head_*.pine`, `pine/lab/tail_strategy.pine`. Strategy file sha256 must stay `56bf544a61fdeea51553cd54d7040f4defc8fe02f1fe9900ad83f958e18c3c22`.
- No parallel function-local arrays used with `indexof`/`get` lock-step (RE10045); dedup = one `map<string, int>`.
- Alerts are informational only; text must say "informational, not a trade signal".
- Python: `C:/Users/utkuc/Downloads/efloud-bot/.venv311/Scripts/python.exe`. Work in worktree `C:/tmp/wt-ind` (branch `feat/indicator-zones-only`).
- Commit trailer: `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.

---

### Task 1: Remove the Signals layer from the indicator

**Files:**
- Modify: `pine/lab/tail_indicator.pine` (inputs lines 2-7; zoneBoxes/sig arrays ~26-28; signal block `if barstate.isconfirmed` / `for c in fired` ~349-374; `showZones` block in the `barstate.islast` drawing section; `f_dropSummary` + dashboard ~495-526)
- Generated: `pine/efloud_lab.pine`
- Test: `tests/test_pine_lab_zones_only.py` (create)

**Interfaces:**
- Consumes: nothing.
- Produces: indicator without `sigLines`, `sigLabels`, `zoneBoxes`, `showZones`, `showLevels`, `maxDrawings`, `f_dropSummary`; `tgChatId`/`tgTag` inputs remain (used by Task 2); dashboard table with 6 rows.

- [ ] **Step 1: Write the failing test** — create `tests/test_pine_lab_zones_only.py`:

```python
"""Zones-only publish build (spec docs/superpowers/specs/2026-11-19-indicator-zones-only-design.md)."""
import hashlib
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
IND = (ROOT / "pine" / "efloud_lab.pine").read_text(encoding="utf-8")
STRAT = ROOT / "pine" / "efloud_lab_strategy.pine"
STRAT_SHA = "56bf544a61fdeea51553cd54d7040f4defc8fe02f1fe9900ad83f958e18c3c22"


def test_signal_layer_removed():
    for token in ("sigLines", "sigLabels", "zoneBoxes", '"LONG "', '"SHORT "',
                  '"Entry/SL/TP lines"', '"Pending candidate zones"', '"Kept signal drawings"'):
        assert token not in IND, token


def test_dashboard_has_no_signal_engine_rows():
    for row in ('"Pending W/Z/R"', '"Po3"', '"Drops (last 20)"'):
        assert row not in IND, row
    for row in ('"Range EQ"', '"OTE"', '"Zones s/i·BB·MB·FVG·Liq"'):
        assert row in IND, row


def test_at_most_one_alert_call_site():
    assert len(re.findall(r"\balert\(", IND)) <= 1


def test_strategy_artefact_unchanged():
    assert hashlib.sha256(STRAT.read_bytes()).hexdigest() == STRAT_SHA
```

- [ ] **Step 2: Run to verify it fails**
Run: `python -m pytest tests/test_pine_lab_zones_only.py -q -p no:cacheprovider`
Expected: FAIL in `test_signal_layer_removed` and `test_dashboard_has_no_signal_engine_rows`; `test_strategy_artefact_unchanged` PASS.

- [ ] **Step 3: Edit `pine/lab/tail_indicator.pine`**
  1. Inputs (lines 2-7) become:
```pine
grpVis = "Görsel"
showObs     = input.bool(true, "Active OB boxes", group = grpVis)
showDash    = input.bool(true, "Dashboard", group = grpVis)
```
  2. Delete the three `var` lines `zoneBoxes`, `sigLines`, `sigLabels`.
  3. Delete the whole signal block that starts with `if barstate.isconfirmed` followed by `for c in fired` and ends after the two `while array.size(sigLines|sigLabels) > …` loops (≈ lines 349-374), including the `alert(alertMsg, …)` call.
  4. In the `barstate.islast` drawing section delete `f_clearBoxes(zoneBoxes)` and the `if showZones` / `for c in cands` block; change the z-order comment to `// z-order (bottom → top): OTE → FVG → OB/iOB → BB/MB → liquidity`.
  5. Delete `f_dropSummary()` (its only caller is the removed dashboard row).
  6. Dashboard: `var table dash = table.new(position.top_right, 2, 6, border_width = 1)` and the `if barstate.islast and showDash` block becomes:
```pine
if barstate.islast and showDash
    f_cell(0, "Variant", variantLabel)
    f_cell(1, "Bias " + biasTf, htfBias == 1 ? "BULL" : htfBias == -1 ? "BEAR" : "UNDEF")
    f_cell(2, "Macro " + macroTf, macroBias == 1 ? "BULL" : macroBias == -1 ? "BEAR" : "-")
    f_cell(3, "Range EQ", zoneOk ? f_fmt(zEq) : "-")
    f_cell(4, "Zones s/i·BB·MB·FVG·Liq", str.tostring(dashObS) + "/" + str.tostring(dashObI) + "·" + str.tostring(dashBb) + "·" + str.tostring(dashMb) + "·" + str.tostring(dashFvg) + "·" + str.tostring(dashLiq))
    f_cell(5, "OTE", dashOte)
```
  7. First line comment: `// ─── INDICATOR TAIL: zone drawings, dashboard, zone alerts ───────────────────`.

- [ ] **Step 4: Build and run tests**
Run: `python scripts/build_pine_lab.py && python scripts/build_pine_lab.py --check && python -m pytest tests/test_pine_lab_zones_only.py tests/test_pine_lab_build.py tests/test_pine_lab_visuals.py tests/test_pine_lab_variant.py tests/test_pine_lab_parity.py -q -p no:cacheprovider`
Expected: all PASS. If an existing pine-lab test asserted a removed token, update that assertion only and note it in the commit body.

- [ ] **Step 5: Commit**
```bash
git add pine/lab/tail_indicator.pine pine/efloud_lab.pine tests/test_pine_lab_zones_only.py
git commit -m "feat(pine): indicator drops the signal layer (zones-only publish build)"
```

### Task 2: Zone event alerts

**Files:**
- Modify: `pine/lab/tail_indicator.pine` (alert inputs after `tgTag`; new block at end of file)
- Generated: `pine/efloud_lab.pine`
- Test: `tests/test_pine_lab_zones_only.py`

**Interfaces:**
- Consumes: from the tail/core — `Zone`, `f_pushZone`, `f_collectObs(array<OB>, bool, array<Zone>)`, `f_obEdges(OB) → [top, bot]`, `flips` (`Flip` with `ob`, `flipBar`, `dead`, `cls`), `fvgs` (`top`, `bot`, `idx`, `bias`, `mitigatedIdx`), `shPiv`/`slPiv` (`price`, `bar`, `swept`), `equals` (`isHigh`, `priceB`, `idxB`, `swept`), `f_fmt`, `f_jsonEsc`, `f_htmlEsc`, `tgChatId`, `tgTag`.
- Produces: inputs `alertZones`, `alertSweep`; `var map<string, int> alertSeen`; one `alert()` call.

- [ ] **Step 1: Add failing tests** (append to `tests/test_pine_lab_zones_only.py`):
```python
def test_zone_alert_inputs_and_single_alert():
    assert '"Alert: zone entry"' in IND and '"Alert: liquidity sweep"' in IND
    assert len(re.findall(r"\balert\(", IND)) == 1
    assert "alert.freq_once_per_bar_close" in IND


def test_zone_alert_dedup_is_one_capped_map():
    assert "map.new<string, int>()" in IND
    assert "map.size(alertSeen) >= 500" in IND
    assert "barstate.isrealtime" in IND


def test_alert_text_is_informational():
    assert "informational, not a trade signal" in IND
```
- [ ] **Step 2: Run** `python -m pytest tests/test_pine_lab_zones_only.py -q -p no:cacheprovider` → the 3 new tests FAIL.
- [ ] **Step 3: Inputs** — after the `tgTag` line add:
```pine
alertZones = input.bool(true, "Alert: zone entry", group = grpAlert)
alertSweep = input.bool(true, "Alert: liquidity sweep", group = grpAlert)
```
- [ ] **Step 4: Alert block** — append at the end of `pine/lab/tail_indicator.pine`:
```pine
// ─── Zone event alerts (informational; spec 2026-11-19) ───────────────────────
// Realtime closed bars only. Dedup: one capped map (no parallel arrays, RE10045). The first realtime bar only
// seeds the map so levels swept long ago do not fire.
var map<string, int> alertSeen = map.new<string, int>()
var bool alertSeeded = false
prevHi = high[1]
prevLo = low[1]

f_zKey(string kind, int x1, float top, float bot) =>
    kind + ":" + str.tostring(x1) + ":" + f_fmt(top) + ":" + f_fmt(bot)

f_enteredNow(float top, float bot, float ph, float pl) =>
    low <= top and high >= bot and not (pl <= top and ph >= bot)

f_note(array<string> ev, string key, string txt, bool seeded) =>
    if not map.contains(alertSeen, key)
        if map.size(alertSeen) >= 500
            map.clear(alertSeen)
        map.put(alertSeen, key, 1)
        if seeded
            array.push(ev, txt)
    true

if barstate.isconfirmed and barstate.isrealtime
    array<string> ev = array.new<string>()
    if alertZones
        for f in fvgs
            if f.mitigatedIdx < 0 and f_enteredNow(f.top, f.bot, prevHi, prevLo)
                f_note(ev, f_zKey("FVG", f.idx, f.top, f.bot), "ZONE FVG " + (f.bias == 1 ? "BULL" : "BEAR") + " [" + f_fmt(f.bot) + "–" + f_fmt(f.top) + "]", alertSeeded)
        array<Zone> zo = array.new<Zone>()
        f_collectObs(swingObs, false, zo)
        f_collectObs(intObs, true, zo)
        for fl in flips
            if fl.flipBar >= 0 and not fl.dead and (fl.cls == 1 or fl.cls == 2)
                [zt, zb] = f_obEdges(fl.ob)
                f_pushZone(zo, zt, zb, fl.ob.idx, -fl.ob.bias, fl.cls == 1 ? "BB" : "MB", fl.cls == 1 ? 2 : 3, false)
        for z in zo
            if not z.faded and f_enteredNow(z.top, z.bot, prevHi, prevLo)
                f_note(ev, f_zKey(z.txt, z.x1, z.top, z.bot), "ZONE " + z.txt + " " + (z.dir == 1 ? "BULL" : "BEAR") + " [" + f_fmt(z.bot) + "–" + f_fmt(z.top) + "]", alertSeeded)
    if alertSweep
        for p in shPiv
            if p.swept
                f_note(ev, f_zKey("BSL", p.bar, p.price, p.price), "SWEEP BSL " + f_fmt(p.price), alertSeeded)
        for p in slPiv
            if p.swept
                f_note(ev, f_zKey("SSL", p.bar, p.price, p.price), "SWEEP SSL " + f_fmt(p.price), alertSeeded)
        for e in equals
            if e.swept
                f_note(ev, f_zKey(e.isHigh ? "EQH" : "EQL", e.idxB, e.priceB, e.priceB), "SWEEP " + (e.isHigh ? "EQH " : "EQL ") + f_fmt(e.priceB), alertSeeded)
    alertSeeded := true
    if array.size(ev) > 0
        string tgChat = str.trim(tgChatId)
        string msg = ""
        if tgChat == ""
            string evJson = ""
            for e in ev
                evJson := evJson + (evJson == "" ? "" : ",") + '"' + f_jsonEsc(e) + '"'
            msg := '{"symbol":"' + syminfo.ticker + '","tf":"' + timeframe.period + '","events":[' + evJson + '],"note":"informational, not a trade signal"}'
        else
            string tgText = "📍 <b>" + syminfo.ticker + " · " + timeframe.period + "</b>" + '\\n' + f_jsonEsc(f_htmlEsc(array.join(ev, " | "))) + '\\n' + "ℹ️ informational, not a trade signal" + '\\n' + f_jsonEsc(f_htmlEsc(tgTag))
            msg := '{"chat_id":"' + f_jsonEsc(tgChat) + '","text":"' + tgText + '","parse_mode":"HTML","disable_web_page_preview":true}'
        alert(msg, alert.freq_once_per_bar_close)
```
- [ ] **Step 5: Build + tests**: `python scripts/build_pine_lab.py && python scripts/build_pine_lab.py --check && python -m pytest tests/test_pine_lab_zones_only.py tests/test_pine_lab_*.py -q -p no:cacheprovider` → all PASS.
- [ ] **Step 6: Commit** `git add pine/lab/tail_indicator.pine pine/efloud_lab.pine tests/test_pine_lab_zones_only.py` → `feat(pine): informational zone-entry and liquidity-sweep alerts`.

### Task 3: Publish kit + product doc

**Files:** Modify `docs/indicator/tradingview-publish.md` (section (b) "How it works", "Settings", "Alerts", "Limitations"; checklist (c) "bota ayna sinyal motoru" item), `docs/indicator/u2algo-price-action.md` (§3 signals layer, §4 dashboard rows, §5 removed inputs, §6 alerts, §7 limits), `docs/pine-lab/README.md` (SON DURUM: zones-only product build).

- [ ] **Step 1:** In (b): delete the `[*][b]Signals:[/b] …` bullet; Dashboard bullet → "bias, range equilibrium, zone counts and OTE state"; Settings → drop "signal lines" and "Baseline: … SL/TP …" wording, keep structure lengths; Alerts → "Two optional alert types fire once per confirmed bar close: price entering an active order block, breaker/mitigation block or fair value gap, and a liquidity level (BSL/SSL, EQH/EQL) being swept. They are informational, not trade signals. Empty Telegram chat id = JSON payload; with a chat id the payload is ready for a Telegram bot webhook."; Limitations → add "The indicator does not generate entries, stops or targets."
- [ ] **Step 2:** In (c) replace "bota ayna sinyal motoru" with "bölge olayı alert'leri (bilgi amaçlı)".
- [ ] **Step 3:** Mirror the same facts in `docs/indicator/u2algo-price-action.md` §3-§7 (Turkish) and add a line to `docs/pine-lab/README.md` SON DURUM: "Yayın sürümü yalnız bölge haritası (2026-11-19, spec …); sinyal katmanı yalnız parity stratejisinde."
- [ ] **Step 4:** `python -m pytest tests/ci tests/collab tests/test_docs_param_parity.py -q -p no:cacheprovider` → PASS; commit `docs(indicator): zones-only publish kit and product doc`.

### Task 4: Runtime check on TradingView + PR

- [ ] **Step 1:** `tv_health_check` (MCP). If TV Desktop/debug port is down, stop and ask the operator to start it (`reference_tradingview_mcp_launch` memory).
- [ ] **Step 2:** Follow `skills/tradingview-mcp/SKILL.md` save-target cautions; `pine_set_source` ← `pine/efloud_lab.pine` → `pine_smart_compile` → `pine_get_errors` must be 0. Do NOT `pine_save` over a published script without operator OK.
- [ ] **Step 3:** On BTCUSDT.P 15m and ETHUSDT.P 15m: `capture_screenshot` (chart) — zones visible, no LONG/SHORT labels; `pine_get_console`/errors show no runtime error (RE10045).
- [ ] **Step 4:** `python scripts/regression_ledger.py render` + `check`; push; `gh pr create` with test + runtime evidence; operator publishes manually per `docs/indicator/tradingview-publish.md`.
