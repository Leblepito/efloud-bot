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
INDICATOR_ONLY_INPUTS = {"showObs", "showZones", "showLevels", "showDash", "maxDrawings"}

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
