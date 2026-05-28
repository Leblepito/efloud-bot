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
from backtest.grid import GridRunner, expand_grid, config_hash
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


def cmd_portfolio(args):
    with open(args.config, encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    tfs = [cfg["timeframes"]["htf"], cfg["timeframes"]["mtf"], cfg["timeframes"]["entry"], "1d"]
    symbols = [s.strip() for s in args.symbols.split(",") if s.strip()]
    data = _load_data_for_period(symbols, tfs, args.period_days)

    run_id = uuid.uuid4().hex[:8]
    out_dir = Path(
        f"reports/backtests/{time.strftime('%Y-%m-%d')}_"
        f"portfolio_{len(symbols)}sym_{args.period_days}d_{run_id}"
    )
    capture_provenance(out_dir)

    result = run_backtest(
        symbols=symbols, data=data, config=cfg, initial_balance=args.balance
    )
    (out_dir / "result.json").write_text(json.dumps(result, indent=2, default=str))
    print(f"OK Portfolio backtest: {out_dir}")
    print(
        f"   Symbols: {len(symbols)}  "
        f"Trades: {result.get('total_trades', 0)}  "
        f"Return: {result.get('total_return_pct', 0)}%  "
        f"DD: {result.get('max_drawdown_pct', 0)}%"
    )


def _grid_run_one(cfg_with_meta: dict) -> dict:
    """Top-level picklable function for grid worker.

    PERF NOTE: Each worker reloads the cache from parquet. For a 200-config grid
    x 10 symbols x 4 TFs = 8,000 parquet reads. With sha256 verify, each takes
    50-200ms -> 7-25 min total overhead on a ~17h grid (~2-3%). Acceptable for v1.

    Future optimization: pass `data` as a serialized blob in cfg_with_meta or use
    multiprocessing.Manager shared dict. Both add complexity; defer until measured
    overhead becomes a real bottleneck.

    Workers use verify_sha=False (the cache was already verified at fetch time).
    """
    cfg = cfg_with_meta["config"]
    symbols = cfg_with_meta["symbols"]
    period_days = cfg_with_meta["period_days"]
    balance = cfg_with_meta["balance"]
    tfs = [cfg["timeframes"]["htf"], cfg["timeframes"]["mtf"], cfg["timeframes"]["entry"], "1d"]
    data = _load_data_for_period(symbols, tfs, period_days, verify_sha=False)
    result = run_backtest(symbols=symbols, data=data, config=cfg, initial_balance=balance)
    result["config_hash"] = config_hash(cfg)
    # Flatten the grid-varied fields into top-level for ranking
    for k in cfg_with_meta.get("grid_keys", []):
        parts = k.split(".")
        cur = cfg
        for p in parts:
            cur = cur[p]
        result[k] = cur
    return result


def cmd_grid(args):
    with open(args.grid, encoding="utf-8") as f:
        grid_spec = yaml.safe_load(f)
    with open(grid_spec["base"], encoding="utf-8") as f:
        base_cfg = yaml.safe_load(f)
    overrides = grid_spec["overrides"]  # dict[dotted_key, list]

    symbols = [s.strip() for s in args.symbols.split(",") if s.strip()]
    grid_run_id = uuid.uuid4().hex[:8]
    out_dir = Path(
        f"reports/backtests/grid_{time.strftime('%Y-%m-%d')}_{grid_run_id}"
    )
    # Refuse dirty git tree for grid runs (spec ss6.8)
    capture_provenance(out_dir, allow_dirty=False)

    runner = GridRunner(out_dir)
    cfgs = [
        {
            "config": cfg,
            "symbols": symbols,
            "period_days": args.period_days,
            "balance": args.balance,
            "grid_keys": list(overrides.keys()),
        }
        for cfg in expand_grid(base_cfg, overrides)
    ]
    print(f"Grid: {len(cfgs)} configs x {len(symbols)} symbols")
    results = runner.run(cfgs, run_one_fn=_grid_run_one, workers=args.workers)

    # Rank by sharpe-like (descending); skip results with errors
    ranked = sorted(
        (r for r in results if "error" not in r),
        key=lambda r: r.get("sharpe_like", 0),
        reverse=True,
    )
    (out_dir / "ranking.json").write_text(json.dumps(ranked[:20], indent=2, default=str))
    print(f"OK Grid complete: {out_dir} (top 20 in ranking.json)")
    error_count = sum(1 for r in results if "error" in r)
    if error_count:
        print(f"   WARNING: {error_count} configs failed (see configs/ for details)")


def cmd_compare(args):
    """Run v1 vs v2 SMC backtest comparison (spec §8.2)."""
    from backtest.comparison import run_v1_v2_comparison

    # Resolve hypothesis if provided
    doctrine_tags = None
    if args.hypothesis:
        try:
            from backend.social.archive import load_doctrine_snapshots
            from backend.social.hypotheses import generate_hypotheses
            rows = load_doctrine_snapshots("state/social_doctrine.jsonl")
            doctrines = [row.get("doctrine", {}) for row in rows if row.get("doctrine")]
            hypotheses = generate_hypotheses(doctrines)
            match = next((h for h in hypotheses if h["id"] == args.hypothesis), None)
            if match:
                doctrine_tags = match.get("doctrine_tags")
        except (ImportError, ModuleNotFoundError):
            # Fallback if backend is not available in current PYTHONPATH
            pass

    with open(args.config, encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    tfs = [cfg["timeframes"]["htf"], cfg["timeframes"]["mtf"], cfg["timeframes"]["entry"], "1d"]
    symbols = [s.strip() for s in args.symbols.split(",") if s.strip()]
    data = _load_data_for_period(symbols, tfs, args.period_days)

    run_id = uuid.uuid4().hex[:8]
    out_dir = Path(
        f"reports/backtests/{time.strftime('%Y-%m-%d')}_"
        f"compare_{len(symbols)}sym_{args.period_days}d_{run_id}"
    )
    capture_provenance(out_dir)

    report = run_v1_v2_comparison(
        symbols=symbols, data=data, config=cfg, initial_balance=args.balance,
        hypothesis=args.hypothesis, doctrine_tags=doctrine_tags
    )
    (out_dir / "comparison.json").write_text(json.dumps(report, indent=2, default=str))
    print(f"OK Compare backtest: {out_dir}")
    if args.hypothesis:
        print(f"   Hypothesis: {args.hypothesis} (Tags: {doctrine_tags})")
    print(
        f"   v1 trades={report['v1']['total_trades']}  "
        f"v2 trades={report['v2']['total_trades']}"
    )
    for metric, verdict in report["gates"].items():
        marker = {"pass": "[PASS]", "warn": "[WARN]", "hard_reject": "[REJECT]"}.get(
            verdict, "[?]"
        )
        print(
            f"   {marker} {metric}: v1={report['v1'].get(metric)} "
            f"v2={report['v2'].get(metric)}"
        )


def build_parser():
    """Build the argparse parser. Extracted from main() so tests can introspect."""
    p = argparse.ArgumentParser(prog="backtest")
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("single")
    s.add_argument("--symbol", required=True)
    s.add_argument("--period-days", type=int, default=365)
    s.add_argument("--config", default="configs/config.phase2_1k.yaml")
    s.add_argument("--balance", type=float, default=2000.0)
    s.set_defaults(func=cmd_single)

    p_port = sub.add_parser("portfolio")
    p_port.add_argument("--symbols", required=True, help="comma-separated, e.g. BTC/USDT,ETH/USDT")
    p_port.add_argument("--period-days", type=int, default=365)
    p_port.add_argument("--config", default="configs/config.phase2_1k.yaml")
    p_port.add_argument("--balance", type=float, default=2000.0)
    p_port.set_defaults(func=cmd_portfolio)

    p_grid = sub.add_parser("grid")
    p_grid.add_argument("--grid", required=True, help="path to grid YAML spec")
    p_grid.add_argument("--symbols", required=True)
    p_grid.add_argument("--period-days", type=int, default=365)
    p_grid.add_argument("--balance", type=float, default=2000.0)
    p_grid.add_argument("--workers", type=int, default=4)
    p_grid.set_defaults(func=cmd_grid)

    p_cmp = sub.add_parser("compare", help="Run v1 vs v2 SMC backtest comparison")
    p_cmp.add_argument("--symbols", required=True, help="comma-separated, e.g. BTC/USDT,ETH/USDT")
    p_cmp.add_argument("--period-days", type=int, default=30)
    p_cmp.add_argument("--config", default="configs/config.phase2_1k.yaml")
    p_cmp.add_argument("--balance", type=float, default=2000.0)
    p_cmp.add_argument("--hypothesis", help="Link backtest to a social research hypothesis ID")
    p_cmp.set_defaults(func=cmd_compare)

    return p


def main():
    args = build_parser().parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
