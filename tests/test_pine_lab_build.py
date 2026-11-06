"""Build + lint guards for the Pine lab family (spec §7.2)."""
import re
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.build_pine_lab import PARTS, build  # noqa: E402

GEN_IND = ROOT / "pine" / "efloud_lab.pine"
GEN_STR = ROOT / "pine" / "efloud_lab_strategy.pine"
STRATEGY_ONLY_INPUTS = {"marginUsd", "leverage", "maxHoldHours", "tp1ClosePct", "moveSlToBe"}
INDICATOR_ONLY_INPUTS = {"showObs", "showZones", "showLevels", "showDash", "maxDrawings",
                         "showBreakers", "showFvg", "showLiq", "showOte", "showHistory", "obBodyOnly",
                         "liqVolumeConfirm", "maxZonesPerSide", "colBull", "colBear", "colNeutral", "zoneAlpha"}

INPUT_RE = re.compile(r"^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=\s*input\.(?:int|float|bool|string|timeframe)\(", re.M)
LEGACY_RE = re.compile(r"(?<![.\w])(study|security|ema|sma|atr|rsi|highest|lowest)\(")
SEC_RE = re.compile(r"request\.security\(\s*[^,]+,\s*[^,]+,\s*([A-Za-z_]\w*)\(")


def _inputs(text: str) -> set:
    return {m.group(1) for m in INPUT_RE.finditer(text)}


def _func_last_line(text: str, name: str) -> str:
    m = re.search(rf"^{name}\([^\n]*\)\s*=>\n((?:[ \t]+[^\n]*\n)+)", text, re.M)
    assert m, f"function {name} not found"
    body = [ln for ln in m.group(1).splitlines() if ln.strip()]
    return body[-1].strip()


@pytest.mark.parametrize("target", list(PARTS))
def test_generated_file_matches_build(target):
    assert target.exists(), f"{target} missing — run scripts/build_pine_lab.py"
    assert target.read_text(encoding="utf-8") == build()[target]


def test_input_names_in_sync():
    ind = _inputs(GEN_IND.read_text(encoding="utf-8")) - INDICATOR_ONLY_INPUTS
    stg = _inputs(GEN_STR.read_text(encoding="utf-8")) - STRATEGY_ONLY_INPUTS
    assert ind == stg, f"indicator-only={ind - stg} strategy-only={stg - ind}"
    assert "biasTf" in ind and "emitOnce" in ind


@pytest.mark.parametrize("path", [GEN_IND, GEN_STR])
def test_version_header_and_caps(path):
    lines = path.read_text(encoding="utf-8").splitlines()
    assert lines[0] == "//@version=6"
    decl = next(ln for ln in lines if ln.startswith(("indicator(", "strategy(")))
    for cap in ("max_lines_count", "max_labels_count", "max_boxes_count", "max_bars_back"):
        assert cap in decl, f"{cap} missing in {path.name}"


@pytest.mark.parametrize("path", [GEN_IND, GEN_STR])
def test_no_legacy_calls(path):
    code = "\n".join(ln.split("//")[0] for ln in path.read_text(encoding="utf-8").splitlines())
    assert not LEGACY_RE.search(code), LEGACY_RE.search(code).group(0)


@pytest.mark.parametrize("path", [GEN_IND, GEN_STR])
def test_security_calls_are_non_repainting(path):
    text = path.read_text(encoding="utf-8")
    calls = [ln for ln in text.splitlines() if "request.security(" in ln]
    assert calls, "lab must request an HTF bias series"
    for ln in calls:
        assert "lookahead = barmerge.lookahead_on" in ln, ln
        m = SEC_RE.search(ln)
        assert m, f"security expression must be a function call: {ln}"
        assert _func_last_line(text, m.group(1)).endswith("[1]"), m.group(1)


def test_check_mode_exit_code():
    res = subprocess.run([sys.executable, "scripts/build_pine_lab.py", "--check"], cwd=ROOT, capture_output=True, text=True)
    assert res.returncode == 0, res.stderr


def _func_body(text: str, name: str) -> str:
    m = re.search(rf"^{name}\([^\n]*\)\s*=>\n((?:[ \t]+[^\n]*\n|\n)+)", text, re.M)
    assert m, f"function {name} not found"
    return "\n".join(ln.split("//")[0] for ln in m.group(1).splitlines())


