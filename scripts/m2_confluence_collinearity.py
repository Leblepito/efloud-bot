"""M2 (2026-06-20 algorithm audit): confluence component over-counting / collinearity.

Audit finding: "OB triple-count (+10/+5 near-swing/+3 at-EQ = +18 for ONE
concept, confluence.py:32-37); OB/OTE/FVG fire together on 'pullback into
discount POI' (partial triple double-count); daily +5 echoes HTF +25.
Effective DOF ~= 3, not 8 -> conf=80 may fit the dominant in-sample pattern
rather than independent edge. Direction: single-factor NET attribution +
8-component correlation matrix."

This script computes the second half directly: it runs the REAL production
`engine.signals.generate_signals` (min_confluence=0, so every aligned trigger
is captured regardless of threshold -- this measures the RAW component
firing/co-occurrence pattern the scoring formula is built on, not a
backtest-filtered subsample) across the full locally cached OHLCV history for
10 symbols, records which of the 9 named confluence components fired on each
signal (parsed from `Signal.reasons`, the same strings `calc_confluence`
appends), and reports marginal firing rates + a phi-coefficient (Pearson
correlation for binary variables) pairwise matrix.

NET single-factor PnL attribution (does component X alone predict edge) is
NOT computed here -- that requires the full walk-forward backtest per
component-subset, which is far more compute than this sandbox's constraints
allow in one sitting (see docs/results/2026-07-08-c4-net-cost-confluence-sweep.md
for the same compute-ceiling finding on the C4 sweep). This script covers the
correlation-matrix half of M2's stated direction; results + interpretation
are written up in docs/results/2026-07-08-m2-confluence-collinearity.md.

Usage:
    python -m scripts.m2_confluence_collinearity --symbols BTC/USDT,ETH/USDT,...
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import yaml

from data.cache import OHLCVCache
from engine.signals import generate_signals
from engine.smc import SMCEngine

COMPONENTS = [
    "MTF CHoCH confirmation", "Price in HTF FVG", "Price at Order Block",
    "OB near swing (high conf)", "Price at OB EQ (refined entry)",
    "Price in OTE (0.618-0.786)", "SFP liquidity sweep",
    "Correct premium/discount zone", "Range deviation",
]
SHORT = {
    "MTF CHoCH confirmation": "MTF_CHoCH",
    "Price in HTF FVG": "HTF_FVG",
    "Price at Order Block": "OB",
    "OB near swing (high conf)": "OB_near_swing",
    "Price at OB EQ (refined entry)": "OB_at_EQ",
    "Price in OTE (0.618-0.786)": "OTE",
    "SFP liquidity sweep": "SFP",
    "Correct premium/discount zone": "correct_zone",
    "Range deviation": "deviation",
}

DEFAULT_SYMBOLS = ["BTC/USDT", "ETH/USDT", "XRP/USDT", "DOGE/USDT", "SOL/USDT",
                    "BNB/USDT", "TRX/USDT", "LINK/USDT", "BCH/USDT", "ADA/USDT"]


def collect_rows(symbols: list[str], config_path: str, cache_dir: str = "cache/ohlcv") -> list[dict]:
    with open(config_path, encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    sc, fib = cfg["structure"], cfg["fibonacci"]
    engine = SMCEngine(
        swing_lb=sc["swing_lookback"], ob_seq=sc["ob_sequential"],
        body_mode=sc["body_mode"], eq_thr=sc["eq_threshold_pct"] / 100,
        range_lb=sc["range_lookback"], ote_lo=fib["ote_lower"], ote_hi=fib["ote_upper"],
    )
    cache = OHLCVCache(cache_dir, verify_sha=False)
    rows = []
    for sym in symbols:
        df_htf, df_mtf, df_entry, df_daily = (
            cache.get(sym, "4h"), cache.get(sym, "1h"),
            cache.get(sym, "15m"), cache.get(sym, "1d"),
        )
        if df_htf is None or df_mtf is None or df_entry is None:
            print(f"SKIP {sym}: missing cache")
            continue
        sigs = generate_signals(
            engine, df_htf, df_mtf, df_entry,
            min_confluence=0, min_rr=0.0, fib_ext=fib.get("ext_tp2", 1.618),
            recency_bars=len(df_entry), df_daily=df_daily,
        )
        for s in sigs:
            row = {c: (c in s.reasons) for c in COMPONENTS}
            row["symbol"] = sym
            row["confluence"] = s.confluence
            rows.append(row)
        print(f"{sym}: {len(sigs)} signals")
    return rows


def analyze(rows: list[dict]) -> dict:
    n = len(rows)
    mat = np.array([[1 if r[c] else 0 for c in COMPONENTS] for r in rows])
    k = len(COMPONENTS)
    labels = [SHORT[c] for c in COMPONENTS]
    marginals = {labels[i]: float(mat[:, i].mean()) for i in range(k)}
    phi = np.zeros((k, k))
    for i in range(k):
        for j in range(k):
            xi, xj = mat[:, i], mat[:, j]
            phi[i, j] = 0.0 if xi.std() == 0 or xj.std() == 0 else np.corrcoef(xi, xj)[0, 1]
    flagged = [
        (labels[i], labels[j], float(phi[i, j]))
        for i in range(k) for j in range(i + 1, k) if abs(phi[i, j]) > 0.3
    ]
    return {"n": n, "labels": labels, "marginals": marginals,
            "phi": phi.tolist(), "flagged_pairs": flagged}


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--symbols", default=",".join(DEFAULT_SYMBOLS))
    ap.add_argument("--config", default="configs/config.phase2_1k.yaml")
    ap.add_argument("--out", default="")
    args = ap.parse_args()
    symbols = [s.strip() for s in args.symbols.split(",") if s.strip()]

    rows = collect_rows(symbols, args.config)
    result = analyze(rows)

    print(f"\nTotal signals: {result['n']}")
    print("\nMarginal firing rates:")
    for label, rate in result["marginals"].items():
        print(f"  {label:<15} {rate*100:5.1f}%")
    print("\nFlagged pairs (|phi| > 0.3):")
    for a, b, v in sorted(result["flagged_pairs"], key=lambda x: -abs(x[2])):
        print(f"  {a} <-> {b}: phi={v:.3f}")

    if args.out:
        Path(args.out).write_text(json.dumps(result, indent=2))
        print(f"Wrote {args.out}")


if __name__ == "__main__":
    main()
