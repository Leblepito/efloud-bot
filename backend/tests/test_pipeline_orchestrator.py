"""Pipeline orchestrator tests — PR #15 (Phase 4b), Lane F metrics + wiring.

Ties the offline pipeline together for one cron tick: Lane B → Lane C → Lane D,
chaining artifact dirs, and rolls up per-stage metrics (Lane F) + the budget.
Draft-only; the approval→publish step is event-driven (Phase 5 poller), separate.
"""
from __future__ import annotations

import json

import pytest

from scripts.pipeline_orchestrator import PipelineOrchestrator

DATE = "2026-06-09"


def _event(eid: str) -> dict:
    return {
        "event_id": eid, "event_type": "content_job.created", "schema_version": "1.0.0",
        "occurred_at": f"{DATE}T00:00:00Z",
        "source": {"service": "efloud-bot", "env": "testnet", "commit": None, "loop_id": "l"},
        "signal": {"symbol": "BTC/USDT", "direction": "LONG", "entry": 50000.0, "sl": 49000.0,
                   "tp1": 52000.0, "tp2": 53000.0, "confluence": 85, "timeframe": "15m",
                   "horizon": None, "regime": "TRENDING", "reasons": ["FVG"], "reasons_detail": {}},
        "compliance": {"disclaimer_tr": "x", "disclaimer_en": "y", "no_guarantee": True},
    }


def _full_analysis_processor(ev: dict) -> dict:
    s = ev["signal"]
    return {
        "event_id": ev["event_id"], "symbol": s["symbol"], "timeframe": s["timeframe"],
        "direction": s["direction"], "entry": s["entry"], "sl": s["sl"],
        "tp1": s["tp1"], "tp2": s["tp2"], "confluence": s["confluence"],
        "analysis": {"structure": "TRENDING", "invalidation": "48800 altı",
                     "summary": "FVG retest", "confidence": "high"},
        "cost_usd": 0.01,
    }


def _write_jobs(tmp_path, events):
    jobs = tmp_path / "jobs"; jobs.mkdir()
    (jobs / f"{DATE}.jsonl").write_text(
        "\n".join(json.dumps(e) for e in events) + "\n", encoding="utf-8")
    return jobs


def test_orchestrator_chains_b_c_d_and_rolls_up(tmp_path):
    jobs = _write_jobs(tmp_path, [_event("a")])
    orch = PipelineOrchestrator(jobs_path=jobs, work_dir=tmp_path / "work",
                                lane_b_processor=_full_analysis_processor)
    m = orch.run(date=DATE)
    assert m["lane_b"]["succeeded"] == 1
    assert m["lane_c"]["generated"] == 1
    assert m["lane_d"]["generated"] == 1
    assert m["cost_usd"] == pytest.approx(0.01)
    assert "budget_remaining" in m


def test_orchestrator_low_confidence_stops_at_lane_c(tmp_path):
    def low_proc(ev):
        a = _full_analysis_processor(ev)
        a["analysis"]["confidence"] = "low"
        return a
    jobs = _write_jobs(tmp_path, [_event("a")])
    m = PipelineOrchestrator(jobs_path=jobs, work_dir=tmp_path / "work",
                             lane_b_processor=low_proc).run(date=DATE)
    assert m["lane_b"]["succeeded"] == 1
    assert m["lane_c"]["generated"] == 0          # gated on confidence
    assert m["lane_d"]["generated"] == 0


def test_orchestrator_emits_metrics_summary_via_notifier(tmp_path):
    jobs = _write_jobs(tmp_path, [_event("a")])
    sent = []
    PipelineOrchestrator(jobs_path=jobs, work_dir=tmp_path / "work",
                         lane_b_processor=_full_analysis_processor,
                         notifier=sent.append).run(date=DATE)
    assert len(sent) == 1
    assert "pipeline" in sent[0].lower()


def test_orchestrator_empty_day_is_noop(tmp_path):
    jobs = tmp_path / "jobs"; jobs.mkdir()
    m = PipelineOrchestrator(jobs_path=jobs, work_dir=tmp_path / "work",
                             lane_b_processor=_full_analysis_processor).run(date=DATE)
    assert m["lane_b"]["total"] == 0
    assert m["lane_d"]["generated"] == 0
