#!/usr/bin/env python3
"""Evaluate a backtest comparison.json against the HERMES.md §6 Adım 3 gates.

`python -m backtest.cli compare` writes a comparison.json with v1/v2 metrics.
This tool turns that file into a pass / warn / hard_reject verdict, prints a
colored table, emits a JSON verdict, and sets an exit code so it can gate CI /
a rollout step:

    0  → all gates pass            (HERMES: "Tümü pass → S7'ye geç")
    1  → at least one warn         (HERMES: "warn → shadow süresini uzat")
    2  → at least one hard_reject  (HERMES: "hard_reject → v2 redesign")
    3  → usage / IO error (bad path, unreadable JSON)

Thresholds are NOT re-hardcoded here — they are imported from
backtest.comparison.DEFAULT_GATES (the same table the harness itself applies),
so this tool and the harness can never drift.

Usage:
    python scripts/evaluate_backtest_gates.py path/to/comparison.json
    python scripts/evaluate_backtest_gates.py comparison.json --json-only
    python scripts/evaluate_backtest_gates.py comparison.json --no-color
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

# Allow `python scripts/evaluate_backtest_gates.py ...` (repo root not otherwise
# on sys.path when invoked as a file rather than `-m`).
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backtest.comparison import DEFAULT_GATES, _evaluate_metric

EXIT_PASS = 0
EXIT_WARN = 1
EXIT_HARD_REJECT = 2
EXIT_ERROR = 3

# Worst-first severity ordering — overall verdict = worst metric status.
_SEVERITY = {"pass": 0, "skip": 0, "warn": 1, "hard_reject": 2}
_STATUS_EXIT = {"pass": EXIT_PASS, "warn": EXIT_WARN, "hard_reject": EXIT_HARD_REJECT}

_ANSI = {
    "pass": "\x1b[32m",        # green
    "warn": "\x1b[33m",        # yellow
    "hard_reject": "\x1b[31m",  # red
    "skip": "\x1b[90m",        # grey
    "reset": "\x1b[0m",
    "bold": "\x1b[1m",
}


def _rule_text(spec: dict) -> str:
    """Human-readable threshold description for one gate spec."""
    # ASCII-only on purpose — this prints to a Windows cp1252 console.
    if "v2_min_abs" in spec:
        return f"v2 >= {spec['v2_min_abs']} abs (reject < {spec['hard_reject_abs']})"
    if "v2_min_vs_v1" in spec:
        return f"v2 >= {spec['v2_min_vs_v1']}x v1 (reject < {spec['hard_reject_vs_v1']}x v1)"
    if "v2_max_vs_v1" in spec:
        return f"v2 <= {spec['v2_max_vs_v1']}x v1 (reject > {spec['hard_reject_vs_v1']}x v1)"
    return ""


def build_verdict(comparison: dict, gate_table: dict | None = None) -> dict[str, Any]:
    """Evaluate every gate against the comparison's v1/v2 metrics.

    A metric absent from BOTH v1 and v2 is reported as "skip" (and listed in
    `missing`) rather than coerced to 0.0 — coercion would spuriously
    hard_reject absolute-floor gates like avg_realized_rr. If the comparison
    already carries a harness-computed `gates[metric]` for a missing metric,
    that status is used as a fallback.
    """
    gate_table = gate_table or DEFAULT_GATES
    v1 = comparison.get("v1", {}) or {}
    v2 = comparison.get("v2", {}) or {}
    embedded = comparison.get("gates", {}) or {}

    metrics: dict[str, dict] = {}
    missing: list[str] = []
    worst = "pass"

    for metric, spec in gate_table.items():
        has_v1 = isinstance(v1.get(metric), (int, float)) and not isinstance(v1.get(metric), bool)
        has_v2 = isinstance(v2.get(metric), (int, float)) and not isinstance(v2.get(metric), bool)
        if has_v1 and has_v2:
            status = _evaluate_metric(float(v1[metric]), float(v2[metric]), spec)
        elif metric in embedded:
            status = embedded[metric]
        else:
            status = "skip"
            missing.append(metric)
        metrics[metric] = {
            "v1": v1.get(metric),
            "v2": v2.get(metric),
            "status": status,
            "rule": _rule_text(spec),
        }
        if _SEVERITY.get(status, 0) > _SEVERITY.get(worst, 0):
            worst = status

    return {
        "overall": worst,
        "exit_code": _STATUS_EXIT.get(worst, EXIT_PASS),
        "metrics": metrics,
        "missing": missing,
        "hypothesis": comparison.get("hypothesis"),
        "doctrine_tags": comparison.get("doctrine_tags"),
    }


def _fmt_num(x: Any) -> str:
    if isinstance(x, (int, float)) and not isinstance(x, bool):
        return f"{x:.4g}"
    return "—"


def format_table(verdict: dict, color: bool = True) -> str:
    """Render the verdict as an aligned table. ANSI colors when color=True."""
    def c(text: str, key: str) -> str:
        if not color:
            return text
        return f"{_ANSI.get(key, '')}{text}{_ANSI['reset']}"

    rows = []
    header = f"{'METRIC':<18} {'V1':>10} {'V2':>10} {'STATUS':<12} RULE"
    rows.append(c(header, "bold") if color else header)
    rows.append("-" * len(header))
    for metric, m in verdict["metrics"].items():
        status = m["status"]
        status_cell = f"{status:<12}"
        rows.append(
            f"{metric:<18} {_fmt_num(m['v1']):>10} {_fmt_num(m['v2']):>10} "
            f"{c(status_cell, status)} {m['rule']}"
        )
    rows.append("-" * len(header))
    overall = verdict["overall"]
    rows.append(f"OVERALL: {c(overall.upper(), overall)}  (exit {verdict['exit_code']})")
    if verdict.get("missing"):
        rows.append(c(f"skipped (metric absent): {', '.join(verdict['missing'])}", "skip"))
    return "\n".join(rows)


def _use_color(flag_no_color: bool) -> bool:
    if flag_no_color or os.environ.get("NO_COLOR"):
        return False
    return sys.stdout.isatty()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Evaluate a backtest comparison.json against the HERMES gate targets.",
    )
    parser.add_argument("comparison_json", help="Path to comparison.json")
    parser.add_argument("--json-only", action="store_true",
                        help="Emit only the JSON verdict (no table).")
    parser.add_argument("--no-color", action="store_true", help="Disable ANSI colors.")
    args = parser.parse_args(argv)

    try:
        with open(args.comparison_json, encoding="utf-8") as f:
            comparison = json.load(f)
    except (OSError, json.JSONDecodeError) as e:
        print(f"error: cannot read {args.comparison_json}: {e}", file=sys.stderr)
        return EXIT_ERROR

    verdict = build_verdict(comparison)

    if args.json_only:
        print(json.dumps(verdict, indent=2))
        return verdict["exit_code"]

    print(format_table(verdict, color=_use_color(args.no_color)))
    print()
    print(json.dumps(verdict, indent=2))
    return verdict["exit_code"]


if __name__ == "__main__":
    sys.exit(main())
