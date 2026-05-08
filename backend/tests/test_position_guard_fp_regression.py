"""Position guard FP-tolerance regression — spec §9.5.

The position guard rejects when notional > max_notional + 1e-6.
This test asserts that at exact cap boundary, position is ALLOWED
(the +1e-6 epsilon absorbs FP residue).
"""
import pytest
from engine.safety.position_guard import PositionGuard


@pytest.mark.parametrize("balance,cap_pct", [
    (500.0, 1.0), (500.0, 2.0), (500.0, 3.33),
    (1000.0, 2.0), (1000.0, 3.33), (1000.0, 5.0),
    (2000.0, 2.0), (2000.0, 3.33), (2000.0, 5.0),
    (5000.0, 1.0), (5000.0, 10.0),
])
def test_at_exact_cap_boundary_position_allowed(balance, cap_pct):
    """Boundary case: notional == max_notional + tiny FP residue -> allowed."""
    guard = PositionGuard(max_notional_pct_of_balance=cap_pct)
    # Construct: entry x size with FP residue ~= balance * cap_pct/100
    target_margin = balance * (cap_pct / 100)
    # Add tiny FP noise via multiplication — produces residue ~1e-15
    entry = target_margin * 1.0000000000001
    size = 1.0
    res = guard.can_open_position(
        balance=balance, entry=entry, size=size,
        sl=entry * 0.95, atr=entry * 0.05,
        direction="LONG", symbol="BTC/USDT",
        existing_positions=[], leverage=1,
    )
    assert res.allowed is True, (
        f"FP-tolerance regression at balance=${balance}, cap={cap_pct}%: {res.reason}"
    )


def test_clearly_above_cap_still_rejected():
    """Sanity: 50% over cap is still rejected (epsilon doesn't blow open the door)."""
    guard = PositionGuard(max_notional_pct_of_balance=2.0)
    # notional = 30 vs max = 1000 * 2% = 20
    res = guard.can_open_position(
        balance=1000.0, entry=30.0, size=1.0,
        sl=29.0, atr=1.5, direction="LONG", symbol="BTC/USDT",
        existing_positions=[], leverage=1,
    )
    assert res.allowed is False
    assert "exceeds max" in res.reason
