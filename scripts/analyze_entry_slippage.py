#!/usr/bin/env python3
"""Entry-slippage / latency analyzer (read-only Phase-0 measurement).

Reads the trade journal (``trade_journal.jsonl``) and reports the gap between the
SMC *signal* entry price and the *actual* exchange fill, per symbol and overall.
This is the measurement tool for the entry-zone-vs-fill slippage initiative: it
turns the telemetry fields added to ``TradeSnapshot`` (``signal_entry_price``,
``actual_fill_price``, ``zone_mid``, ``latency_ms``) into an actionable baseline.

Slippage convention (matches engine/journal recording):
    LONG  slippage_pct = (fill - signal) / signal * 100
    SHORT slippage_pct = (signal - fill) / signal * 100
    A POSITIVE value is ADVERSE (we paid worse than the signal price).

This script is strictly read-only: it never touches the exchange, DB, or live
state. Use it to collect a baseline BEFORE and AFTER any entry-timing change
(async review, require_confirmation flip) to verify the gap actually shrank.

Usage:
    python scripts/analyze_entry_slippage.py
    python scripts/analyze_entry_slippage.py --journal state/trade_journal.jsonl \
        --since 2026-06-01T00:00:00Z --symbols BTC/USDT,ETH/USDT \
        --summary out.md --csv out.csv --json out.json
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import sys
from pathlib import Path
from statistics import mean, median
from typing import Any, Dict, List, Optional

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


# ── pure helpers (unit-tested) ────────────────────────────────────────────────

def _percentile(vals: List[float], p: float) -> Optional[float]:
    """Linear-interpolated percentile (p in [0,1]). None for empty input."""
    if not vals:
        return None
    s = sorted(vals)
    if len(s) == 1:
        return s[0]
    k = (len(s) - 1) * p
    f = int(math.floor(k))
    c = int(math.ceil(k))
    if f == c:
        return s[f]
    return s[f] * (c - k) + s[c] * (k - f)


def _f(t: Dict[str, Any], key: str) -> float:
    try:
        return float(t.get(key) or 0.0)
    except (TypeError, ValueError):
        return 0.0


def _has_telemetry(t: Dict[str, Any]) -> bool:
    return _f(t, "signal_entry_price") > 0.0 and _f(t, "actual_fill_price") > 0.0


def _signed_slip_pct(t: Dict[str, Any]) -> float:
    """Direction-signed slippage; recomputed from prices (does not trust the
    stored field, so the analyzer stays correct even if journal-side math drifts).
    """
    sig = _f(t, "signal_entry_price")
    fill = _f(t, "actual_fill_price")
    if sig <= 0:
        return 0.0
    if str(t.get("direction", "")).upper() == "LONG":
        return (fill - sig) / sig * 100.0
    return (sig - fill) / sig * 100.0


def _zone_gap_pct(t: Dict[str, Any]) -> Optional[float]:
    zm = _f(t, "zone_mid")
    fill = _f(t, "actual_fill_price")
    if zm > 0 and fill > 0:
        return abs(fill - zm) / zm * 100.0
    return None


def _stats(group: List[Dict[str, Any]]) -> Dict[str, Any]:
    n = len(group)
    signed = [_signed_slip_pct(t) for t in group]
    abs_slip = [abs(x) for x in signed]
    lat = [_f(t, "latency_ms") for t in group if _f(t, "latency_ms") > 0.0]
    zone_gap = [g for g in (_zone_gap_pct(t) for t in group) if g is not None]
    adverse = [x for x in signed if x > 0.0]
    return {
        "n": n,
        "mean_slippage_pct": round(mean(signed), 4) if signed else 0.0,
        "median_abs_slippage_pct": round(median(abs_slip), 4) if abs_slip else 0.0,
        "p90_abs_slippage_pct": round(_percentile(abs_slip, 0.90), 4) if abs_slip else 0.0,
        "max_abs_slippage_pct": round(max(abs_slip), 4) if abs_slip else 0.0,
        "adverse_rate": round(len(adverse) / n, 4) if n else 0.0,
        "mean_latency_ms": round(mean(lat), 1) if lat else None,
        "mean_zone_gap_pct": round(mean(zone_gap), 4) if zone_gap else None,
    }


def compute_slippage_stats(trades: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Aggregate slippage/latency stats overall and per-symbol.

    Only trades carrying telemetry (signal_entry_price>0 and actual_fill_price>0)
    contribute to the stats; ``n_total`` vs ``n_with_telemetry`` exposes coverage.
    """
    tele = [t for t in trades if _has_telemetry(t)]
    by_symbol: Dict[str, List[Dict[str, Any]]] = {}
    for t in tele:
        by_symbol.setdefault(str(t.get("symbol", "?")), []).append(t)
    return {
        "n_total": len(trades),
        "n_with_telemetry": len(tele),
        "overall": _stats(tele),
        "by_symbol": {s: _stats(g) for s, g in sorted(by_symbol.items())},
    }