def test_store_ob_reads_bar_history_from_global_buffers():
    """f_storeOb runs only on break bars; a `x[off]` inside it reads the function's own call history,
    not bar history (TradingView 'should be called on each calculation'), so the OB scan must use
    the per-bar global buffers instead of the history operator."""
    core = (ROOT / "pine" / "lab" / "core.pine").read_text(encoding="utf-8")
    body = _func_body(core, "f_storeOb")
    assert not re.search(r"[A-Za-z_]\w*\s*\[", body), re.search(r"[A-Za-z_]\w*\s*\[", body).group(0)
    assert "bufPHi" in body and "bufPLo" in body


def test_confirm_reads_bar_history_from_global_buffers():
    """f_confirm is only called for IN_ZONE candidates: the same call-history hazard as f_storeOb, so it
    must index the open/close/time ring buffers (no `[off` history), and the buffers must cover the scan depth."""
    core = (ROOT / "pine" / "lab" / "core.pine").read_text(encoding="utf-8")
    body = _func_body(core, "f_confirm")
    assert "[off" not in body, "history reference left in f_confirm"
    assert not re.search(r"\b(open|close|high|low|time)[ \t]*\[", body)
    for buf in ("bufOpen", "bufClose", "bufTime"):
        assert buf in body and f"var array<" in core and re.search(rf"var array<\w+>\s+{buf}\b", core)
    cap = int(re.search(r"^bufCap\s*=\s*(\d+)", core, re.M).group(1))
    assert cap >= 992                                    # scan depth bound is min(recency + timeout + 2, 990) (+1 prior bar)
    assert "bufCap" in core.split("// after the structure pass")[1].split("// ====")[0]



TAIL = ROOT / "pine" / "lab" / "tail_indicator.pine"
HISTORY_RE = re.compile(r"\b[A-Za-z_]\w*[ \t]*\[[ \t]*[A-Za-z0-9_]")   # ident[ expr  (array.get is a call, not this)
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


def test_history_regex_ignores_tuple_literal_on_next_line():
    assert not HISTORY_RE.search("    dir := d\n    [h, l, hBar, lBar, dir]\n")
    assert HISTORY_RE.search("    float v = low[off]\n")
    assert HISTORY_RE.search("    v := bufHi [2]\n")
    assert HISTORY_RE.search("    x = close [1]\n")


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


def test_tail_defines_zone_helpers_and_fvg_layer():
    text = TAIL.read_text(encoding="utf-8")
    for needle in ("type Zone", "f_bufAt(", "f_drawNearest(", "var int bufLastBar", "zoneLayerBoxes", "if showFvg"):
        assert needle in text, needle
    body = _tail_function_bodies(text)["f_drawNearest"]
    assert "array.get" in body and "f_boxZone" in body


def test_tail_liquidity_layer_uses_tail_volume_buffers():
    text = TAIL.read_text(encoding="utf-8")
    for needle in ("var array<float> bufVol", "var array<float> bufVolMa", "f_sweepBar(", "f_volConfirmed(", "if showLiq", "liqLines"):
        assert needle in text, needle
    # ta.sma(volume, 60) must be a global (unconditional) line, never inside a function
    assert re.search(r"^volMa60\s*=\s*ta\.sma\(volume,\s*60\)", text, re.M)


def test_tail_ob_layer_uses_zone_pipeline():
    text = TAIL.read_text(encoding="utf-8")
    assert "f_drawObs(" not in text and "obBoxes" not in text
    for needle in ("f_obEdges(", "f_isBreakerCopy(", "f_collectObs(", "obBodyOnly"):
        assert needle in text, needle


def test_tail_flip_tracker_present_and_buffer_only():
    text = TAIL.read_text(encoding="utf-8")
    for needle in ("type Flip", "var array<Flip> flips", "f_lastPivotBefore(", "f_legExtInit(", "f_trackFlips(", "if showBreakers"):
        assert needle in text, needle
    bodies = _tail_function_bodies(text)
    assert "f_bufAt" in bodies["f_legExtInit"]
    assert "mitigatedIdx" not in bodies["f_trackFlips"], "flip tracking must not filter on mitigatedIdx (every flip happens on a mitigated OB)"


def test_tail_ote_range_state_and_drawing():
    text = TAIL.read_text(encoding="utf-8")
    for needle in ("var float rngH", "var float rngL", "var int rngDir", "f_updateRange(", "f_barOfExtreme(", "if showOte", "0.705"):
        assert needle in text, needle
    body = _tail_function_bodies(text)["f_updateRange"]
    assert "b.internal" in body and "rawLow" in body and "rawHigh" in body
