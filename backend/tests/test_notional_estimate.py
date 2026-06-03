"""F1: give the RiskReviewer agent a real size_notional_pct, not a hardcoded 0.0.

The agent review ctx passed size_notional_pct=0.0 (sizing happens later), so the
risk agent's "notional > 8% → REJECT" rule could never fire. F1 estimates the
notional up-front using the SAME sizer the open step uses, so the (shadow) risk
review is meaningful. This unit-tests the estimator.
"""
import pytest

from engine.safe_orchestrator import SafeOrchestrator

_CFG = {
    "timeframes": {"htf": "4h", "mtf": "1h", "entry": "15m"},
    "structure": {"swing_lookback": 5, "ob_sequential": 5, "body_mode": True,
                  "eq_threshold_pct": 0.1, "range_lookback": 50},
    "fibonacci": {"ote_lower": 0.618, "ote_upper": 0.786, "ext_tp2": 1.618},
    "safety": {"adx_trend_threshold": 25, "adx_range_threshold": 20,
               "volatile_atr_mult": 2.5, "daily_loss_limit_pct": 10.0,
               "weekly_drawdown_limit_pct": 25.0, "consecutive_loss_limit": 3,
               "starting_balance": 2000, "max_position_notional_pct": 2.0},
    "risk": {"min_confluence": 50, "min_rr": 1.8, "max_open_positions": 10,
             "recency_bars": 40, "risk_per_trade_pct": 1.0},
    "operation": {"watch_only": True},
    "exchange": {"leverage": 5},
}


@pytest.fixture
def orch(tmp_path):
    return SafeOrchestrator(config=dict(_CFG), state_dir=str(tmp_path))


def test_estimate_notional_positive_for_valid_trade(orch):
    pct = orch._estimate_size_notional_pct(balance=2000.0, entry=100.0, sl=98.0)
    assert pct > 0.0
    assert pct <= 100.0  # sane bound (it's a % of balance)


def test_estimate_notional_zero_without_balance(orch):
    assert orch._estimate_size_notional_pct(0.0, 100.0, 98.0) == 0.0
    assert orch._estimate_size_notional_pct(None, 100.0, 98.0) == 0.0


def test_estimate_notional_zero_for_bad_entry(orch):
    assert orch._estimate_size_notional_pct(2000.0, 0.0, 98.0) == 0.0
