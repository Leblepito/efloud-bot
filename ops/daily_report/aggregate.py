"""Daily report aggregation — compute_summary() pure function.

Takes raw DB rows (trades + equity_history) and returns a dict with computed
fields suitable for rendering. No I/O, no DB calls — caller fetches rows first.
"""
from __future__ import annotations

from typing import Any, Optional


def compute_summary(
    trades: list[dict],
    equity_history: list[dict],
) -> dict[str, Any]:
    """Aggregate last-24h trades + equity into summary dict.

    Args:
        trades: list of trade dicts (closed trades within window).
                Each must have keys: symbol, direction, pnl_usdt, reason, opened_at, closed_at.
        equity_history: list of equity_history rows (balance over time).
                Must have keys: ts, balance.

    Returns:
        dict with: trade_count, wins, losses, win_rate_pct, best_trade, worst_trade,
                   equity_start, equity_end, equity_delta_usdt, equity_delta_pct.
        None for any field that can't be computed (no trades, no equity history).
    """
    summary: dict[str, Any] = {
        "trade_count": len(trades),
        "wins": 0,
        "losses": 0,
        "win_rate_pct": None,
        "best_trade": None,
        "worst_trade": None,
        "equity_start": None,
        "equity_end": None,
        "equity_delta_usdt": None,
        "equity_delta_pct": None,
    }

    # Trade aggregation — wins/losses by pnl_usdt sign
    if trades:
        wins = [t for t in trades if (t.get("pnl_usdt") or 0) > 0]
        losses = [t for t in trades if (t.get("pnl_usdt") or 0) < 0]
        summary["wins"] = len(wins)
        summary["losses"] = len(losses)
        # win_rate over decided trades only (skip break-even pnl=0)
        decided = len(wins) + len(losses)
        if decided > 0:
            summary["win_rate_pct"] = round(len(wins) / decided * 100, 2)

        # Best / worst by pnl_usdt
        sorted_trades = sorted(trades, key=lambda t: t.get("pnl_usdt") or 0)
        summary["best_trade"] = sorted_trades[-1]
        summary["worst_trade"] = sorted_trades[0]

    # Equity delta — first vs last balance in window
    if equity_history:
        sorted_eq = sorted(equity_history, key=lambda e: e["ts"])
        first = sorted_eq[0]["balance"]
        last = sorted_eq[-1]["balance"]
        summary["equity_start"] = round(first, 2)
        summary["equity_end"] = round(last, 2)
        summary["equity_delta_usdt"] = round(last - first, 2)
        if first > 0:
            summary["equity_delta_pct"] = round((last - first) / first * 100, 2)

    return summary
