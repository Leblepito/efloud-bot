"""Lane C copywriter tests — PR #12 (Phase 4a).

Consumes Lane B analysis JSON (§3.2), gates on ``confidence >= medium``, and
produces platform-agnostic copy (caption + thread + alt-text) that carries the
mandated disclaimer and passes the content-compliance checker (banned phrases,
no absolute-$, no performance-% — ratio/risk metrics only, decision #5).
Draft-only: writes copy artifacts to local disk, posts nothing.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from engine.content_jobs import COMPLIANCE_TR
from scripts.content_compliance import find_violations
from scripts.lane_c_copywriter import LaneCCopywriter

DATE = "2026-06-09"


def _analysis(event_id: str, confidence: str = "high", **over) -> dict:
    a = {
        "event_id": event_id,
        "symbol": "BTC/USDT",
        "timeframe": "15m",
        "direction": "LONG",
        "entry": 50000.0, "sl": 49000.0, "tp1": 52000.0, "tp2": 53000.0,
        "confluence": 85,
        "analysis": {
            "structure": "TRENDING",
            "smc_zones": [{"type": "FVG", "price_range": [49900, 50100], "freshness": "fresh"}],
            "invalidation": "15m kapanış 48800 altı",
            "risk_note": "R:R 1:2 to TP1",
            "summary": "15m FVG retest, bullish OB confluence",
            "confidence": confidence,
        },
    }
    a.update(over)
    return a


def _write_analysis(analysis_dir: Path, date: str, items: list[dict]) -> None:
    d = analysis_dir / date
    d.mkdir(parents=True, exist_ok=True)
    for a in items:
        (d / f"{a['event_id']}.json").write_text(
            json.dumps(a, ensure_ascii=False), encoding="utf-8")


@pytest.fixture
def dirs(tmp_path):
    analysis = tmp_path / "analysis"
    out = tmp_path / "copy"
    return analysis, out


def _writer(dirs, **kw) -> LaneCCopywriter:
    analysis, out = dirs
    return LaneCCopywriter(analysis_dir=analysis, out_dir=out, **kw)


def test_skips_low_confidence_analysis(dirs):
    analysis, out = dirs
    _write_analysis(analysis, DATE, [_analysis("a", confidence="low")])
    summary = _writer(dirs).run(date=DATE)
    assert summary["generated"] == 0
    assert summary["skipped_low_confidence"] == 1
    assert not (out / DATE / "a.json").exists()


def test_generates_copy_for_medium_and_high(dirs):
    analysis, out = dirs
    _write_analysis(analysis, DATE, [_analysis("a", confidence="medium"),
                                     _analysis("b", confidence="high")])
    summary = _writer(dirs).run(date=DATE)
    assert summary["generated"] == 2
    copy = json.loads((out / DATE / "a.json").read_text(encoding="utf-8"))
    assert copy["caption"]
    assert isinstance(copy["thread"], list) and copy["thread"]
    assert copy["alt_text"]


def test_copy_carries_disclaimer(dirs):
    _write_analysis(dirs[0], DATE, [_analysis("a")])
    _writer(dirs).run(date=DATE)
    copy = json.loads((dirs[1] / DATE / "a.json").read_text(encoding="utf-8"))
    assert COMPLIANCE_TR in copy["caption"]


def test_copy_has_rr_ratio_and_no_violations(dirs):
    _write_analysis(dirs[0], DATE, [_analysis("a")])
    _writer(dirs).run(date=DATE)
    copy = json.loads((dirs[1] / DATE / "a.json").read_text(encoding="utf-8"))
    assert "R:R" in copy["caption"]
    # The whole copy bundle must be compliance-clean (no $, no banned, no perf-%).
    blob = copy["caption"] + " " + " ".join(copy["thread"]) + " " + copy["alt_text"]
    assert find_violations(blob) == []


def test_non_compliant_generated_copy_is_quarantined(dirs):
    """Defense in depth: if a generated draft trips compliance it is not emitted."""
    analysis, out = dirs
    bad = _analysis("a")
    bad["analysis"]["summary"] = "Garantili getiri, kesin kazanç!"  # banned phrases
    _write_analysis(analysis, DATE, [bad])
    summary = _writer(dirs).run(date=DATE)
    assert summary["violations"] == 1
    assert summary["generated"] == 0
    assert not (out / DATE / "a.json").exists()


def test_summary_counts_mixed(dirs):
    _write_analysis(dirs[0], DATE, [
        _analysis("a", confidence="high"),
        _analysis("b", confidence="low"),
        _analysis("c", confidence="medium"),
    ])
    s = _writer(dirs).run(date=DATE)
    assert s["total"] == 3
    assert s["generated"] == 2
    assert s["skipped_low_confidence"] == 1


def test_missing_analysis_dir_is_noop(dirs):
    s = _writer(dirs).run(date=DATE)
    assert s["total"] == 0
    assert s["generated"] == 0


def test_rerun_is_idempotent_overwrite(dirs):
    _write_analysis(dirs[0], DATE, [_analysis("a")])
    w = _writer(dirs)
    first = w.run(date=DATE)
    second = w.run(date=DATE)
    assert first["generated"] == 1
    assert second["generated"] == 1  # stable, overwrites, no duplication
    assert len(list((dirs[1] / DATE).glob("*.json"))) == 1
