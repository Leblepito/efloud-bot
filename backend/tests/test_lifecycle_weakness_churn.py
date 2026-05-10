"""Regression: WEAKNESS churn guard prevents geometric-decay exits.

Bug history (pre-PR #30): a TP1-hit position with sustained weakness signal got
``partial_close(reason="WEAKNESS")`` called on every tick. Each call shrinks the
position by 25% — so ~4 weakness ticks evaporate the post-TP1 remainder to
roughly a third of its size, with no real adverse-momentum signal between them.

Fix in ``engine/lifecycle.py`` ``PositionLifecycle.on_tick`` weakness branch:
  * MAX_WEAKNESS_EXITS = 3   — hard cap per position
  * WEAKNESS_COOLDOWN_BARS = 4 minutes between exits
  * MIN_REMAINING_SIZE = 0.01 — skip dust-sized residuals

These tests pin all three guards plus the pre-TP1 gate.
"""
from datetime import datetime, timedelta, timezone

import pytest

from engine.lifecycle import PositionLifecycle


def _open_tp1_hit_long(lifecycle, symbol="ETH/USDT"):
    """Open a LONG and walk it through TP1 so the weakness branch is reachable."""
    pos = lifecycle.open_position(
        symbol, "LONG",
        entry_price=2000.0, size=1.0,
        sl=1980.0, tp1=2040.0, tp2=2080.0,
    )
    lifecycle.partial_close(pos, price=2040.0, size_pct=0.5, reason="TP1")
    assert pos.tp1_hit
    assert pos.remaining_size == pytest.approx(0.5)
    return pos


def test_weakness_first_exit_with_no_prior_ts_fires():
    """First WEAKNESS exit (last_weakness_ts is None) bypasses cooldown gate."""
    lc = PositionLifecycle()
    pos = _open_tp1_hit_long(lc)
    assert pos.weakness_exit_count == 0
    assert pos.last_weakness_ts is None

    lc.on_tick({pos.symbol: 2030.0}, intent_checker=lambda _p: True)

    assert pos.weakness_exit_count == 1
    assert pos.last_weakness_ts is not None


def test_weakness_capped_at_3_exits_even_under_sustained_weak_signal():
    """Counter must not exceed MAX_WEAKNESS_EXITS=3 regardless of intent_checker."""
    lc = PositionLifecycle()
    pos = _open_tp1_hit_long(lc)
    pos.weakness_exit_count = 3
    pre_size = pos.remaining_size

    lc.on_tick({pos.symbol: 2030.0}, intent_checker=lambda _p: True)

    assert pos.weakness_exit_count == 3
    assert pos.remaining_size == pytest.approx(pre_size), \
        "No partial_close should fire once cap is reached"


def test_weakness_cooldown_blocks_within_4_minutes():
    """If last_weakness_ts < WEAKNESS_COOLDOWN_BARS minutes ago, no new exit."""
    lc = PositionLifecycle()
    pos = _open_tp1_hit_long(lc)
    pos.weakness_exit_count = 1
    pos.last_weakness_ts = (
        datetime.now(timezone.utc) - timedelta(minutes=1)
    ).isoformat()
    pre_size = pos.remaining_size

    lc.on_tick({pos.symbol: 2030.0}, intent_checker=lambda _p: True)

    assert pos.weakness_exit_count == 1
    assert pos.remaining_size == pytest.approx(pre_size)


def test_weakness_after_cooldown_elapsed_fires_next_exit():
    """Past the 4-min cooldown, the next weak intent triggers an exit."""
    lc = PositionLifecycle()
    pos = _open_tp1_hit_long(lc)
    pos.weakness_exit_count = 1
    pos.last_weakness_ts = (
        datetime.now(timezone.utc) - timedelta(minutes=10)
    ).isoformat()
    pre_size = pos.remaining_size

    lc.on_tick({pos.symbol: 2030.0}, intent_checker=lambda _p: True)

    assert pos.weakness_exit_count == 2
    assert pos.remaining_size < pre_size


def test_weakness_skips_dust_sized_remainder():
    """If remaining_size < MIN_REMAINING_SIZE (0.01), no exit even when weak."""
    lc = PositionLifecycle()
    # Open with already-dust size; do NOT call partial_close (which would
    # shrink it further and confuse the assertion).
    pos = lc.open_position(
        "ETH/USDT", "LONG",
        entry_price=2000.0, size=0.005,
        sl=1980.0, tp1=2040.0, tp2=2080.0,
    )
    pos.tp1_hit = True
    assert pos.remaining_size < 0.01
    pre_count = pos.weakness_exit_count
    pre_size = pos.remaining_size

    lc.on_tick({pos.symbol: 2030.0}, intent_checker=lambda _p: True)

    assert pos.weakness_exit_count == pre_count
    assert pos.remaining_size == pre_size


def test_weakness_branch_skipped_pre_tp1():
    """Weakness check is gated on tp1_hit — pre-TP1 weak signals are ignored."""
    lc = PositionLifecycle()
    pos = lc.open_position(
        "ETH/USDT", "LONG",
        entry_price=2000.0, size=1.0,
        sl=1980.0, tp1=2040.0, tp2=2080.0,
    )
    assert not pos.tp1_hit
    pre_count = pos.weakness_exit_count
    pre_size = pos.remaining_size

    # Tick at a price that does NOT cross SL/TP1/TP2 → only the weakness
    # branch could mutate state, and it must be gated off.
    lc.on_tick({pos.symbol: 2010.0}, intent_checker=lambda _p: True)

    assert pos.weakness_exit_count == pre_count
    assert pos.remaining_size == pre_size
