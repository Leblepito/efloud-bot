"""PositionGuard max_open_positions enforcement gate.

Without this gate, the engine could open arbitrary numbers of simultaneous
positions despite `risk.max_open_positions` being declared in config.
Aggressive Mode v1 needs this enforced because we're going from de-facto-1
to max=5 — without enforcement, signals could pile up beyond intended exposure.
"""
from dataclasses import dataclass
from typing import Optional

from engine.safety.position_guard import PositionGuard


@dataclass
class _FakePos:
    symbol: str
    direction: str
    is_open: bool = True
    avg_entry_price: float = 100.0
    remaining_size: float = 0.1
    scenario_id: Optional[str] = None
    id: str = "fake-pos"


def _guard(max_open=5):
    return PositionGuard(
        max_notional_pct_of_balance=10.0,
        max_total_exposure_multiplier=5.0,
        max_holding_hours=24.0,
        max_pyramid_adds=0,
        min_sl_distance_atr=0.5,
        max_sl_distance_atr=5.0,
        reserve_balance=0.0,
        max_open_positions=max_open,
    )


def _ok_args(symbol="ZIL/USDT", direction="LONG"):
    """Sane args that pass all *other* guards — the test isolates the new gate."""
    return dict(
        balance=2000.0,
        entry=100.0,
        size=0.1,           # notional 10 = 0.5% of $2000 (well under 10% max)
        sl=99.0,            # 1.0 abs distance
        atr=1.0,            # sl_atr_mult = 1.0 (in [0.5, 5.0])
        direction=direction,
        symbol=symbol,
        leverage=5,
    )


def test_under_max_allows_new_position():
    """4 open + max=5 → 5th allowed."""
    guard = _guard(max_open=5)
    existing = [
        _FakePos(symbol=f"S{i}/USDT", direction="LONG", id=f"p{i}")
        for i in range(4)
    ]
    result = guard.can_open_position(existing_positions=existing, **_ok_args())
    assert result.allowed, f"Should allow 5th position, got: {result.reason}"


def test_at_max_rejects_new_position():
    """5 open + max=5 → reject."""
    guard = _guard(max_open=5)
    existing = [
        _FakePos(symbol=f"S{i}/USDT", direction="LONG", id=f"p{i}")
        for i in range(5)
    ]
    result = guard.can_open_position(existing_positions=existing, **_ok_args())
    assert not result.allowed
    assert "max_open_positions" in result.reason.lower() or "5" in result.reason


def test_over_max_rejects_new_position():
    """6 open (legacy state) + max=5 → still reject."""
    guard = _guard(max_open=5)
    existing = [
        _FakePos(symbol=f"S{i}/USDT", direction="LONG", id=f"p{i}")
        for i in range(6)
    ]
    result = guard.can_open_position(existing_positions=existing, **_ok_args())
    assert not result.allowed


def test_max_one_legacy_single_asset_mode():
    """max=1 → only one open position ever (legacy single-asset)."""
    guard = _guard(max_open=1)
    existing = [_FakePos(symbol="BTC/USDT", direction="LONG", id="p0")]
    # Different symbol — should still reject since max=1
    result = guard.can_open_position(existing_positions=existing, **_ok_args(symbol="ETH/USDT"))
    assert not result.allowed


def test_closed_positions_dont_count_toward_max():
    """5 open + 3 closed + max=5 → reject 6th (closed don't matter, but...).

    Wait: 5 open + max=5 = at-cap. The 3 closed positions are irrelevant.
    This test pins that we count `is_open` only, not total list length.
    """
    guard = _guard(max_open=5)
    existing = [
        _FakePos(symbol=f"S{i}/USDT", direction="LONG", id=f"p{i}")
        for i in range(5)
    ] + [
        _FakePos(symbol=f"OLD{i}/USDT", direction="LONG", is_open=False, id=f"old{i}")
        for i in range(3)
    ]
    result = guard.can_open_position(existing_positions=existing, **_ok_args())
    # 5 open → at max, reject
    assert not result.allowed

    # Drop one open — 4 open + 3 closed → allow
    existing[0].is_open = False
    result = guard.can_open_position(existing_positions=existing, **_ok_args())
    assert result.allowed, f"4 open + 3 closed should allow 5th open, got: {result.reason}"


def test_default_max_open_is_unlimited_or_high():
    """Backwards-compat: PositionGuard without max_open_positions kwarg should
    not break — either unlimited (no gate) or some high default like 999.
    Existing tests may construct guard without this kwarg.
    """
    # Guard without max_open_positions kwarg
    guard = PositionGuard(
        max_notional_pct_of_balance=10.0,
        max_total_exposure_multiplier=5.0,
        max_holding_hours=24.0,
        max_pyramid_adds=0,
        min_sl_distance_atr=0.5,
        max_sl_distance_atr=5.0,
        reserve_balance=0.0,
    )
    existing = [
        _FakePos(symbol=f"S{i}/USDT", direction="LONG", id=f"p{i}")
        for i in range(50)
    ]
    result = guard.can_open_position(existing_positions=existing, **_ok_args())
    # If default is unlimited or >= 50, should allow
    assert result.allowed, f"Default should be permissive, got: {result.reason}"
