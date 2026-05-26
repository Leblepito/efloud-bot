"""PositionGuard reverse-on-profit policy.

When an opposite-direction signal arrives on a symbol that already has an
open position, the default is REJECT — TP or SL must fire first. The bot
must not rely on Binance's isolated-margin auto-flip behaviour (which was
silently closing the existing side whenever the bot fired a contra-side
order — the FIL incident, 2026-05-14).

Exception: if the current unrealized PnL clears a small fee+slippage
buffer (default 0.2%), the reverse is permitted — the market has moved
in the position's favour and the new signal confirms the move.

Partial-close state (TP1 hit, trail active) is always blocked: the
remaining size is on a risk-free trail, and adding a flip would
complicate atomicity for no expected-value gain.
"""
from dataclasses import dataclass, field
from typing import List, Optional

from engine.safety.position_guard import PositionGuard


@dataclass
class _FakeExit:
    """Stand-in for engine.lifecycle.Exit — only fields read by the guard matter."""
    size: float = 0.05
    price: float = 100.0
    pnl: float = 0.0


@dataclass
class _FakePos:
    symbol: str = "FIL/USDT"
    direction: str = "LONG"
    is_open: bool = True
    avg_entry_price: float = 100.0
    remaining_size: float = 0.1
    scenario_id: Optional[str] = None
    id: str = "fake-pos-1"
    exits: List[_FakeExit] = field(default_factory=list)


def _guard(threshold: float = 0.2):
    return PositionGuard(
        max_notional_pct_of_balance=10.0,
        max_total_exposure_multiplier=5.0,
        max_holding_hours=24.0,
        max_pyramid_adds=0,
        min_sl_distance_atr=0.5,
        max_sl_distance_atr=5.0,
        reserve_balance=0.0,
        max_open_positions=10,
        reverse_min_profit_pct=threshold,
    )


# ── 1. can_reverse_position: profit threshold ──────────────────────────────

def test_reverse_allowed_when_profitable_long():
    """LONG @ 100 with price 101 → 1.0% PnL > 0.2% threshold → allow."""
    pos = _FakePos(direction="LONG", avg_entry_price=100.0)
    result = _guard().can_reverse_position(pos, current_price=101.0)
    assert result.allowed
    assert "REVERSE_OK" in result.reason


def test_reverse_allowed_when_profitable_short():
    """SHORT @ 100 with price 98 → 2.0% PnL > threshold → allow."""
    pos = _FakePos(direction="SHORT", avg_entry_price=100.0)
    result = _guard().can_reverse_position(pos, current_price=98.0)
    assert result.allowed
    assert "REVERSE_OK" in result.reason


def test_reverse_rejected_when_underwater_long():
    """LONG @ 100 with price 99 → -1.0% PnL → reject."""
    pos = _FakePos(direction="LONG", avg_entry_price=100.0)
    result = _guard().can_reverse_position(pos, current_price=99.0)
    assert not result.allowed
    assert "REVERSE_BLOCKED_NOT_PROFITABLE" in result.reason


def test_reverse_rejected_when_underwater_short():
    """SHORT @ 100 with price 101 → -1.0% PnL → reject."""
    pos = _FakePos(direction="SHORT", avg_entry_price=100.0)
    result = _guard().can_reverse_position(pos, current_price=101.0)
    assert not result.allowed
    assert "REVERSE_BLOCKED_NOT_PROFITABLE" in result.reason


def test_reverse_rejected_when_marginal_profit():
    """LONG @ 100 with price 100.1 → 0.1% PnL < 0.2% threshold → reject.
    The buffer exists precisely to cover fee+slippage on this kind of move."""
    pos = _FakePos(direction="LONG", avg_entry_price=100.0)
    result = _guard().can_reverse_position(pos, current_price=100.1)
    assert not result.allowed
    assert "REVERSE_BLOCKED_NOT_PROFITABLE" in result.reason


def test_reverse_rejected_at_breakeven():
    """LONG @ 100 with price 100.0 → 0% PnL → reject."""
    pos = _FakePos(direction="LONG", avg_entry_price=100.0)
    result = _guard().can_reverse_position(pos, current_price=100.0)
    assert not result.allowed


def test_reverse_threshold_overridable_via_param():
    """min_profit_pct kwarg overrides constructor value."""
    pos = _FakePos(direction="LONG", avg_entry_price=100.0)
    # 0.5% PnL, default threshold 0.2 → allow
    assert _guard().can_reverse_position(pos, 100.5).allowed
    # Same PnL, threshold 1.0 → reject
    assert not _guard().can_reverse_position(pos, 100.5, min_profit_pct=1.0).allowed


# ── 2. Partial close (TP1 hit) blocks reverse ───────────────────────────────

