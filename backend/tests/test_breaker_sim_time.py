"""CircuitBreaker.check(now=...) — sim-time injection for backtest cooldown correctness.

Without sim-time injection, breaker.check() uses datetime.utcnow() (wall clock). In a
backtest, simulation time advances thousands of bars per real second, so a 120-min
cooldown locks the breaker for 120 REAL minutes — making the rest of the backtest
useless (every cycle just spams "TRIPPED").

This test pins the contract: check(now=sim_time) compares resume_at to sim_time, not
wall-clock. Live mode (no `now` arg) keeps wall-clock semantics (back-compat).
"""
from datetime import datetime, timedelta

from engine.safety.breaker import CircuitBreaker, BreakerState


def _fresh(consec_pause=120):
    return CircuitBreaker(
        starting_balance=2000.0,
        consecutive_loss_limit=3,
        consecutive_loss_pause_minutes=consec_pause,
        emergency_balance_threshold=None,
    )


def test_check_default_uses_wall_clock():
    """Live mode (no `now` arg) — back-compat path uses datetime.utcnow()."""
    b = _fresh()
    status = b.check()
    assert status.state == BreakerState.OPEN


def test_check_accepts_sim_time_for_trip_resume_at():
    """When tripped via sim-time check, resume_at is computed from sim-time, not wall-clock."""
    b = _fresh(consec_pause=120)
    sim_now = datetime(2025, 6, 1, 12, 0, 0)

    # Force 3 losses, then check at sim-time → should trip
    b.record_trade(-10.0, timestamp=sim_now)
    b.record_trade(-10.0, timestamp=sim_now)
    b.record_trade(-10.0, timestamp=sim_now)
    status = b.check(now=sim_now)
    assert status.state == BreakerState.TRIPPED
    # resume_at should be sim_now + 120 min, not wall-clock + 120 min
    expected_resume = sim_now + timedelta(minutes=120)
    assert status.resume_at == expected_resume


def test_check_resumes_when_sim_time_passes_resume_at():
    """The critical fix: cooldown elapses on sim-time, not wall-clock.

    Trip at sim-T0, advance sim-clock past resume_at, breaker should auto-resume.
    """
    b = _fresh(consec_pause=120)
    sim_t0 = datetime(2025, 6, 1, 12, 0, 0)

    b.record_trade(-10.0, timestamp=sim_t0)
    b.record_trade(-10.0, timestamp=sim_t0)
    b.record_trade(-10.0, timestamp=sim_t0)
    status = b.check(now=sim_t0)
    assert status.state == BreakerState.TRIPPED

    # Advance sim-clock by 121 min — past the 120-min cooldown
    sim_t1 = sim_t0 + timedelta(minutes=121)
    status = b.check(now=sim_t1)
    assert status.state == BreakerState.OPEN, \
        "Breaker must resume when sim-time passes resume_at"


def test_check_stays_tripped_before_sim_resume_at():
    """Mid-cooldown: state remains TRIPPED, no premature resume."""
    b = _fresh(consec_pause=120)
    sim_t0 = datetime(2025, 6, 1, 12, 0, 0)

    b.record_trade(-10.0, timestamp=sim_t0)
    b.record_trade(-10.0, timestamp=sim_t0)
    b.record_trade(-10.0, timestamp=sim_t0)
    b.check(now=sim_t0)

    # Only 60 min advanced — cooldown is 120 min, must remain tripped
    sim_mid = sim_t0 + timedelta(minutes=60)
    status = b.check(now=sim_mid)
    assert status.state == BreakerState.TRIPPED


def test_sim_time_resume_then_re_trip():
    """After resume, can trip again on next 3 losses (counter reset works correctly).

    Uses tiny losses so daily-loss-pct limit doesn't pre-empt the consec_loss path.
    """
    b = _fresh(consec_pause=60)
    sim_t0 = datetime(2025, 6, 1, 12, 0, 0)

    # First trip — 3 small losses (well under daily 3% = $60 budget)
    for _ in range(3):
        b.record_trade(-1.0, timestamp=sim_t0)
    b.check(now=sim_t0)

    # Resume after cooldown
    sim_t1 = sim_t0 + timedelta(minutes=61)
    assert b.check(now=sim_t1).state == BreakerState.OPEN

    # Three more losses → trip again on consec_loss path
    for _ in range(3):
        b.record_trade(-1.0, timestamp=sim_t1)
    status = b.check(now=sim_t1)
    assert status.state == BreakerState.TRIPPED
    assert status.resume_at == sim_t1 + timedelta(minutes=60)
