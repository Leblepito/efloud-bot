from datetime import datetime, timedelta, timezone

from engine.safety.breaker import BreakerState, CircuitBreaker


def _now():
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _breaker():
    return CircuitBreaker(
        daily_loss_pct_limit=10.0,
        weekly_drawdown_pct_limit=25.0,
        consecutive_loss_limit=3,
        starting_balance=400.0,
        emergency_balance_threshold=0,
    )


def test_recent_peak_still_halts():
    b = _breaker()
    b.peak_balance = 400.0
    b.peak_set_at = _now() - timedelta(days=2)
    b.current_balance = 290.0
    assert b.check().state == BreakerState.HALTED


def test_stale_peak_is_rebased_and_does_not_halt():
    b = _breaker()
    b.peak_balance = 400.0
    b.peak_set_at = _now() - timedelta(days=14)
    b.current_balance = 290.0
    st = b.check()
    assert st.state == BreakerState.OPEN
    assert b.peak_balance == 290.0


def test_peak_set_at_roundtrip():
    b = _breaker()
    stamp = _now() - timedelta(days=3)
    b.peak_set_at = stamp
    b2 = _breaker()
    b2.restore_from_dict(b.to_dict())
    assert b2.peak_set_at == stamp
