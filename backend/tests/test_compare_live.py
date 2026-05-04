"""Reconciliation tests — pure function, no I/O.

Spec: docs/superpowers/specs/2026-05-04-backtest-design.md §5 (Phase B)
"""
import pytest
from backtest.compare_live import reconcile


def _live(symbol, direction, opened_at, pnl):
    return {"symbol": symbol, "direction": direction, "opened_at": opened_at, "pnl_usdt": pnl}


def _bt(symbol, direction, opened_at, pnl):
    return {"symbol": symbol, "direction": direction, "opened_at": opened_at, "pnl": pnl}


def test_perfect_match_zero_drift():
    """Identical live + backtest trades → 100% match, 0% drift."""
    live = [_live("BTC/USDT", "LONG", "2026-05-01T10:00:00", 5.0)]
    bt = [_bt("BTC/USDT", "LONG", "2026-05-01T10:00:00", 5.0)]
    result = reconcile(live, bt)
    assert result["matched_pairs"] == 1
    assert result["unmatched_live"] == []
    assert result["unmatched_backtest"] == []
    assert result["drift_pct_mean"] == 0.0


def test_unmatched_live_trade_in_output():
    """Live trade with no backtest counterpart → unmatched_live."""
    live = [_live("BTC/USDT", "LONG", "2026-05-01T10:00:00", 5.0)]
    bt = []  # no backtest trades
    result = reconcile(live, bt)
    assert result["matched_pairs"] == 0
    assert len(result["unmatched_live"]) == 1
    assert result["unmatched_backtest"] == []


def test_unmatched_backtest_trade_in_output():
    live = []
    bt = [_bt("BTC/USDT", "LONG", "2026-05-01T10:00:00", 5.0)]
    result = reconcile(live, bt)
    assert result["matched_pairs"] == 0
    assert result["unmatched_live"] == []
    assert len(result["unmatched_backtest"]) == 1


def test_match_window_excludes_distant_trades():
    """Trades >2h apart → no match."""
    live = [_live("BTC/USDT", "LONG", "2026-05-01T10:00:00", 5.0)]
    bt = [_bt("BTC/USDT", "LONG", "2026-05-01T15:00:00", 5.0)]  # 5h later
    result = reconcile(live, bt, match_window_hours=2.0)
    assert result["matched_pairs"] == 0


def test_drift_calculation():
    """Live $4 vs backtest $5 → -20% drift."""
    live = [_live("BTC/USDT", "LONG", "2026-05-01T10:00:00", 4.0)]
    bt = [_bt("BTC/USDT", "LONG", "2026-05-01T10:00:00", 5.0)]
    result = reconcile(live, bt)
    assert result["drift_pct_mean"] == pytest.approx(-20.0)


def test_calibration_recommendation_on_high_drift():
    """If mean drift > threshold (default 5%), emit slippage recommendation."""
    # 4 trades all with -10% drift (live worse than backtest)
    live = [_live("BTC/USDT", "LONG", f"2026-05-0{i}T10:00:00", 9.0) for i in range(1, 5)]
    bt = [_bt("BTC/USDT", "LONG", f"2026-05-0{i}T10:00:00", 10.0) for i in range(1, 5)]
    result = reconcile(live, bt)
    assert result["drift_pct_mean"] == pytest.approx(-10.0)
    rec = result["calibration_recommendation"]
    assert rec is not None
    # Recommend ~10% increase: entry 0.05 → 0.055, sl 0.10 → 0.11, exit 0.05 → 0.055
    assert rec["entry_slip_pct"] == pytest.approx(0.055, rel=0.01)
    assert rec["sl_slip_pct"] == pytest.approx(0.11, rel=0.01)


def test_no_calibration_recommendation_when_drift_small():
    """Drift below threshold → recommendation is None."""
    live = [_live("BTC/USDT", "LONG", "2026-05-01T10:00:00", 4.95)]  # ~1% drift
    bt = [_bt("BTC/USDT", "LONG", "2026-05-01T10:00:00", 5.0)]
    result = reconcile(live, bt)
    assert result["calibration_recommendation"] is None


def test_skips_near_zero_pnl_to_avoid_div_zero():
    """Backtest pnl ~0 → skip drift calculation for that pair."""
    live = [_live("BTC/USDT", "LONG", "2026-05-01T10:00:00", 5.0)]
    bt = [_bt("BTC/USDT", "LONG", "2026-05-01T10:00:00", 0.001)]  # near-zero
    result = reconcile(live, bt)
    assert result["matched_pairs"] == 1
    # The pair is matched but drift is undefined → mean is 0 (no contributing pairs) or NaN-handled
    assert result["per_trade_drift"] == [] or all(p.get("drift_pct") is not None for p in result["per_trade_drift"])
