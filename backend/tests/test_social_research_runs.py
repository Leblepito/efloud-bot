"""Latest-compare-run aggregator + snapshot integration.

Covers the verdict-badges follow-up flagged in the PR #89 review: the
frontend SocialLearningCenter needs a PASS/WARN/REJECT label per
hypothesis, sourced from the latest backtest compare report. These
tests pin the aggregation + snapshot extension that feed that badge.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from backend.social.research_runs import (
    latest_runs_per_hypothesis,
    research_runs_payload,
    summary_verdict,
)


def _write_run(
    root: Path,
    name: str,
    *,
    hypothesis: str | None,
    gates: dict[str, str],
    doctrine_tags: list[str] | None = None,
    deltas: dict | None = None,
    write_comparison: bool = True,
) -> Path:
    run_dir = root / name
    run_dir.mkdir(parents=True, exist_ok=True)
    if write_comparison:
        report = {
            "v1": {"win_rate": 50.0},
            "v2": {"win_rate": 55.0},
            "deltas": deltas or {},
            "gates": gates,
            "hypothesis": hypothesis,
            "doctrine_tags": doctrine_tags or [],
        }
        (run_dir / "comparison.json").write_text(
            json.dumps(report), encoding="utf-8"
        )
    return run_dir


@pytest.mark.parametrize(
    "gates,expected",
    [
        ({}, "UNKNOWN"),
        ({"max_drawdown_pct": "pass"}, "PASS"),
        ({"max_drawdown_pct": "warn", "win_rate": "pass"}, "WARN"),
        ({"max_drawdown_pct": "hard_reject", "win_rate": "warn"}, "REJECT"),
        ({"max_drawdown_pct": "pass", "stop_hunt_rate": "weird_value"}, "UNKNOWN"),
    ],
)
def test_summary_verdict_precedence(gates, expected):
    assert summary_verdict(gates) == expected


def test_latest_runs_per_hypothesis_picks_newest_run(tmp_path):
    root = tmp_path / "reports" / "backtests"
    _write_run(
        root, "2026-05-10_compare_1sym_30d_aaaa",
        hypothesis="h1", gates={"max_drawdown_pct": "warn"}, doctrine_tags=["A"],
    )
    _write_run(
        root, "2026-05-20_compare_1sym_30d_bbbb",
        hypothesis="h1", gates={"max_drawdown_pct": "pass"}, doctrine_tags=["A", "B"],
    )
    _write_run(
        root, "2026-05-15_compare_2sym_30d_cccc",
        hypothesis="h2", gates={"max_drawdown_pct": "hard_reject"},
        doctrine_tags=["X"],
    )

    latest = latest_runs_per_hypothesis(root)

    assert set(latest.keys()) == {"h1", "h2"}
    assert latest["h1"].run_date == "2026-05-20"
    assert latest["h1"].doctrine_tags == ["A", "B"]
    assert latest["h2"].run_date == "2026-05-15"


def test_latest_runs_ignores_non_compare_and_no_hypothesis(tmp_path):
    root = tmp_path / "reports" / "backtests"
    _write_run(
        root, "2026-05-20_portfolio_9sym_365d_xxxx",
        hypothesis="h1", gates={"max_drawdown_pct": "pass"},
    )
    _write_run(
        root, "2026-05-21_compare_1sym_30d_yyyy",
        hypothesis=None, gates={"max_drawdown_pct": "pass"},
    )
    _write_run(
        root, "2026-05-22_compare_1sym_30d_zzzz",
        hypothesis="h1", gates={"max_drawdown_pct": "pass"},
    )

    latest = latest_runs_per_hypothesis(root)

    assert set(latest.keys()) == {"h1"}
    assert latest["h1"].run_date == "2026-05-22"


def test_latest_runs_handles_missing_or_corrupt_comparison(tmp_path):
    root = tmp_path / "reports" / "backtests"
    # Compare dir without comparison.json
    (root / "2026-05-22_compare_1sym_30d_empty").mkdir(parents=True)
    # Compare dir with broken JSON
    broken_dir = root / "2026-05-22_compare_1sym_30d_broken"
    broken_dir.mkdir(parents=True)
    (broken_dir / "comparison.json").write_text("{not valid json", encoding="utf-8")
    # Valid run
    _write_run(
        root, "2026-05-22_compare_1sym_30d_ok",
        hypothesis="h1", gates={"max_drawdown_pct": "pass"},
    )

    latest = latest_runs_per_hypothesis(root)
    assert set(latest.keys()) == {"h1"}


def test_latest_runs_empty_when_root_missing(tmp_path):
    assert latest_runs_per_hypothesis(tmp_path / "does-not-exist") == {}


def test_research_runs_payload_shape(tmp_path):
    root = tmp_path / "reports" / "backtests"
    _write_run(
        root, "2026-05-25_compare_1sym_30d_aaaa",
        hypothesis="social_ote_fvg_htf_bias_v1",
        gates={"max_drawdown_pct": "pass", "stop_hunt_rate": "pass"},
        doctrine_tags=["MSB", "OTE", "FVG", "HTF_BIAS"],
        deltas={"max_drawdown_pct": {"abs": -1.2, "rel_pct": -10.0}},
    )

    payload = research_runs_payload(root)

    assert "social_ote_fvg_htf_bias_v1" in payload
    entry = payload["social_ote_fvg_htf_bias_v1"]
    assert entry["verdict"] == "PASS"
    assert entry["gates"] == {"max_drawdown_pct": "pass", "stop_hunt_rate": "pass"}
    assert entry["doctrine_tags"] == ["MSB", "OTE", "FVG", "HTF_BIAS"]
    assert entry["run_date"] == "2026-05-25"
    assert "deltas" in entry
    assert entry["run_dir"].endswith("2026-05-25_compare_1sym_30d_aaaa")


def test_snapshot_includes_research_runs(tmp_path):
    from backend.social.reports import build_social_research_snapshot

    archive = tmp_path / "state" / "social_doctrine.jsonl"
    reports_root = tmp_path / "reports" / "backtests"
    _write_run(
        reports_root, "2026-05-25_compare_1sym_30d_aaaa",
        hypothesis="my_hypothesis",
        gates={"max_drawdown_pct": "warn"},
        doctrine_tags=["MSB"],
    )

    snapshot = build_social_research_snapshot(
        path=archive, reports_root=reports_root
    )

    assert "research_runs" in snapshot
    assert "my_hypothesis" in snapshot["research_runs"]
    assert snapshot["research_runs"]["my_hypothesis"]["verdict"] == "WARN"
    assert snapshot["research_only"] is True


def test_snapshot_research_runs_empty_when_no_reports(tmp_path):
    from backend.social.reports import build_social_research_snapshot

    archive = tmp_path / "state" / "social_doctrine.jsonl"
    reports_root = tmp_path / "reports" / "backtests"

    snapshot = build_social_research_snapshot(
        path=archive, reports_root=reports_root
    )

    assert snapshot["research_runs"] == {}
