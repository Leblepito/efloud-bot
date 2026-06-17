"""Wave-2 falsification test — does the LIVE engine carry tradeable OOS edge?

Per the 2026-06-17 Wave-2 NO-GO review (docs/handoff/2026-06-17-claude-wave2-review-nogo.md §4.1):
before committing to a Pine premium-strategy redesign, validate the *real* edge in
the Python engine (no RE10045 there). If the full live engine logic cannot produce
OOS PF >= 1.30 AND net-positive on >= 4/5 symbols, the Pine redesign is DROPPED.

Method (fixed-parameter walk-forward):
  - Run each symbol on the FULL cached year (continuous → full HTF context, no
    warmup truncation at the split boundary).
  - Partition the resulting trades by entry time into IS (before SPLIT) / OOS (>= SPLIT).
  - Compute PF / net / win-rate per partition per symbol + pooled aggregate.
  - Symbols run in parallel processes (wall-time ≈ one symbol).

Config: configs/config.phase2_1k.yaml (prod-active: conf=50, min_rr=1.8, smc_version=v2).
  smc_v2_shadow is forced FALSE so v2 actually executes in the sim (prod logs-only).
Costs: 0.04% Binance USD-M taker commission (realistic net PF). Funding left 0 (noted).

Usage:
  python -m scripts.wave2_falsification               # full: 5 sym, full year, step=4
  python -m scripts.wave2_falsification --smoke        # 1 sym (BTC), last 60d, fast
"""
from __future__ import annotations

import argparse
import json
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

import pandas as pd
import yaml

from backtest.engine import run_backtest

CACHE = "cache/ohlcv"
CONFIG_PATH = "configs/config.phase2_1k.yaml"
CORE_SYMBOLS = ["BTC/USDT", "ETH/USDT", "SOL/USDT", "BNB/USDT", "XRP/USDT"]
SPLIT = pd.Timestamp("2025-11-15")  # ~6mo IS (May–Nov 2025) / ~6mo OOS (Nov 2025–May 2026)
COMMISSION_PCT = 0.04               # Binance USD-M taker, round-trip netted per trade
INITIAL_BALANCE = 2000.0
TFS = ["4h", "1h", "15m", "1d"]


def _load(sym: str) -> dict:
    b = sym.replace("/", "_")
    return {tf: pd.read_parquet(f"{CACHE}/{b}/{tf}.parquet") for tf in TFS}


def _pf(trades: list) -> float:
    w = sum(t["pnl"] for t in trades if t["pnl"] > 0)
    l = abs(sum(t["pnl"] for t in trades if t["pnl"] < 0))
    if l > 0:
        return round(w / l, 3)
    return float("inf") if w > 0 else 0.0


def _wr(trades: list) -> float:
    if not trades:
        return 0.0
    wins = sum(1 for t in trades if t["pnl"] > 0)
    return round(wins / len(trades) * 100, 1)


def _part_stats(trades: list) -> dict:
    gross_win = sum(t["pnl"] for t in trades if t["pnl"] > 0)
    gross_loss = abs(sum(t["pnl"] for t in trades if t["pnl"] < 0))
    return {
        "n": len(trades),
        "pf": _pf(trades),
        "win_rate": _wr(trades),
        "net": round(sum(t["pnl"] for t in trades), 2),
        "gross_win": round(gross_win, 2),
        "gross_loss": round(gross_loss, 2),
    }


