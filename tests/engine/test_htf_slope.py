"""A4: orchestrator must compute htf_slope_pct for the RegimeAgent review ctx.

RegimeAgent.filter_context whitelists htf_slope_pct, but the orchestrator never
supplied it (phantom field — the agent saw only htf_bias + adx). This unit-tests
the slope computation now wired into the agent-review context.
"""
import pandas as pd
import pytest

from engine.safe_orchestrator import SafeOrchestrator


def _df(closes):
    return pd.DataFrame({"open": closes, "high": closes, "low": closes, "close": closes})


def test_uptrend_is_positive():
    assert SafeOrchestrator._htf_slope_pct(_df([100.0 + i for i in range(26)]), lookback=20) > 0


def test_downtrend_is_negative():
    assert SafeOrchestrator._htf_slope_pct(_df([200.0 - i for i in range(26)]), lookback=20) < 0


def test_flat_is_zero():
    assert SafeOrchestrator._htf_slope_pct(_df([100.0] * 30), lookback=20) == 0.0


def test_short_df_returns_zero():
    assert SafeOrchestrator._htf_slope_pct(_df([100.0] * 5), lookback=20) == 0.0


def test_exact_value_plus_10pct():
    # iloc[-1]=110, iloc[-1-20]=100 → +10%
    closes = [100.0] * 21 + [110.0]
    assert SafeOrchestrator._htf_slope_pct(_df(closes), lookback=20) == pytest.approx(10.0)