# ── IO / CLI ──────────────────────────────────────────────────────────────────

def load_journal(path: Path, since: Optional[str], symbols: Optional[List[str]]) -> List[Dict[str, Any]]:
    if not path.exists():
        raise SystemExit(f"journal not found: {path}")
    rows: List[Dict[str, Any]] = []
    sym_set = set(symbols) if symbols else None
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            if sym_set is not None and row.get("symbol") not in sym_set:
                continue
            if since is not None:
                ets = str(row.get("entry_timestamp") or "")
                if ets and ets < since:
                    continue
            rows.append(row)
    return rows


def _fmt(v: Optional[float]) -> str:
    return "n/a" if v is None else f"{v:.4f}"


def render_markdown(stats: Dict[str, Any]) -> str:
    o = stats["overall"]
    lines = [
        "# Entry slippage report",
        "",
        f"- trades scanned: **{stats['n_total']}**  |  with telemetry: **{stats['n_with_telemetry']}**",
        f"- overall mean slippage: **{_fmt(o['mean_slippage_pct'])}%** (+ = adverse)",
        f"- median |slippage|: **{_fmt(o['median_abs_slippage_pct'])}%**  |  p90: **{_fmt(o['p90_abs_slippage_pct'])}%**  |  max: **{_fmt(o['max_abs_slippage_pct'])}%**",
        f"- adverse rate: **{_fmt(o['adverse_rate'])}**  |  mean latency: **{_fmt(o['mean_latency_ms'])} ms**  |  mean zone-gap: **{_fmt(o['mean_zone_gap_pct'])}%**",
        "",
        "| symbol | n | mean slip% | median |slip|% | p90 |slip|% | adverse | latency ms | zone-gap% |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for sym, s in stats["by_symbol"].items():
        lines.append(
            f"| {sym} | {s['n']} | {_fmt(s['mean_slippage_pct'])} | "
            f"{_fmt(s['median_abs_slippage_pct'])} | {_fmt(s['p90_abs_slippage_pct'])} | "
            f"{_fmt(s['adverse_rate'])} | {_fmt(s['mean_latency_ms'])} | {_fmt(s['mean_zone_gap_pct'])} |"
        )
    return "\n".join(lines) + "\n"


def write_csv(stats: Dict[str, Any], path: Path) -> None:
    cols = ["symbol", "n", "mean_slippage_pct", "median_abs_slippage_pct",
            "p90_abs_slippage_pct", "max_abs_slippage_pct", "adverse_rate",
            "mean_latency_ms", "mean_zone_gap_pct"]
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(cols)
        for sym, s in [("__overall__", stats["overall"]), *stats["by_symbol"].items()]:
            w.writerow([sym] + [s.get(c) for c in cols[1:]])


def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Read-only entry-slippage/latency analyzer for trade_journal.jsonl")
    p.add_argument("--journal", default="state/trade_journal.jsonl", help="Trade journal JSONL path")
    p.add_argument("--since", default=None, help="UTC lower bound on entry_timestamp, e.g. 2026-06-01T00:00:00Z")
    p.add_argument("--symbols", default=None, help="Comma-separated symbol filter, e.g. BTC/USDT,ETH/USDT")
    p.add_argument("--summary", default=None, help="Write markdown summary to this path")
    p.add_argument("--csv", default=None, help="Write per-symbol CSV to this path")
    p.add_argument("--json", default=None, help="Write machine-readable JSON to this path")
    return p.parse_args(argv)


def main(argv: Optional[List[str]] = None) -> int:
    args = parse_args(argv)
    symbols = [s.strip() for s in args.symbols.split(",")] if args.symbols else None
    rows = load_journal(Path(args.journal), args.since, symbols)
    stats = compute_slippage_stats(rows)

    md = render_markdown(stats)
    if args.summary:
        Path(args.summary).write_text(md, encoding="utf-8")
    if args.csv:
        write_csv(stats, Path(args.csv))
    if args.json:
        Path(args.json).write_text(json.dumps(stats, indent=2), encoding="utf-8")
    # Always echo the summary to stdout so it is usable without output files.
    print(md)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
