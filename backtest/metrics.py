"""Backtest metrics aggregation."""
from __future__ import annotations

import numpy as np
import pandas as pd

# Profit factor sentinel: used when there are wins but zero losses (perfect trader).
# Plain 999.0 is JSON-serializable; float("inf") is not. Consumers should treat
# any value >= 999 as "effectively infinite — perfect record".
_PROFIT_FACTOR_INFINITY_PROXY = 999.0


def serialize_trade(p) -> dict:
    # Initial SL is what was set at open time. Position.sl can move to break-even
    # on TP1 hit; initial_sl preserves the original zone for visualization.
    initial_sl = getattr(p, "initial_sl", None) or float(p.sl)
    return {
        "symbol": p.symbol,
        "direction": p.direction,
        "entry": float(p.avg_entry_price),
        "exit": float(p.exits[-1].price) if p.exits else None,
        "pnl": float(p.realized_pnl),
        "exit_reason": p.exits[-1].reason if p.exits else None,
        "opened_at": str(p.opened_at),
        "closed_at": str(p.closed_at) if p.closed_at else None,
        # Zone fields — original SL/TP1/TP2 set at entry (not mutated post-open)
        "sl": float(initial_sl),
        "tp1": float(p.tp1),
        "tp2": float(p.tp2),
        "sl_moved_to_be": bool(getattr(p, "sl_moved_to_be", False)),
        # MAE/MFE — populated by per-bar update_excursion calls in backtest engine
        "mae_pct": float(getattr(p, "mae_pct", 0.0)),
        "mfe_pct": float(getattr(p, "mfe_pct", 0.0)),
    }


def aggregate_metrics(
    trades: list[dict],
    initial_balance: float,
    peak_balance: float,
    final_balance: float,
) -> dict:
    """Compute win_rate, profit_factor, sharpe-like, etc.

    Returns a dict with keys:
        total_trades, wins, losses, win_rate, profit_factor,
        total_return_pct, realized_giveback_pct, sharpe_like
    """
    wins = [t for t in trades if t["pnl"] > 0]
    losses = [t for t in trades if t["pnl"] < 0]
    sum_wins = sum(t["pnl"] for t in wins)
    sum_losses = abs(sum(t["pnl"] for t in losses))
    pf = sum_wins / sum_losses if sum_losses > 0 else (_PROFIT_FACTOR_INFINITY_PROXY if sum_wins > 0 else 0.0)

    pnl_pcts = [t["pnl"] / initial_balance * 100 for t in trades]
    sharpe = (
        float(np.mean(pnl_pcts)) / float(np.std(pnl_pcts))
        if len(pnl_pcts) > 2 and np.std(pnl_pcts) > 0
        else 0.0
    )

    return {
        "total_trades": len(trades),
        "wins": len(wins),
        "losses": len(losses),
        "win_rate": round(len(wins) / len(trades) * 100, 1) if trades else 0.0,
        "profit_factor": round(pf, 2),
        "total_return_pct": round((final_balance - initial_balance) / initial_balance * 100, 2) if initial_balance > 0 else 0.0,
        # realized_giveback_pct: how much of the realized peak balance was given back to final.
        # This is NOT a peak-to-trough across the trade timeline — it's just (peak - final) / peak.
        # The TRUE peak-to-trough MTM drawdown lives in the engine's `max_drawdown_pct` (set per-tick
        # during run_backtest, not here).
        "realized_giveback_pct": (
            round((peak_balance - final_balance) / peak_balance * 100, 2)
            if peak_balance > 0
            else 0.0
        ),
        "sharpe_like": round(sharpe, 2),
    }


def compute_stop_hunt_rate(
    trades: list[dict],
    data: dict,
    entry_tf: str = "15m",
    lookback_bars: int = 4,
) -> float:
    """Fraction of SL exits where price subsequently reached the original tp1.

    A stop-hunt is when an SL fires and price reaches the originally-planned
    tp1 within `lookback_bars` bars after the exit timestamp. This proxies
    the spec §8.2 metric: "SL hit, then price moves to original target within 1h"
    (1h = 4 × 15m bars at the default entry TF).

    Returns 0.0 if there are no SL exits among `trades`.

    Direction semantics:
        LONG  → stop-hunt if any high in next N bars >= tp1
        SHORT → stop-hunt if any low  in next N bars <= tp1
    """
    sl_trades = [t for t in trades if t.get("exit_reason") == "SL"]
    if not sl_trades:
        return 0.0
    hunt_count = 0
    for t in sl_trades:
        sym = t["symbol"]
        sym_data = data.get(sym)
        if sym_data is None or entry_tf not in sym_data:
            continue
        df = sym_data[entry_tf]
        closed_at = pd.Timestamp(t["closed_at"])
        after = df.loc[df.index > closed_at].iloc[:lookback_bars]
        if after.empty:
            continue
        tp1 = float(t["tp1"])
        if t["direction"] == "LONG":
            if (after["high"] >= tp1).any():
                hunt_count += 1
        else:  # SHORT
            if (after["low"] <= tp1).any():
                hunt_count += 1
    return hunt_count / len(sl_trades)
