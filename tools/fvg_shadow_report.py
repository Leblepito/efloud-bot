"""Summarise `[fvg shadow]` log lines (T-20261114-01).

Usage on the VPS:
    docker logs --since 168h efloud-bot 2>&1 | python tools/fvg_shadow_report.py
    python tools/fvg_shadow_report.py bot.log

Go-live bar (spec 2026-11-14-fvg-entry-shadow-design.md): >= 30 closed shadow
trades, net avg R > 0 and above the live v2 trades over the same dates.
"""
from __future__ import annotations

import re
import sys
from collections import Counter, defaultdict
from typing import Dict, Iterable, List

_RE = re.compile(r"\[fvg shadow\] (?P<event>\S+) (?P<sym>\S+) (?P<dir>LONG|SHORT)(?P<rest>.*)$")
_RE_R = re.compile(r"reason=(?P<reason>\S+) gross_r=(?P<g>[-+]?\d+\.\d+) net_r=(?P<n>[-+]?\d+\.\d+)")
MIN_TRADES = 30


def summarize(lines: Iterable[str]) -> Dict[str, dict]:
    """Per symbol and "TOTAL": event counts, exit reasons and R lists."""
    out: Dict[str, dict] = defaultdict(lambda: {"events": Counter(), "reasons": Counter(),
                                                "gross": [], "net": []})
    for ln in lines:
        m = _RE.search(ln)
        if not m:
            continue
        for key in (m["sym"], "TOTAL"):
            s = out[key]
            s["events"][m["event"]] += 1
            if m["event"] == "exit":
                r = _RE_R.search(m["rest"])
                if r:
                    s["reasons"][r["reason"]] += 1
                    s["gross"].append(float(r["g"]))
                    s["net"].append(float(r["n"]))
    return dict(out)


def _avg(xs: List[float]) -> float:
    return sum(xs) / len(xs) if xs else 0.0


def render(summary: Dict[str, dict]) -> str:
    rows = ["symbol        setups fills closed  win%   avgR_gross avgR_net  exits"]
    for sym in sorted(summary, key=lambda k: (k == "TOTAL", k)):
        s = summary[sym]
        n = len(s["net"])
        win = 100.0 * sum(1 for x in s["net"] if x > 0) / n if n else 0.0
        reasons = " ".join(f"{k}:{v}" for k, v in sorted(s["reasons"].items()))
        rows.append(f"{sym:<13} {s['events']['setup+']:>6} {s['events']['filled']:>5} {n:>6} "
                    f"{win:>5.1f} {_avg(s['gross']):>+11.2f} {_avg(s['net']):>+8.2f}  {reasons}")
    total = summary.get("TOTAL")
    n = len(total["net"]) if total else 0
    net = _avg(total["net"]) if total else 0.0
    verdict = ("PASS" if n >= MIN_TRADES and net > 0 else
               f"WAIT (n={n}/{MIN_TRADES})" if n < MIN_TRADES else "FAIL (net avg R <= 0)")
    rows.append(f"go-live bar (vs live v2 still to compare by hand): {verdict}")
    return "\n".join(rows)


def main(argv: List[str]) -> int:
    if len(argv) > 1:
        with open(argv[1], encoding="utf-8", errors="replace") as fh:
            print(render(summarize(fh)))
    else:
        print(render(summarize(sys.stdin)))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
