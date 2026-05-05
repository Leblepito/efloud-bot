"""CircuitBreaker.sync_balance — keeps current/peak in sync with live exchange equity.

Without sync, current_balance only updates via record_trade(pnl) which is realized-only.
On open positions, unrealized PnL or external wallet changes (manual transfer) drift the
breaker state away from reality. Real incident (2026-05-05): bot HALTED with reported
balance $993 while wallet was actually $2040 because the breaker tracked stale state.
"""
from engine.safety.breaker import CircuitBreaker, BreakerState


def _fresh_breaker(starting=2000.0, threshold=1800.0):
    return CircuitBreaker(
        starting_balance=starting,
        emergency_balance_threshold=threshold,
    )


def test_sync_balance_updates_current():
    breaker = _fresh_breaker()
    assert breaker.current_balance == 2000.0
    breaker.sync_balance(2040.0)
    assert breaker.current_balance == 2040.0


def test_sync_balance_raises_peak_when_higher():
    breaker = _fresh_breaker()
    assert breaker.peak_balance == 2000.0
    breaker.sync_balance(2500.0)
    assert breaker.peak_balance == 2500.0
    assert breaker.current_balance == 2500.0


def test_sync_balance_does_not_lower_peak_when_dropping():
    """Peak is high-watermark — never goes down even if current drops."""
    breaker = _fresh_breaker()
    breaker.sync_balance(2500.0)
    assert breaker.peak_balance == 2500.0
    breaker.sync_balance(2200.0)
    assert breaker.current_balance == 2200.0
    assert breaker.peak_balance == 2500.0   # unchanged


def test_sync_balance_does_not_clear_halted_state():
    """HALTED is sticky by design — sync_balance MUST NOT auto-recover.

    Operator must manual_reset() after acknowledging the triggering condition.
    Otherwise a balance bounce (e.g., a pump that briefly recovers wallet)
    would silently un-halt the bot.
    """
    breaker = _fresh_breaker(starting=2000.0, threshold=1800.0)
    # Force HALT
    breaker.current_balance = 1500.0   # below threshold
    breaker.check()                     # triggers _halt
    assert breaker.status.state == BreakerState.HALTED

    # Now wallet recovers above threshold
    breaker.sync_balance(2200.0)

    # current_balance updated, but HALT state persists
    assert breaker.current_balance == 2200.0
    assert breaker.status.state == BreakerState.HALTED


def test_sync_balance_then_manual_reset_clears_halt():
    """After manual_reset following a sync, breaker resumes correctly."""
    breaker = _fresh_breaker(starting=2000.0, threshold=1800.0)
    breaker.current_balance = 1500.0
    breaker.check()
    assert breaker.status.state == BreakerState.HALTED

    breaker.sync_balance(2200.0)
    breaker.manual_reset("operator acknowledged after wallet investigation")

    # State cleared, current at synced value
    assert breaker.status.state == BreakerState.OPEN
    assert breaker.current_balance == 2200.0
    # peak should match current after reset (drawdown protection)
    assert breaker.peak_balance == 2200.0

    # Subsequent check — does NOT re-trip because current > threshold
    status = breaker.check()
    assert status.state == BreakerState.OPEN


def test_sync_balance_with_open_state_stays_open():
    """Normal-flow: sync updates values, OPEN state unchanged."""
    breaker = _fresh_breaker()
    assert breaker.status.state == BreakerState.OPEN
    breaker.sync_balance(2100.0)
    breaker.check()
    assert breaker.status.state == BreakerState.OPEN
    assert breaker.current_balance == 2100.0