def run_one(sym: str, period_days: int | None, step: int) -> dict:
    """Worker: run one symbol, return per-partition trade stats. Picklable (module-level)."""
    cfg = yaml.safe_load(open(CONFIG_PATH, encoding="utf-8"))
    # Force v2 to EXECUTE in the sim (prod runs v2 shadow-only / v1-executed).
    cfg.setdefault("engine", {})["smc_v2_shadow"] = False
    smc_version = cfg.get("engine", {}).get("smc_version", "v1")

    data = {sym: _load(sym)}
    if period_days is not None:
        end = data[sym]["15m"].index.max()
        cutoff = end - pd.Timedelta(days=period_days)
        data[sym] = {tf: df[df.index >= cutoff] for tf, df in data[sym].items()}

    t0 = time.time()
    res = run_backtest(
        symbols=[sym], data=data, config=cfg, initial_balance=INITIAL_BALANCE,
        step_every_n_bars=step, smc_version=smc_version, commission_pct=COMMISSION_PCT,
    )
    trades = res["trades"]
    # Partition by SIMULATED entry time (sim_opened_at). NOTE: opened_at is the live
    # engine's wall-clock datetime.utcnow() and must NOT be used here — it would put
    # every trade in OOS. sim_opened_at is stamped by run_backtest from sim_open_ts.
    for t in trades:
        st = t.get("sim_opened_at")
        t["_ts"] = pd.Timestamp(st) if st else pd.NaT
        if t["_ts"] is not pd.NaT and t["_ts"].tzinfo is not None:
            t["_ts"] = t["_ts"].tz_localize(None)
    is_tr = [t for t in trades if t["_ts"] is not pd.NaT and t["_ts"] < SPLIT]
    oos_tr = [t for t in trades if t["_ts"] is not pd.NaT and t["_ts"] >= SPLIT]
    return {
        "symbol": sym,
        "smc_version": smc_version,
        "elapsed_s": round(time.time() - t0, 1),
        "skipped_cycles": res.get("skipped_cycles", 0),
        "total_trades": len(trades),
        "max_drawdown_pct": res.get("max_drawdown_pct"),
        "full_pf": res.get("profit_factor"),
        "full_return_pct": res.get("total_return_pct"),
        "is": _part_stats(is_tr),
        "oos": _part_stats(oos_tr),
        "data_start": str(data[sym]["15m"].index.min()),
        "data_end": str(data[sym]["15m"].index.max()),
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--smoke", action="store_true", help="1 symbol (BTC), last 60d, step=4")
    ap.add_argument("--symbols", default=None, help="comma-separated override")
    ap.add_argument("--step", type=int, default=4)
    ap.add_argument("--workers", type=int, default=5)
    ap.add_argument("--out", default=None)
    args = ap.parse_args()

    if args.smoke:
        symbols, period_days, workers = ["BTC/USDT"], 60, 1
    else:
        symbols = (args.symbols.split(",") if args.symbols else CORE_SYMBOLS)
        period_days, workers = None, args.workers

    print(f"[wave2-falsification] symbols={symbols} period={'full-year' if period_days is None else f'{period_days}d'} "
          f"step={args.step} split={SPLIT.date()} commission={COMMISSION_PCT}% workers={workers}", flush=True)

    t0 = time.time()
    results = []
    if workers == 1:
        for s in symbols:
            r = run_one(s, period_days, args.step)
            results.append(r)
            print(f"  done {s}: total={r['total_trades']} OOS(n={r['oos']['n']} pf={r['oos']['pf']} "
                  f"net={r['oos']['net']}) elapsed={r['elapsed_s']}s", flush=True)
    else:
        with ProcessPoolExecutor(max_workers=workers) as ex:
            futs = {ex.submit(run_one, s, period_days, args.step): s for s in symbols}
            for fut in as_completed(futs):
                r = fut.result()
                results.append(r)
                print(f"  done {r['symbol']}: total={r['total_trades']} OOS(n={r['oos']['n']} "
                      f"pf={r['oos']['pf']} net={r['oos']['net']}) elapsed={r['elapsed_s']}s", flush=True)

    results.sort(key=lambda r: symbols.index(r["symbol"]))

    # Pooled aggregate OOS across all symbols (pool gross win/loss → exact PF).
    oos_pos_symbols = sum(1 for r in results if r["oos"]["net"] > 0)
    oos_total_n = sum(r["oos"]["n"] for r in results)
    oos_total_net = round(sum(r["oos"]["net"] for r in results), 2)
    pool_win = sum(r["oos"]["gross_win"] for r in results)
    pool_loss = sum(r["oos"]["gross_loss"] for r in results)
    oos_pooled_pf = round(pool_win / pool_loss, 3) if pool_loss > 0 else (
        float("inf") if pool_win > 0 else 0.0)

    gate_pf_ok = isinstance(oos_pooled_pf, float) and oos_pooled_pf >= 1.30
    gate_sym_ok = oos_pos_symbols >= 4
    gate_pass = bool(gate_pf_ok and gate_sym_ok)

    summary = {
        "split": str(SPLIT.date()),
        "commission_pct": COMMISSION_PCT,
        "step": args.step,
        "symbols": symbols,
        "per_symbol": results,
        "oos_aggregate": {
            "pooled_pf": oos_pooled_pf,
            "symbols_net_positive": oos_pos_symbols,
            "symbols_total": len(symbols),
            "oos_total_trades": oos_total_n,
            "oos_total_net": oos_total_net,
        },
        "falsification_gate": {
            "criterion": "OOS pooled PF >= 1.30 AND >= 4/5 symbols net-positive",
            "oos_pooled_pf": oos_pooled_pf,
            "pf_gate": "PASS" if gate_pf_ok else "FAIL",
            "symbols_net_positive": f"{oos_pos_symbols}/{len(symbols)}",
            "symbol_gate": "PASS" if gate_sym_ok else "FAIL",
            "verdict": "PASS — engine carries OOS edge, Wave-2 may be reconsidered"
                       if gate_pass else
                       "FAIL — engine edge insufficient, DROP Pine redesign",
        },
        "wall_time_s": round(time.time() - t0, 1),
    }

    out = args.out or f"reports/wave2_falsification_{'smoke' if args.smoke else 'full'}.json"
    Path(out).parent.mkdir(parents=True, exist_ok=True)
    Path(out).write_text(json.dumps(summary, indent=2, default=str))

    print("\n=== OOS RESULTS (per symbol) ===", flush=True)
    print(f"{'SYM':<10}{'OOS_n':>7}{'OOS_PF':>9}{'OOS_WR':>8}{'OOS_net$':>10}{'IS_PF':>8}{'IS_n':>7}", flush=True)
    for r in results:
        print(f"{r['symbol']:<10}{r['oos']['n']:>7}{r['oos']['pf']:>9}{r['oos']['win_rate']:>7}%"
              f"{r['oos']['net']:>10}{r['is']['pf']:>8}{r['is']['n']:>7}", flush=True)
    print(f"\nOOS pooled PF: {oos_pooled_pf}  | symbols net-positive: {oos_pos_symbols}/{len(symbols)}  | "
          f"OOS trades: {oos_total_n}  | OOS net: ${oos_total_net}", flush=True)
    print(f"GATE (PF>=1.30 AND >=4/5 net+): {'PASS' if gate_pass else 'FAIL'}  "
          f"[pf_gate={'PASS' if gate_pf_ok else 'FAIL'}, sym_gate={'PASS' if gate_sym_ok else 'FAIL'}]", flush=True)
    print(f"Wrote {out}", flush=True)


if __name__ == "__main__":
    main()