def test_reverse_rejected_after_tp1_hit():
    """Even if remaining position is wildly profitable, having any exit
    recorded means TP1 has fired; the trail is risk-free — don't flip it."""
    pos = _FakePos(
        direction="LONG", avg_entry_price=100.0,
        exits=[_FakeExit(size=0.05, price=105.0, pnl=0.25)],
    )
    result = _guard().can_reverse_position(pos, current_price=110.0)
    assert not result.allowed
    assert "REVERSE_BLOCKED_PARTIAL_CLOSED" in result.reason


def test_reverse_rejected_when_position_closed():
    """A closed position cannot be reversed (defensive — caller should
    have filtered, but the guard owns its own invariant)."""
    pos = _FakePos(is_open=False)
    result = _guard().can_reverse_position(pos, current_price=110.0)
    assert not result.allowed
    assert "REVERSE_BLOCKED_POSITION_CLOSED" in result.reason


def test_reverse_rejected_on_invalid_price():
    pos = _FakePos(direction="LONG", avg_entry_price=100.0)
    assert not _guard().can_reverse_position(pos, current_price=0).allowed
    assert not _guard().can_reverse_position(pos, current_price=-1).allowed


def test_reverse_rejected_on_invalid_avg_entry():
    pos = _FakePos(direction="LONG", avg_entry_price=0.0)
    assert not _guard().can_reverse_position(pos, current_price=100.0).allowed


# ── 3. can_open_position: opposite-direction now blocks ─────────────────────

def _open_args(symbol="FIL/USDT", direction="SHORT"):
    return dict(
        balance=2000.0,
        entry=100.0,
        size=0.1,
        sl=101.0 if direction == "SHORT" else 99.0,
        atr=1.0,
        direction=direction,
        symbol=symbol,
        leverage=5,
    )


def test_opposite_direction_blocks_open():
    """Existing LONG + incoming SHORT signal → block with explicit reason."""
    existing = [_FakePos(symbol="FIL/USDT", direction="LONG", id="p1")]
    result = _guard().can_open_position(existing_positions=existing, **_open_args())
    assert not result.allowed
    assert "OPPOSITE_DIRECTION_EXISTS" in result.reason


def test_same_direction_still_blocks_with_legacy_reason():
    """Regression: duplicate-direction check still fires first and uses
    its existing reason format (not the new OPPOSITE_DIRECTION one)."""
    existing = [_FakePos(symbol="FIL/USDT", direction="SHORT", id="p1")]
    result = _guard().can_open_position(existing_positions=existing, **_open_args())
    assert not result.allowed
    assert "Already SHORT open" in result.reason
    assert "OPPOSITE" not in result.reason


def test_no_existing_position_allows_open():
    """No existing position on the symbol → normal allow path."""
    result = _guard().can_open_position(existing_positions=[], **_open_args())
    assert result.allowed


def test_opposite_on_different_symbol_does_not_block():
    """LONG ETH/USDT open + incoming SHORT FIL/USDT → opposite check only
    fires when symbol matches."""
    existing = [_FakePos(symbol="ETH/USDT", direction="LONG", id="p-eth")]
    result = _guard().can_open_position(existing_positions=existing, **_open_args())
    assert result.allowed


def test_opposite_check_ignores_hedge_scenarios():
    """Position with scenario_id (hedge leg) does NOT trigger opposite block.
    Mirrors duplicate-direction's hedge exemption."""
    existing = [_FakePos(symbol="FIL/USDT", direction="LONG", id="p1",
                         scenario_id="hedge-1")]
    result = _guard().can_open_position(existing_positions=existing, **_open_args())
    assert result.allowed


def test_opposite_check_ignores_closed_positions():
    """Closed position with opposite direction → not a block."""
    existing = [_FakePos(symbol="FIL/USDT", direction="LONG", id="p1", is_open=False)]
    result = _guard().can_open_position(existing_positions=existing, **_open_args())
    assert result.allowed


def test_opposite_direction_allowed_in_hedge_mode():
    """If hedge_mode is True, PositionGuard must allow opposite-direction entry."""
    # We construct a custom guard where hedge_mode=True
    guard = PositionGuard(
        max_notional_pct_of_balance=10.0,
        max_total_exposure_multiplier=5.0,
        max_holding_hours=24.0,
        max_pyramid_adds=0,
        min_sl_distance_atr=0.5,
        max_sl_distance_atr=5.0,
        reserve_balance=0.0,
        max_open_positions=10,
        reverse_min_profit_pct=0.2,
        hedge_mode=True,
    )
    existing = [_FakePos(symbol="FIL/USDT", direction="LONG", id="p1")]
    
    # Attempting to open a SHORT position (opposite to LONG)
    res = guard.can_open_position(existing_positions=existing, **_open_args(direction="SHORT"))
    
    assert res.allowed is True
    assert "OPPOSITE_DIRECTION_EXISTS" not in res.reason

