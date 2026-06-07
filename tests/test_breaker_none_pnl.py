"""Tests for engine/safety/breaker.py None-safe pnl handling.

Bug-hunt #13: PR #167's calendar-midnight fix (bug-hunt #11) regressed when a
trade's pnl field is None — sum() raised TypeError on int + None, crashing every
run_cycle. These tests pin the None-skip behavior and the regression-safe daily
loss accumulation.

Run: python -m pytest tests/test_breaker_none_pnl.py -v
"""

import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

# Add repo root to path so `engine.*` imports resolve
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# Match production: breaker.py reads state.json from CWD if EFLOUD_STATE_DIR
# unset. We just set up a clean breaker directly to avoid that file dance.
from engine.safety.breaker import CircuitBreaker, BreakerState  # noqa: E402


def _midnight_ts():
    now = datetime.now(timezone.utc)
    return now.replace(hour=0, minute=0, second=0, microsecond=0)


def _today_trade(pnl, ts=None, ts_offset_seconds=0):
    """Build a trade record shaped like a journal entry."""
    base = _midnight_ts()
    if ts is None:
        ts = base + timedelta(seconds=ts_offset_seconds)
    return {"ts": ts, "pnl": pnl, "symbol": "TEST/USDT"}


def test_daily_pnl_skips_none_pnl_entries():
    """Bug-hunt #13 regression: trade pnl=None must not crash the breaker."""
    cb = CircuitBreaker(daily_loss_pct_limit=5.0, starting_balance=1000.0)
    cb.current_balance = 1000.0
    cb.trades_today = [
        _today_trade(-10.0, ts_offset_seconds=10),
        _today_trade(None, ts_offset_seconds=20),  # open position, no realized PnL
        _today_trade(-5.0, ts_offset_seconds=30),
    ]
    # Should not raise. The None entry is skipped, the two -10 + -5 = -15
    # still put us at -1.5% which is well under -5% so breaker stays OPEN.
    state = cb.check(datetime.now(timezone.utc))
    assert state.state == BreakerState.OPEN, f"expected OPEN, got {state.state}"


def test_daily_pnl_all_none_does_not_trip():
    """If all trades have pnl=None, daily_pnl=0, breaker stays OPEN."""
    cb = CircuitBreaker(daily_loss_pct_limit=5.0, starting_balance=1000.0)
    cb.current_balance = 1000.0
    cb.trades_today = [
        _today_trade(None, ts_offset_seconds=10),
        _today_trade(None, ts_offset_seconds=20),
    ]
    state = cb.check(datetime.now(timezone.utc))
    assert state.state == BreakerState.OPEN


def test_daily_pnl_realized_losses_still_trip():
    """Sanity: legitimate realized losses still trip the daily limit."""
    cb = CircuitBreaker(daily_loss_pct_limit=5.0, starting_balance=1000.0)
    cb.current_balance = 1000.0
    cb.trades_today = [
        _today_trade(-100.0, ts_offset_seconds=10),  # -10% realized
        _today_trade(None, ts_offset_seconds=20),    # open, ignored
    ]
    state = cb.check(datetime.now(timezone.utc))
    # -10% > -5% limit → TRIPPED
    assert state.state == BreakerState.TRIPPED


def test_old_buggy_behavior_would_crash():
    """Document the original bug for posterity — confirms the fix matters."""
    cb = CircuitBreaker(daily_loss_pct_limit=5.0, starting_balance=1000.0)
    cb.current_balance = 1000.0
    cb.trades_today = [
        _today_trade(-10.0, ts_offset_seconds=10),
        _today_trade(None, ts_offset_seconds=20),
    ]
    # If the fix is reverted, this should raise TypeError. With the fix in
    # place, it returns OPEN. We assert it does NOT raise.
    try:
        cb.check(datetime.now(timezone.utc))
    except TypeError as e:
        pytest.fail(f"breaker crashed on None pnl (bug-hunt #13 regression): {e}")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
