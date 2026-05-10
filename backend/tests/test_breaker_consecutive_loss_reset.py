"""Regression: ``consecutive_losses`` counter resets on a winning trade.

Existing tests (``test_breaker_sim_time.py``, ``test_breaker_balance_sync.py``)
cover trip-on-3-losses + cooldown + sim-time resume. The counter-reset path in
``engine/safety/breaker.py`` ``record_trade`` (``if pnl < 0`` increments,
``else`` resets) had no dedicated test: a winning trade slipping between two
losses should NOT count toward the trip threshold.

Without the reset, the bot would falsely trip on the next 2 losses (cumulative
loss count = 4) even though the streak was broken in the middle.
"""
from datetime import datetime

from engine.safety.breaker import CircuitBreaker, BreakerState


def _fresh():
    return CircuitBreaker(
        starting_balance=2000.0,
        consecutive_loss_limit=3,
        consecutive_loss_pause_minutes=120,
        emergency_balance_threshold=None,
    )


def test_winning_trade_resets_consecutive_loss_counter():
    """A win between losses sets ``consecutive_losses`` back to 0 — and
    therefore the next 2 losses must NOT trip the breaker."""
    b = _fresh()
    sim_t = datetime(2026, 5, 9, 12, 0, 0)

    b.record_trade(-5.0, timestamp=sim_t)
    b.record_trade(-5.0, timestamp=sim_t)
    assert b.consecutive_losses == 2

    b.record_trade(+10.0, timestamp=sim_t)
    assert b.consecutive_losses == 0, "Win must reset the counter"

    b.record_trade(-5.0, timestamp=sim_t)
    b.record_trade(-5.0, timestamp=sim_t)
    assert b.consecutive_losses == 2

    status = b.check(now=sim_t)
    assert status.state == BreakerState.OPEN, \
        "Counter is 2 (not 4) after the win, breaker must NOT trip"


def test_break_even_trade_zero_pnl_resets_counter():
    """Zero-pnl close hits the ``else`` branch (``pnl < 0`` is False), so the
    counter resets — same path as a winning trade."""
    b = _fresh()
    sim_t = datetime(2026, 5, 9, 12, 0, 0)

    b.record_trade(-5.0, timestamp=sim_t)
    b.record_trade(-5.0, timestamp=sim_t)
    assert b.consecutive_losses == 2

    b.record_trade(0.0, timestamp=sim_t)
    assert b.consecutive_losses == 0
