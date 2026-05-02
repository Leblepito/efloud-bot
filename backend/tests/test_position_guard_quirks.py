"""Position guard floating-point + display quirks.

Bug #1 — Display: max_size_pct=3.33% rendered as "3% of balance"
         (`:.0f` rounds 3.33 to 3, confuses operators).

Bug #2 — Float comparison: notional=32.95000001 vs max=32.95 triggered
         with same display value 32.95, blocking legitimate trades.
"""
from __future__ import annotations

from dataclasses import dataclass

import pytest

from engine.safety.position_guard import PositionGuard


@dataclass
class _StubPosition:
    symbol: str
    direction: str
    is_open: bool = True
    avg_entry_price: float = 0.0
    remaining_size: float = 0.0
    scenario_id: str | None = None
    id: str = "x"


def test_display_shows_two_decimal_percentage():
    """3.33% must render as '3.33%' not '3%' in rejection message."""
    guard = PositionGuard(max_notional_pct_of_balance=3.33)
    # Trigger the size-cap rejection
    res = guard.can_open_position(
        balance=1000.0, entry=100.0, size=10.0, sl=99.0,
        atr=1.0, direction="LONG", symbol="X/USDT",
        existing_positions=[], leverage=1,
    )
    assert res.allowed is False
    # Old bug: "(3% of balance)". Fix expected: "(3.33% of balance)".
    assert "3.33%" in res.reason, f"Expected '3.33%' in reason, got: {res.reason!r}"


def test_size_at_exact_cap_is_allowed_due_to_float_tolerance():
    """notional == max_notional + tiny FP residue should still pass.

    Real-world example: balance=1000, max_size_pct=3.33% → max_notional=33.3
    A signal computed for size that yields notional=33.30000000000001 must
    be allowed (otherwise the bot rejects 'Size 33.30 exceeds max 33.30').
    """
    guard = PositionGuard(max_notional_pct_of_balance=3.33)
    # Construct a notional that is a hair above max due to float math.
    # entry=100, size=0.333000000000001 → notional ≈ 33.300000000000001
    # max_notional = 1000 * 0.0333 = 33.300000000000004 (similar FP residue)
    # SL/ATR sanity: entry=100, sl=98 → sl_dist=2, atr=2 → sl_atr_mult=1.0 OK
    res = guard.can_open_position(
        balance=1000.0, entry=100.0, size=0.333000000000001,
        sl=98.0, atr=2.0,
        direction="LONG", symbol="X/USDT",
        existing_positions=[], leverage=1,
    )
    assert res.allowed is True, (
        f"Float-tolerance fail: {res.reason}. "
        "Comparison must allow notional ≈ max_notional within ~1e-6."
    )


def test_size_clearly_above_cap_is_still_rejected():
    """5% notional with 3.33% cap must still be blocked (regression guard)."""
    guard = PositionGuard(max_notional_pct_of_balance=3.33)
    res = guard.can_open_position(
        balance=1000.0, entry=50.0, size=1.0, sl=49.0,  # notional=50, cap=33.3
        atr=1.0, direction="LONG", symbol="X/USDT",
        existing_positions=[], leverage=1,
    )
    assert res.allowed is False
    assert "exceeds max" in res.reason
