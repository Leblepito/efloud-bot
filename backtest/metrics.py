"""Backtest metrics aggregation."""
from __future__ import annotations
import numpy as np


def serialize_trade(p) -> dict:
    return {
        "symbol": p.symbol,
        "direction": p.direction,
        "entry": float(p.avg_entry_price),
        "exit": float(p.exits[-1].price) if p.exits else None,
        "pnl": float(p.realized_pnl),
        "exit_reason": p.exits[-1].reason if p.exits else None,
        "opened_at": str(p.opened_at),
        "closed_at": str(p.closed_at) if p.closed_at else None,
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
        total_return_pct, realized_drawdown_pct, sharpe_like
    """
    wins = [t for t in trades if t["pnl"] > 0]
    losses = [t for t in trades if t["pnl"] < 0]
    sum_wins = sum(t["pnl"] for t in wins)
    sum_losses = abs(sum(t["pnl"] for t in losses))
    pf = sum_wins / sum_losses if sum_losses > 0 else (999.0 if sum_wins > 0 else 0.0)

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
        "total_return_pct": round(
            (final_balance - initial_balance) / initial_balance * 100, 2
        ),
        "realized_drawdown_pct": (
            round((peak_balance - final_balance) / peak_balance * 100, 2)
            if peak_balance > 0
            else 0.0
        ),
        "sharpe_like": round(sharpe, 2),
    }
