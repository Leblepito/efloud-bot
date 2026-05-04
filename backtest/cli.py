"""Backtest CLI — argparse with single | portfolio | grid subcommands."""
from __future__ import annotations

import argparse
import json
import time
import uuid
from pathlib import Path

import pandas as pd
import yaml

from backtest.engine import run_backtest
from backtest.reproducibility import capture_provenance
from data.cache import OHLCVCache


def _load_data_for_period(symbols, timeframes, period_days, cache_dir="cache/ohlcv", verify_sha=True):
    """Load OHLCV data from cache for a period.

    verify_sha=True (default) -> sha256 check on every read (~50-200ms/file).
    verify_sha=False (grid worker mode) -> trust the cache, skip checksum.
    """
    cache = OHLCVCache(cache_dir, verify_sha=verify_sha)
    end_ms = int(time.time() * 1000)
    start_ms = end_ms - period_days * 86400 * 1000
    data = {}
    for s in symbols:
        data[s] = {}
        for tf in timeframes:
            df = cache.get(s, tf)
            if df is None:
                raise FileNotFoundError(
                    f"No cache for {s} {tf}. Run `python -m scripts.prefetch_data` first."
                )
            # Slice to period
            cutoff = pd.Timestamp(start_ms, unit="ms")
            data[s][tf] = df[df.index >= cutoff]
    return data


def cmd_single(args):
    with open(args.config, encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    tfs = [cfg["timeframes"]["htf"], cfg["timeframes"]["mtf"], cfg["timeframes"]["entry"], "1d"]
    data = _load_data_for_period([args.symbol], tfs, args.period_days)

    run_id = uuid.uuid4().hex[:8]
    out_dir = Path(
        f"reports/backtests/{time.strftime('%Y-%m-%d')}_"
        f"{args.symbol.replace('/', '_')}_{args.period_days}d_{run_id}"
    )
    capture_provenance(out_dir)

    result = run_backtest(
        symbols=[args.symbol], data=data, config=cfg, initial_balance=args.balance
    )
    (out_dir / "result.json").write_text(json.dumps(result, indent=2, default=str))
    print(f"OK Single backtest complete: {out_dir}")
    print(
        f"   Trades: {result.get('total_trades', 0)}  "
        f"PF: {result.get('profit_factor', 0)}  "
        f"Return: {result.get('total_return_pct', 0)}%"
    )


def main():
    p = argparse.ArgumentParser(prog="backtest")
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("single")
    s.add_argument("--symbol", required=True)
    s.add_argument("--period-days", type=int, default=365)
    s.add_argument("--config", default="configs/config.phase2_1k.yaml")
    s.add_argument("--balance", type=float, default=2000.0)
    s.set_defaults(func=cmd_single)

    args = p.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
