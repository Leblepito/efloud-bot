"""C9 regression: OB.near_swing must only consider PAST swings.

``engine.smc.SMCEngine.order_blocks`` tagged an Order Block as ``near_swing``
using ``abs(s.idx - i) < 30``, which also matched swings up to ~30 bars in the
FUTURE of the breakout bar ``i``. Future swings do not exist yet in live
trading, so the live ``near_swing`` value (a confluence input worth +5) diverged
from the backtest value for the same bar — a silent backtest/live divergence.

Fix: only count swings strictly in the past within the window
(``0 < i - s.idx < 30``).
"""
from types import SimpleNamespace

import pandas as pd

from engine.smc import SMCEngine


def _ob_fixture_df() -> pd.DataFrame:
    """18 flat bars (body 0, range 1.0 → ATR ≈ 1.0), one bearish OB candle,
    then a large bullish breakout (body 3 > 1.5·ATR) at bar 19."""
    rows = [{"open": 100.0, "close": 100.0, "high": 100.5, "low": 99.5, "volume": 1.0}
            for _ in range(18)]
    rows.append({"open": 100.0, "close": 99.0, "high": 100.0, "low": 99.0, "volume": 1.0})   # bar 18 bearish
    rows.append({"open": 99.0, "close": 102.0, "high": 102.0, "low": 99.0, "volume": 1.0})    # bar 19 bull breakout
    idx = pd.date_range("2026-01-01", periods=len(rows), freq="15min")
    return pd.DataFrame(rows, index=idx)


def _single_bull_ob(sl):
    eng = SMCEngine()
    obs = eng.order_blocks(_ob_fixture_df(), sh=[], sl=sl, trend="UNDEF")
    bulls = [o for o in obs if o.direction == "BULL"]
    assert len(bulls) == 1, f"expected exactly one BULL OB, got {obs}"
    return bulls[0]


def test_future_swing_does_not_set_near_swing():
    """A swing 5 bars AFTER the breakout must NOT tag the OB as near_swing."""
    future_swing = SimpleNamespace(idx=24, price=99.0)  # i+5, == OB bot price
    ob = _single_bull_ob([future_swing])
    assert ob.near_swing is False


def test_past_swing_sets_near_swing():
    """A swing 5 bars BEFORE the breakout (real, known) still counts."""
    past_swing = SimpleNamespace(idx=14, price=99.0)  # i-5, == OB bot price
    ob = _single_bull_ob([past_swing])
    assert ob.near_swing is True
