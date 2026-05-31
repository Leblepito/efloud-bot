"""Tests for scripts/evaluate_backtest_gates.py — the backtest gate verdict tool.

The tool turns a `comparison.json` (produced by `python -m backtest.cli compare`)
into a pass / warn / hard_reject verdict + an exit code, applying the HERMES.md
§6 Adım 3 gate targets. It reuses backtest.comparison.DEFAULT_GATES as the single
source of truth for thresholds rather than re-hardcoding them.

Works entirely from synthetic / fixture JSON — no real backtest run required.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.evaluate_backtest_gates import (
    EXIT_HARD_REJECT,
    EXIT_PASS,
    EXIT_WARN,
    build_verdict,
    format_table,
    main,
)

FIXTURE = Path(__file__).parent / "fixtures" / "comparison_sample.json"


def _comparison(v2_overrides: dict | None = None, drop: list[str] | None = None) -> dict:
    """An all-passing v1/v2 comparison; tweak v2 metrics or drop keys per test."""
    v1 = {
        "win_rate": 0.50, "avg_realized_rr": 1.55, "max_drawdown_pct": 10.0,
        "stop_hunt_rate": 0.40, "sharpe_like": 1.00,
    }
    v2 = {
        "win_rate": 0.55, "avg_realized_rr": 1.70, "max_drawdown_pct": 9.0,
        "stop_hunt_rate": 0.15, "sharpe_like": 1.10,
    }
    if v2_overrides:
        v2.update(v2_overrides)
    if drop:
        for k in drop:
            v1.pop(k, None)
            v2.pop(k, None)
    return {"v1": v1, "v2": v2}


# ── verdict logic ─────────────────────────────────────────────────

def test_all_pass_verdict_and_exit_code():
    verdict = build_verdict(_comparison())
    assert verdict["overall"] == "pass"
    assert verdict["exit_code"] == EXIT_PASS
    assert all(m["status"] == "pass" for m in verdict["metrics"].values())


def test_hard_reject_when_avg_rr_below_floor():
    """avg_realized_rr 1.0 < hard_reject_abs 1.2 → hard_reject, exit 2."""
    verdict = build_verdict(_comparison({"avg_realized_rr": 1.0}))
    assert verdict["metrics"]["avg_realized_rr"]["status"] == "hard_reject"
    assert verdict["overall"] == "hard_reject"
    assert verdict["exit_code"] == EXIT_HARD_REJECT


def test_warn_when_avg_rr_between_floor_and_target():
    """1.2 ≤ 1.35 < 1.5 → warn (not hard_reject), exit 1."""
    verdict = build_verdict(_comparison({"avg_realized_rr": 1.35}))
    assert verdict["metrics"]["avg_realized_rr"]["status"] == "warn"
    assert verdict["overall"] == "warn"
    assert verdict["exit_code"] == EXIT_WARN


def test_stop_hunt_rate_hard_reject_when_worse_than_v1():
    """stop_hunt_rate worse than v1 (ratio > hard_reject 1.0) → hard_reject
    (lower=better). NB: the canonical _evaluate_metric uses strict '>', so a
    ratio of exactly 1.0 is a warn, not a hard_reject — this test uses 0.50
    (1.25×v1) to land unambiguously in hard_reject."""
    verdict = build_verdict(_comparison({"stop_hunt_rate": 0.50}))
    assert verdict["metrics"]["stop_hunt_rate"]["status"] == "hard_reject"


def test_overall_is_worst_status():
    """A mix → overall reflects the worst (hard_reject dominates warn)."""
    verdict = build_verdict(_comparison({
        "avg_realized_rr": 1.35,    # warn
        "sharpe_like": 0.80,        # 0.80/1.0 = 0.8 < hard_reject 0.9 → hard_reject
    }))
    assert verdict["metrics"]["avg_realized_rr"]["status"] == "warn"
    assert verdict["metrics"]["sharpe_like"]["status"] == "hard_reject"
    assert verdict["overall"] == "hard_reject"


def test_missing_metric_is_skipped_not_treated_as_zero():
    """A metric absent from v1/v2 must be reported as skipped, NOT silently
    coerced to 0.0 (which would spuriously hard_reject avg_realized_rr)."""
    verdict = build_verdict(_comparison(drop=["sharpe_like"]))
    assert verdict["metrics"]["sharpe_like"]["status"] == "skip"
    assert "sharpe_like" in verdict["missing"]
    # Dropping a metric must not flip an otherwise-passing run.
    assert verdict["overall"] == "pass"


def test_verdict_metrics_carry_v1_v2_values():
    verdict = build_verdict(_comparison())
    m = verdict["metrics"]["win_rate"]
    assert m["v1"] == 0.50
    assert m["v2"] == 0.55


# ── rendering ─────────────────────────────────────────────────────

def test_format_table_plain_has_metrics_and_no_ansi():
    verdict = build_verdict(_comparison({"avg_realized_rr": 1.0}))
    table = format_table(verdict, color=False)
    assert "avg_realized_rr" in table
    assert "hard_reject" in table
    assert "win_rate" in table
    assert "\x1b[" not in table  # no ANSI escape codes when color=False


def test_format_table_color_has_ansi():
    verdict = build_verdict(_comparison())
    table = format_table(verdict, color=True)
    assert "\x1b[" in table


def test_format_table_is_ascii_safe():
    """The table must be ASCII-only so it prints on a Windows cp1252 console
    (the operator's environment) without a UnicodeEncodeError."""
    verdict = build_verdict(_comparison())
    table = format_table(verdict, color=False)
    assert table.isascii(), "table contains non-ASCII chars that crash cp1252 stdout"


# ── CLI entrypoint ────────────────────────────────────────────────

def test_main_reads_fixture_and_returns_pass_exit(capsys):
    code = main([str(FIXTURE)])
    out = capsys.readouterr().out
    assert code == EXIT_PASS
    # Default output includes a JSON verdict block.
    assert '"overall"' in out
    assert "pass" in out


def test_main_hard_reject_file_returns_exit_2(tmp_path, capsys):
    comp = _comparison({"avg_realized_rr": 1.0})
    p = tmp_path / "comparison.json"
    p.write_text(json.dumps(comp), encoding="utf-8")
    code = main([str(p), "--no-color"])
    assert code == EXIT_HARD_REJECT


def test_main_json_only_emits_pure_json(tmp_path, capsys):
    comp = _comparison()
    p = tmp_path / "comparison.json"
    p.write_text(json.dumps(comp), encoding="utf-8")
    code = main([str(p), "--json-only"])
    out = capsys.readouterr().out
    assert code == EXIT_PASS
    parsed = json.loads(out)  # entire stdout must be valid JSON
    assert parsed["overall"] == "pass"
    assert parsed["exit_code"] == EXIT_PASS


def test_main_missing_file_returns_error_exit(capsys):
    code = main(["/no/such/comparison.json"])
    assert code != EXIT_PASS
