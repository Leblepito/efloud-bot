"""Tests for engine/lifecycle.py None-safety sweep (bug-hunt #15).

PR #170 fixed realized_pnl. PR #171 closes the same None-arithmetic pattern
across the rest of the lifecycle properties / methods: total_size_entered,
total_size_exited, avg_entry_price (e.price * e.size), unrealized_pnl
(current_price=None from stale price_map).

Run: python -m pytest tests/test_lifecycle_none_safety_sweep.py -v
"""

import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from engine.lifecycle import PositionLifecycle, Entry, Exit, Position  # noqa: E402


def _make_position_with_entries(entries, exits=None, direction="LONG"):
    """Build a Position with the given entry / exit records."""
    return Position(
        id="test-001",
        symbol="BTC/USDT",
        direction=direction,
        entries=entries,
        exits=exits or [],
        opened_at=datetime.now(timezone.utc).replace(tzinfo=None).isoformat(),
        sl=0.0,
        tp1=0.0,
        tp2=0.0,
    )


# ── total_size_entered ────────────────────────────────────────────────────

def test_total_size_entered_skips_none_size():
    entries = [
        Entry("e1", price=100.0, size=0.1, timestamp="2026-01-01T00:00:00"),
        Entry("e2", price=110.0, size=None, timestamp="2026-01-01T01:00:00"),
        Entry("e3", price=120.0, size=0.1, timestamp="2026-01-01T02:00:00"),
    ]
    pos = _make_position_with_entries(entries)
    # None skipped: 0.1 + 0.1 = 0.2
    assert pos.total_size_entered == pytest.approx(0.2)


def test_total_size_entered_all_none_returns_zero():
    entries = [
        Entry("e1", price=100.0, size=None, timestamp="2026-01-01T00:00:00"),
        Entry("e2", price=110.0, size=None, timestamp="2026-01-01T01:00:00"),
    ]
    pos = _make_position_with_entries(entries)
    assert pos.total_size_entered == 0.0


def test_total_size_entered_no_entries_returns_zero():
    pos = _make_position_with_entries([])
    assert pos.total_size_entered == 0.0


# ── total_size_exited ─────────────────────────────────────────────────────

def test_total_size_exited_skips_none_size():
    exits = [
        Exit("x1", price=100.0, size=0.1, timestamp="2026-01-01T00:00:00",
             reason="MANUAL", pnl=10.0),
        Exit("x2", price=110.0, size=None, timestamp="2026-01-01T01:00:00",
             reason="MANUAL", pnl=None),
        Exit("x3", price=120.0, size=0.1, timestamp="2026-01-01T02:00:00",
             reason="MANUAL", pnl=5.0),
    ]
    pos = _make_position_with_entries([], exits=exits)
    assert pos.total_size_exited == pytest.approx(0.2)


# ── avg_entry_price ───────────────────────────────────────────────────────

def test_avg_entry_price_skips_none_price_or_size():
    """e.price * e.size with either None must not crash."""
    entries = [
        Entry("e1", price=100.0, size=0.1, timestamp="2026-01-01T00:00:00"),
        Entry("e2", price=None, size=0.1, timestamp="2026-01-01T01:00:00"),  # None price
        Entry("e3", price=120.0, size=None, timestamp="2026-01-01T02:00:00"),  # None size
    ]
    pos = _make_position_with_entries(entries)
    # Only e1 contributes: 100 * 0.1 = 10 / 0.1 = 100
    assert pos.avg_entry_price == pytest.approx(100.0)


def test_avg_entry_price_no_valid_entries_returns_zero():
    entries = [
        Entry("e1", price=None, size=0.1, timestamp="2026-01-01T00:00:00"),
        Entry("e2", price=120.0, size=None, timestamp="2026-01-01T01:00:00"),
    ]
    pos = _make_position_with_entries(entries)
    # No valid entries -> total_size = 0 -> fallback 0
    assert pos.avg_entry_price == 0.0


def test_avg_entry_price_legitimate_average():
    """Sanity: weighted average still works for valid entries."""
    entries = [
        Entry("e1", price=100.0, size=0.5, timestamp="2026-01-01T00:00:00"),
        Entry("e2", price=200.0, size=0.5, timestamp="2026-01-01T01:00:00"),
    ]
    pos = _make_position_with_entries(entries)
    # (100 * 0.5 + 200 * 0.5) / 1.0 = 150
    assert pos.avg_entry_price == pytest.approx(150.0)


# ── unrealized_pnl ────────────────────────────────────────────────────────

def test_unrealized_pnl_none_current_price_returns_zero():
    """price_map can carry None for symbols with stale WS snapshot."""
    entries = [
        Entry("e1", price=100.0, size=0.1, timestamp="2026-01-01T00:00:00"),
    ]
    pos = _make_position_with_entries(entries, direction="LONG")
    # pos is_open = True (has entries, no full exits), but current_price is None
    # Without the fix: (None - 100) * 0.1 raises TypeError
    # With the fix: returns 0
    assert pos.unrealized_pnl(None) == 0.0


def test_unrealized_pnl_normal_long():
    """Sanity: long position with valid price computes correct PnL."""
    entries = [
        Entry("e1", price=100.0, size=0.1, timestamp="2026-01-01T00:00:00"),
    ]
    pos = _make_position_with_entries(entries, direction="LONG")
    # (110 - 100) * 0.1 = 1.0
    assert pos.unrealized_pnl(110.0) == pytest.approx(1.0)


def test_unrealized_pnl_normal_short():
    """Sanity: short position with valid price computes correct PnL."""
    entries = [
        Entry("e1", price=100.0, size=0.1, timestamp="2026-01-01T00:00:00"),
    ]
    pos = _make_position_with_entries(entries, direction="SHORT")
    # (100 - 90) * 0.1 = 1.0
    assert pos.unrealized_pnl(90.0) == pytest.approx(1.0)


def test_unrealized_pnl_closed_position_returns_zero():
    """Closed positions skip the math entirely."""
    entries = [
        Entry("e1", price=100.0, size=0.1, timestamp="2026-01-01T00:00:00"),
    ]
    exits = [
        Exit("x1", price=110.0, size=0.1, timestamp="2026-01-01T01:00:00",
             reason="MANUAL", pnl=1.0),
    ]
    pos = _make_position_with_entries(entries, exits=exits)
    # is_open = False
    assert pos.unrealized_pnl(200.0) == 0.0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
