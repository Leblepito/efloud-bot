"""Aggregate the latest backtest compare run per social hypothesis.

Used by `build_social_research_snapshot` so the dashboard's Learning
Center can render PASS / WARN / REJECT verdict badges next to each
hypothesis card. Read-only; never touches engine state or live config.

A compare report is the JSON produced by ``backtest.cli compare`` at
``reports/backtests/<date>_compare_*/comparison.json``. The shape we
consume is whatever ``backtest.comparison.run_v1_v2_comparison`` emits:

    {
        "v1": {...},
        "v2": {...},
        "deltas": {<metric>: {...}},
        "gates": {<metric>: "pass" | "warn" | "hard_reject"},
        "hypothesis": str | None,
        "doctrine_tags": list[str] | None
    }

Reports with no ``hypothesis`` are ignored — they belong to a generic
backtest, not a social-learning hypothesis.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

DEFAULT_REPORTS_ROOT = Path("reports/backtests")
_COMPARE_DIR_PATTERN = re.compile(r"^(?P<date>\d{4}-\d{2}-\d{2})_compare_")


@dataclass(frozen=True)
class CompareRun:
    """One parsed compare run associated with a social hypothesis."""

    hypothesis: str
    run_dir: Path
    run_date: str  # ISO YYYY-MM-DD from the directory name
    gates: dict[str, str]
    doctrine_tags: list[str]
    deltas: dict[str, Any]


def summary_verdict(gates: dict[str, str]) -> str:
    """Collapse per-metric gate verdicts into one badge label.

    Order of precedence: ``hard_reject`` > ``warn`` > ``pass``. Anything
    we don't recognise (or an empty dict) becomes ``UNKNOWN`` so the
    badge can render as neutral instead of falsely green.
    """
    if not gates:
        return "UNKNOWN"
    values = set(gates.values())
    if "hard_reject" in values:
        return "REJECT"
    if "warn" in values:
        return "WARN"
    recognised = {"pass", "warn", "hard_reject"}
    if values - recognised:
        return "UNKNOWN"
    return "PASS"


def _iter_compare_dirs(reports_root: Path):
    if not reports_root.exists():
        return
    for entry in sorted(reports_root.iterdir()):
        if not entry.is_dir():
            continue
        if _COMPARE_DIR_PATTERN.match(entry.name):
            yield entry


def _read_comparison_report(run_dir: Path) -> dict[str, Any] | None:
    report_path = run_dir / "comparison.json"
    if not report_path.exists():
        return None
    try:
        with report_path.open("r", encoding="utf-8") as fh:
            return json.load(fh)
    except (json.JSONDecodeError, OSError):
        return None


def _run_date_from_dirname(name: str) -> str:
    match = _COMPARE_DIR_PATTERN.match(name)
    if not match:
        return ""
    return match.group("date")


def latest_runs_per_hypothesis(
    reports_root: Path | str = DEFAULT_REPORTS_ROOT,
) -> dict[str, CompareRun]:
    """Return the most recent compare run for each hypothesis_id.

    "Most recent" is decided lexicographically on the directory name,
    which begins with ``YYYY-MM-DD_compare_`` and ends with an opaque
    run-id suffix. This matches how ``backtest.cli`` writes them and
    is stable inside a single calendar day because the run-id is
    monotonic per process.
    """
    reports_root = Path(reports_root)
    latest: dict[str, CompareRun] = {}

    for run_dir in _iter_compare_dirs(reports_root):
        report = _read_comparison_report(run_dir)
        if not report:
            continue
        hypothesis = report.get("hypothesis")
        if not hypothesis or not isinstance(hypothesis, str):
            continue

        candidate = CompareRun(
            hypothesis=hypothesis,
            run_dir=run_dir,
            run_date=_run_date_from_dirname(run_dir.name),
            gates=dict(report.get("gates") or {}),
            doctrine_tags=list(report.get("doctrine_tags") or []),
            deltas=dict(report.get("deltas") or {}),
        )
        prev = latest.get(hypothesis)
        if prev is None or candidate.run_dir.name > prev.run_dir.name:
            latest[hypothesis] = candidate

    return latest


def research_runs_payload(
    reports_root: Path | str = DEFAULT_REPORTS_ROOT,
) -> dict[str, dict[str, Any]]:
    """Shape used inside the dashboard snapshot.

    Maps hypothesis id to a JSON-safe summary that the frontend reads
    directly. ``verdict`` is the badge label the SocialLearningCenter
    renders next to each hypothesis card.
    """
    out: dict[str, dict[str, Any]] = {}
    for hypothesis, run in latest_runs_per_hypothesis(reports_root).items():
        out[hypothesis] = {
            "verdict": summary_verdict(run.gates),
            "gates": run.gates,
            "doctrine_tags": run.doctrine_tags,
            "run_dir": str(run.run_dir),
            "run_date": run.run_date,
            "deltas": run.deltas,
        }
    return out
