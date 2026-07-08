"""C4 (2026-06-20 algorithm audit): NET-cost min_confluence sweep.

Runs the REAL production backtest engine (backtest.engine.run_backtest) with
REAL cached OHLCV data and a REAL cost model (commission + funding) across a
set of min_confluence thresholds, so C4 can be resolved from actual NET-cost
evidence instead of the original ad-hoc, uncommitted `c:\\tmp\\verify_s1.py`
script that produced the GROSS-only PF 1.35 (conf=50) vs PF 2.34 (conf=80)
figures quoted in configs/config.phase2_1k.yaml and the audit doc.

Usage:
    python -m scripts.c4_confluence_sweep --symbols BTC/USDT,ETH/USDT \\
        --period-days 75 --confluences 50,55,80

Notes on runtime (2026-07-08 sandbox findings):
    The engine's per-bar position-lifecycle bookkeeping (duplicate-direction
    guards, excursion tracking, breaker checks) gets materially heavier once
    real trades are open, so wall time is NOT linear in period-days once past
    a threshold. On a constrained 2-core sandbox, ~75 days x 1 symbol took
    ~9-12s per confluence value; ~90 days x 1 symbol did not finish in 43s.
    On a normal workstation/VPS this should scale to the full 300+ day,
    10-symbol sweep the audit envisioned (grid spec:
    configs/grids/confluence_x_notional.yaml) in a reasonable time — this
    script is deliberately simple (no multiprocessing) so it's easy to read;
    parallelize across symbols/confluence values for a real production run.

Requires: cache/ohlcv/ populated via `python -m scripts.prefetch_data` first.
"""
from __future__ import annotations

import argparse
import copy
import json
import time
from pathlib import Path

import pandas as pd
import yaml

from backtest.engine import run_backtest
from data.cache import OHLCVCache

# Historical validation basis (CLAUDE.md): the original PF 1.35/2.34 figures
# were measured on the 4h/1h/15m chain, before the 2026-07-06 profile-based
# timeframe redesign introduced 12h HTF for the mid profile. The locally
# cached parquet data (from an earlier prefetch) only has 15m/1h/4h/1d, so
# this sweep pins the historical chain to stay apples-to-apples with the
# figures it's meant to check, rather than silently comparing against a
# different (12h) chain the cache can't even serve.
HISTORICAL_CHAIN = {"htf": "4h", "mtf": "1h", "entry": "15m"}


def run_one(base_cfg: dict, symbols: list[str], data: dict, confluence: int,
            balance: float, commission_pct: float, funding_pct_per_8h: float) -> dict:
    cfg = copy.deepcopy(base_cfg)
    cfg["timeframes"] = dict(HISTORICAL_CHAIN)
    cfg["risk"]["min_confluence"] = confluence
    t0 = time.time()
    result = run_backtest(
        symbols=symbols, data=data, config=cfg, initial_balance=balance,
        commission_pct=commission_pct, funding_pct_per_8h=funding_pct_per_8h,
    )
    result["_wall_time_sec"] = round(time.time() - t0, 1)
    result["_min_confluence"] = confluence
    return result


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--symbols", default="BTC/USDT", help="comma-separated")
    ap.add_argument("--period-days", type=int, default=75)
    ap.add_argument("--confluences", default="50,55,80", help="comma-separated ints")
    ap.add_argument("--config", default="configs/config.phase2_1k.yaml")
    ap.add_argument("--balance", type=float, default=2000.0)
    ap.add_argument("--commission-pct", type=float, default=0.04,
                     help="Binance USD-M taker round-trip %% (NET-cost)")
    ap.add_argument("--funding-pct-per-8h", type=float, default=0.01,
                     help="average symmetric funding drag %% per 8h (NET-cost)")
    ap.add_argument("--out", default="")
    args = ap.parse_args()

    symbols = [s.strip() for s in args.symbols.split(",") if s.strip()]
    confluences = [int(c) for c in args.confluences.split(",") if c.strip()]

    with open(args.config, encoding="utf-8") as f:
        base_cfg = yaml.safe_load(f)

    tfs = list(HISTORICAL_CHAIN.values()) + ["1d"]
    cache = OHLCVCache("cache/ohlcv", verify_sha=False)
    end_ms = int(time.time() * 1000)
    start_ms = end_ms - args.period_days * 86400 * 1000
    cutoff = pd.Timestamp(start_ms, unit="ms")

    data = {}
    for s in symbols:
        data[s] = {}
        for tf in tfs:
            df = cache.get(s, tf)
            if df is None:
                raise FileNotFoundError(
                    f"No cache for {s} {tf}. Run `python -m scripts.prefetch_data` first."
                )
            data[s][tf] = df[df.index >= cutoff]

    results = {}
    for conf in confluences:
        res = run_one(base_cfg, symbols, data, conf, args.balance,
                       args.commission_pct, args.funding_pct_per_8h)
        results[conf] = res
        print(
            f"conf={conf}: trades={res.get('total_trades')} "
            f"PF={res.get('profit_factor')} WR={res.get('win_rate_pct')} "
            f"return={res.get('total_return_pct')}% maxDD={res.get('max_drawdown_pct')}% "
            f"commission={res.get('total_commission')} funding={res.get('total_funding')} "
            f"({res.get('_wall_time_sec')}s)"
        )

    if args.out:
        Path(args.out).write_text(
            json.dumps({str(k): v for k, v in results.items()}, indent=2, default=str)
        )
        print(f"Wrote {args.out}")


if __name__ == "__main__":
    main()
