"""Lane B consumer harness tests — PR #11 (Phase 4a).

The harness reads Lane A `content_job` JSONL, dispatches each *unprocessed* event
to an injected per-event processor (the real screenshot+Gemini work runs as a
Manus task in prod; here it is a fake), enforces a daily/per-batch budget, writes
the analysis artifact to a local-fallback dir, and persists an idempotent
processed-set. Draft-only: the harness never posts anything.

Spec: docs/superpowers/specs/2026-06-04-lane-b-screenshot-design.md
  §4 flow · §6 failure modes · §7 budget ($5/day = 300 events binding; 100/batch).
Out of scope here: the actual screenshot/Gemini call (Manus, external).
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.lane_b_consumer import (
    DEFAULT_BATCH_CAP,
    DEFAULT_DAILY_CAP,
    LaneBConsumer,
)

DATE = "2026-06-09"


# ── helpers ──────────────────────────────────────────────────────────────────

def _event(event_id: str, symbol: str = "BTC/USDT", **over) -> dict:
    sig = {
        "symbol": symbol, "direction": "LONG", "entry": 50000.0, "sl": 49000.0,
        "tp1": 52000.0, "tp2": 53000.0, "confluence": 85, "timeframe": "15m",
        "horizon": None, "regime": "TRENDING", "reasons": ["FVG", "OB"],
        "reasons_detail": {"trace_id": None},
    }
    ev = {
        "event_id": event_id,
        "event_type": "content_job.created",
        "schema_version": "1.0.0",
        "occurred_at": f"{DATE}T00:00:00Z",
        "source": {"service": "efloud-bot", "env": "testnet", "commit": None, "loop_id": "loop"},
        "signal": sig,
        "compliance": {"disclaimer_tr": "x", "disclaimer_en": "y", "no_guarantee": True},
    }
    ev.update(over)
    return ev


def _write_jobs(jobs_dir: Path, date: str, events: list[dict]) -> Path:
    f = jobs_dir / f"{date}.jsonl"
    with f.open("w", encoding="utf-8") as fh:
        for e in events:
            fh.write(json.dumps(e, ensure_ascii=False) + "\n")
    return f


def _ok_processor(event: dict) -> dict:
    """A successful screenshot+analysis stand-in (Manus task result, §3.2)."""
    return {
        "event_id": event["event_id"],
        "symbol": event["signal"]["symbol"],
        "timeframe": event["signal"]["timeframe"],
        "chart_local": f"/tmp/lane-b/{event['event_id']}.png",
        "model": "gemini-2.5-pro",
        "analysis": {"structure": "TRENDING", "confidence": "high",
                     "summary": "LONG FVG retest"},
        "cost_usd": 0.012,
        "latency_ms": 12000,
    }


class _CountingProcessor:
    """Counts calls; optionally fails for specific event_ids."""

    def __init__(self, fail_ids: set[str] | None = None):
        self.calls: list[str] = []
        self.fail_ids = fail_ids or set()

    def __call__(self, event: dict) -> dict:
        self.calls.append(event["event_id"])
        if event["event_id"] in self.fail_ids:
            raise RuntimeError("gemini parse fail")
        return _ok_processor(event)


@pytest.fixture
def dirs(tmp_path):
    jobs = tmp_path / "content_jobs"; jobs.mkdir()
    state = tmp_path / "state"; state.mkdir()
    artifacts = tmp_path / "lane_b"; artifacts.mkdir()
    return jobs, state, artifacts


def _consumer(dirs, processor, **kw) -> LaneBConsumer:
    jobs, state, artifacts = dirs
    return LaneBConsumer(
        jobs_path=jobs, state_path=state, artifacts_path=artifacts,
        processor=processor, **kw,
    )


# ── tests ────────────────────────────────────────────────────────────────────

def test_processes_events_and_writes_local_analysis_artifact(dirs):
    """§4/§6.1: each unprocessed event → processor → analysis JSON on local disk."""
    jobs, state, artifacts = dirs
    _write_jobs(jobs, DATE, [_event("a"), _event("b")])
    c = _consumer(dirs, _ok_processor)

    summary = c.run_batch(date=DATE)

    assert summary["succeeded"] == 2
    assert summary["failed"] == 0
    # Local-fallback artifact per event (§3.2 analysis JSON).
    art_a = artifacts / "analysis" / DATE / "a.json"
    assert art_a.exists()
    payload = json.loads(art_a.read_text(encoding="utf-8"))
    assert payload["event_id"] == "a"
    assert payload["analysis"]["structure"] == "TRENDING"


def test_idempotent_skips_already_processed_events(dirs):
    """§6.7: a second run over the same file processes nothing (event_id set)."""
    _write_jobs(dirs[0], DATE, [_event("a"), _event("b")])
    proc = _CountingProcessor()
    c = _consumer(dirs, proc)

    first = c.run_batch(date=DATE)
    second = c.run_batch(date=DATE)

    assert first["succeeded"] == 2
    assert second["succeeded"] == 0
    assert second["skipped"] == 2
    assert proc.calls == ["a", "b"]  # processor NOT called again on run 2


def test_processed_set_persists_across_instances(dirs):
    """Idempotency survives a fresh process (state written to disk, not memory)."""
    _write_jobs(dirs[0], DATE, [_event("a")])
    c1 = _consumer(dirs, _ok_processor)
    c1.run_batch(date=DATE)

    proc2 = _CountingProcessor()
    c2 = _consumer(dirs, proc2)  # brand-new object, same state_path
    summary = c2.run_batch(date=DATE)

    assert summary["skipped"] == 1
    assert proc2.calls == []


def test_failed_event_is_not_marked_processed_and_retries(dirs):
    """§6.3/§6.4: a processor failure does not mark the event done; it retries."""
    _write_jobs(dirs[0], DATE, [_event("a"), _event("b")])
    proc = _CountingProcessor(fail_ids={"b"})
    c = _consumer(dirs, proc)

    first = c.run_batch(date=DATE)
    assert first["succeeded"] == 1
    assert first["failed"] == 1

    # b retries on the next run; now succeeds (failure cleared).
    proc.fail_ids = set()
    second = c.run_batch(date=DATE)
    assert second["succeeded"] == 1   # only b
    assert second["skipped"] == 1     # a already done
    assert proc.calls == ["a", "b", "b"]


def test_daily_budget_cap_defers_excess_and_flags(dirs):
    """§7: daily cap is binding; excess deferred + budget_exceeded alert set."""
    _write_jobs(dirs[0], DATE, [_event("a"), _event("b"), _event("c")])
    c = _consumer(dirs, _ok_processor, daily_cap=2)

    first = c.run_batch(date=DATE)
    assert first["succeeded"] == 2
    assert first["deferred"] == 1
    assert first["budget_exceeded"] is True
    assert first["budget_remaining"] == 0

    # Same UTC day: cap already spent → nothing more processed.
    second = c.run_batch(date=DATE)
    assert second["succeeded"] == 0
    assert second["budget_exceeded"] is True


def test_batch_cap_limits_per_run_without_budget_alert(dirs):
    """§7: per-batch cap throttles throughput; remainder deferred (not an alert)."""
    _write_jobs(dirs[0], DATE, [_event(x) for x in "abcde"])
    c = _consumer(dirs, _ok_processor, batch_cap=2, daily_cap=300)

    first = c.run_batch(date=DATE)
    assert first["succeeded"] == 2
    assert first["deferred"] == 3
    assert first["budget_exceeded"] is False  # daily cap not breached

    second = c.run_batch(date=DATE)
    assert second["succeeded"] == 2
    third = c.run_batch(date=DATE)
    assert third["succeeded"] == 1
    assert third["deferred"] == 0


def test_missing_daily_file_is_noop(dirs):
    """No JSONL for the date → empty summary, no crash."""
    c = _consumer(dirs, _ok_processor)
    summary = c.run_batch(date=DATE)
    assert summary["total"] == 0
    assert summary["succeeded"] == 0


def test_malformed_jsonl_line_is_skipped(dirs):
    """A corrupt line is skipped defensively; valid events still process."""
    jobs = dirs[0]
    f = jobs / f"{DATE}.jsonl"
    with f.open("w", encoding="utf-8") as fh:
        fh.write(json.dumps(_event("a"), ensure_ascii=False) + "\n")
        fh.write("{ this is not json\n")
        fh.write(json.dumps(_event("b"), ensure_ascii=False) + "\n")
    c = _consumer(dirs, _ok_processor)

    summary = c.run_batch(date=DATE)

    assert summary["succeeded"] == 2
    assert summary["malformed"] == 1


def test_summary_aggregates_cost(dirs):
    """Per-event cost_usd is summed for the budget rollup."""
    _write_jobs(dirs[0], DATE, [_event("a"), _event("b")])
    c = _consumer(dirs, _ok_processor)
    summary = c.run_batch(date=DATE)
    assert summary["cost_usd"] == pytest.approx(0.024)


def test_notifier_receives_batch_summary(dirs):
    """§4: a Telegram batch summary is emitted via the injected notifier."""
    _write_jobs(dirs[0], DATE, [_event("a")])
    sent: list[str] = []
    c = _consumer(dirs, _ok_processor, notifier=sent.append)
    c.run_batch(date=DATE)
    assert len(sent) == 1
    assert "Lane B" in sent[0]


def test_defaults_match_spec_budget():
    """§7: 100 events/batch, 300 events/day (the binding $5/day cap)."""
    assert DEFAULT_BATCH_CAP == 100
    assert DEFAULT_DAILY_CAP == 300


# ── CLI entry (cron tick, §10.2) ─────────────────────────────────────────────

def test_main_dry_run_processes_and_prints_summary(dirs, capsys):
    """`main --dry-run` runs the harness with an offline stub and prints JSON."""
    from scripts.lane_b_consumer import main
    jobs, state, artifacts = dirs
    _write_jobs(jobs, DATE, [_event("a")])

    summary = main([
        "--dry-run", "--jobs", str(jobs), "--state", str(state),
        "--artifacts", str(artifacts), "--date", DATE,
    ])

    assert summary["succeeded"] == 1
    assert (artifacts / "analysis" / DATE / "a.json").exists()
    assert '"succeeded": 1' in capsys.readouterr().out


def test_dry_run_processor_builds_tradingview_url_and_zero_cost():
    """§4: chart URL = BINANCE:{SYM}.P&interval={tf}; dry-run costs nothing."""
    from scripts.lane_b_consumer import _dry_run_processor
    a = _dry_run_processor(_event("a", symbol="BTC/USDT"))
    assert a["chart_url"] == (
        "https://www.tradingview.com/chart/?symbol=BINANCE:BTCUSDT.P&interval=15m"
    )
    assert a["cost_usd"] == 0.0
