"""Daily report aggregate — compute_summary(trades, equity_history)."""
from __future__ import annotations

from datetime import datetime, timezone

from ops.daily_report.aggregate import compute_summary


def _trade(symbol: str, pnl: float, direction: str = "LONG", reason: str = "TP2") -> dict:
    """Helper to build a trade row matching the DB schema."""
    return {
        "id": "abc-123",
        "symbol": symbol,
        "direction": direction,
        "entry": 100.0,
        "exit": 100.0 + pnl / 0.01 if direction == "LONG" else 100.0 - pnl / 0.01,
        "size": 0.01,
        "pnl_usdt": pnl,
        "pnl_pct": pnl / 100.0 * 100,
        "reason": reason,
        "opened_at": datetime(2026, 5, 7, 10, 0, tzinfo=timezone.utc),
        "closed_at": datetime(2026, 5, 7, 12, 0, tzinfo=timezone.utc),
        "confluence": 80,
    }


def _equity(balance: float, ts: datetime) -> dict:
    return {"ts": ts, "balance": balance, "open_positions_count": 0}


def test_empty_trades():
    summary = compute_summary(trades=[], equity_history=[])
    assert summary["trade_count"] == 0
    assert summary["wins"] == 0
    assert summary["losses"] == 0
    assert summary["win_rate_pct"] is None
    assert summary["best_trade"] is None
    assert summary["worst_trade"] is None
    assert summary["equity_start"] is None
    assert summary["equity_end"] is None


def test_all_winners():
    trades = [_trade("BTC/USDT", 10.0), _trade("ETH/USDT", 5.0)]
    summary = compute_summary(trades=trades, equity_history=[])
    assert summary["trade_count"] == 2
    assert summary["wins"] == 2
    assert summary["losses"] == 0
    assert summary["win_rate_pct"] == 100.0
    assert summary["best_trade"]["pnl_usdt"] == 10.0
    assert summary["worst_trade"]["pnl_usdt"] == 5.0


def test_all_losers():
    trades = [_trade("BTC/USDT", -10.0, reason="SL"), _trade("ETH/USDT", -5.0, reason="SL")]
    summary = compute_summary(trades=trades, equity_history=[])
    assert summary["wins"] == 0
    assert summary["losses"] == 2
    assert summary["win_rate_pct"] == 0.0
    assert summary["best_trade"]["pnl_usdt"] == -5.0
    assert summary["worst_trade"]["pnl_usdt"] == -10.0


def test_mixed_with_best_and_worst():
    trades = [
        _trade("BTC/USDT", 15.0),
        _trade("ETH/USDT", -8.0, reason="SL"),
        _trade("XRP/USDT", 3.0),
        _trade("DOGE/USDT", -2.0, reason="SL"),
    ]
    summary = compute_summary(trades=trades, equity_history=[])
    assert summary["trade_count"] == 4
    assert summary["wins"] == 2
    assert summary["losses"] == 2
    assert summary["win_rate_pct"] == 50.0
    assert summary["best_trade"]["symbol"] == "BTC/USDT"
    assert summary["worst_trade"]["symbol"] == "ETH/USDT"


def test_equity_delta_computed():
    eq_start = datetime(2026, 5, 7, 8, 0, tzinfo=timezone.utc)
    eq_end = datetime(2026, 5, 8, 8, 0, tzinfo=timezone.utc)
    equity_history = [_equity(2000.0, eq_start), _equity(2050.0, eq_end)]
    summary = compute_summary(trades=[], equity_history=equity_history)
    assert summary["equity_start"] == 2000.0
    assert summary["equity_end"] == 2050.0
    assert summary["equity_delta_usdt"] == 50.0
    assert summary["equity_delta_pct"] == 2.5
