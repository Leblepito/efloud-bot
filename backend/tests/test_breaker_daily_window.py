"""Daily-loss breaker window must match its calendar-midnight resume (bug-hunt #11).

Pre-fix: daily_pnl summed `trades_today` (a ROLLING 24h window, _cleanup keeps
ts > now-24h), but a daily-loss trip set resume_at to the next CALENDAR midnight.
A late-day loss stayed inside the rolling window past midnight, so at the midnight
resume the breaker immediately re-tripped — extending the halt ~1 day. Fix: sum only
trades since calendar midnight so the window matches the resume semantics.
"""
from datetime import datetime

from engine.safety.breaker import BreakerState, CircuitBreaker


def test_daily_loss_uses_calendar_day_not_rolling_24h():
    b = CircuitBreaker(daily_loss_pct_limit=3.0, starting_balance=1000.0)
    now = datetime(2026, 6, 5, 6, 0, 0)
    # A 5% loss YESTERDAY at 22:00 — before today's midnight, but still inside the
    # rolling 24h window at 06:00. It must NOT count toward TODAY's daily loss.
    b.record_trade(pnl=-50.0, timestamp=datetime(2026, 6, 4, 22, 0, 0))
    status = b.check(now=now)
    assert status.state == BreakerState.OPEN   # calendar-day loss = 0 → no trip


def test_daily_loss_trips_on_a_today_loss():
    b = CircuitBreaker(daily_loss_pct_limit=3.0, starting_balance=1000.0)
    now = datetime(2026, 6, 5, 6, 0, 0)
    # A 5% loss TODAY at 05:00 → must still trip (fix must not stop real same-day trips).
    b.record_trade(pnl=-50.0, timestamp=datetime(2026, 6, 5, 5, 0, 0))
    status = b.check(now=now)
    assert status.state == BreakerState.TRIPPED
