#!/usr/bin/env python3
"""Edge of the AgentTeam's verdicts, measured on closed trades in the trade journal.

The team runs in OBSERVATION mode (configs: agent_team.gating false). Each opened
trade's async review is written to its journal row as `agent_review.team_verdict`
(ACCEPT / REJECT / NEUTRAL / ERROR). This report groups closed trades by verdict and
shows what skipping the REJECT trades would have changed — evidence for the operator
before the team is ever given a gating role. Read-only.

    python scripts/desk/agent_verdict_edge.py --journal /app/state_1k/trade_journal.jsonl
    python scripts/desk/agent_verdict_edge.py --journal state_1k/trade_journal.jsonl --since 2026-11-04 --json
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

SMALL_SAMPLE = 30


def load(path, with_errors: bool = False):
    """Journal rows, last row per trade_id wins; malformed lines are counted, not fatal."""
    by_id: dict = {}
    bad = 0
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            r = json.loads(line)
        except ValueError:
            bad += 1
            continue
        if isinstance(r, dict) and r.get("trade_id"):
            by_id[r["trade_id"]] = r
        else:
            bad += 1
    trades = list(by_id.values())
    return (trades, bad) if with_errors else trades


def _ts(value):
    """ISO-8601 → aware datetime; a value without an offset (e.g. '2026-11-04') is UTC."""
    try:
        t = datetime.fromisoformat(str(value))
    except ValueError:
        return None
    return t if t.tzinfo else t.replace(tzinfo=UTC)


def _stats(rows) -> dict:
    pnl = [float(r.get("realized_pnl") or 0.0) for r in rows]
    pct = [float(r.get("realized_pnl_pct") or 0.0) for r in rows]
    n = len(rows)
    wins = sum(1 for x in pnl if x > 0)
    return {
        "n": n, "wins": wins, "win_rate": wins / n if n else 0.0,
        "total_pnl": round(sum(pnl), 8), "avg_pnl": round(sum(pnl) / n, 8) if n else 0.0,
        "avg_pnl_pct": round(sum(pct) / n, 6) if n else 0.0,
        "small_sample": n < SMALL_SAMPLE,
        "pnl_sources": sorted({str(r.get("pnl_source", "unknown")) for r in rows}),
    }


def report(trades, since=None) -> dict:
    cutoff = _ts(since) if since else None
    closed, open_skipped = [], 0
    for r in trades:
        if cutoff is not None:
            t = _ts(r.get("entry_timestamp"))
            if t is None or t < cutoff:
                continue
        if r.get("exit_timestamp"):
            closed.append(r)
        else:
            open_skipped += 1
    groups: dict = {}
    for r in closed:
        verdict = ((r.get("agent_review") or {}).get("team_verdict")) or "NO_REVIEW"
        groups.setdefault(verdict, []).append(r)
    total = round(sum(float(r.get("realized_pnl") or 0.0) for r in closed), 8)
    kept = [r for r in closed if ((r.get("agent_review") or {}).get("team_verdict")) != "REJECT"]
    kept_total = round(sum(float(r.get("realized_pnl") or 0.0) for r in kept), 8)
    return {
        "since": since, "closed": len(closed), "open_skipped": open_skipped, "total_pnl": total,
        "groups": {k: _stats(v) for k, v in sorted(groups.items())},
        "what_if_skip_reject": {"n": len(kept), "total_pnl": kept_total,
                                "delta": round(kept_total - total, 8)},
    }


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="AgentTeam verdict edge from the trade journal.")
    ap.add_argument("--journal", default="state_1k/trade_journal.jsonl")
    ap.add_argument("--since", help="ISO date/time; filters on entry_timestamp (UTC)")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)
    if not Path(a.journal).is_file():
        print(f"refused: journal not found: {a.journal}", file=sys.stderr)
        return 2
    trades, bad = load(a.journal, with_errors=True)
    rep = report(trades, since=a.since)
    rep["malformed_lines"] = bad
    if a.json:
        print(json.dumps(rep, indent=2))
        return 0
    print(f"AgentTeam verdict edge (observation mode, gating off) | journal {a.journal} | "
          f"since {a.since or 'start'} | closed {rep['closed']} | open skipped {rep['open_skipped']} "
          f"| malformed {bad}")
    print(f"{'verdict':<10} {'n':>4} {'win%':>6} {'total PnL':>12} {'avg PnL':>10} {'avg %':>8}")
    for verdict, s in rep["groups"].items():
        flag = "  (small sample)" if s["small_sample"] else ""
        print(f"{verdict:<10} {s['n']:>4} {100 * s['win_rate']:>5.1f}% {s['total_pnl']:>12.4f} "
              f"{s['avg_pnl']:>10.4f} {s['avg_pnl_pct']:>7.3f}%{flag}")
    w = rep["what_if_skip_reject"]
    print(f"total PnL {rep['total_pnl']:.4f} | if REJECT trades had been skipped: {w['total_pnl']:.4f} "
          f"(delta {w['delta']:+.4f}, n={w['n']}). Hypothesis evidence only — not a gating decision.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
