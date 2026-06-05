"""avg_entry_price must reflect REMAINING inventory cost-basis (bug-hunt #7).

Pre-fix: avg_entry_price = sum(price*size for ALL entries) / total_size_entered.
After a partial (TP1) exit followed by a pyramid add, it never removed the cost
basis of the already-exited size, so the average (and the realized PnL computed
from it at the final close, fed to the circuit breaker) was wrong.

Fix: average-cost replay — entries/exits in timestamp order, exits removed at the
running average. For the common case (no add after an exit) this equals the simple
all-entries average, so behavior is unchanged there.
"""
import pytest

from engine.lifecycle import Entry, Exit, Position


def _entry(price, size, ts):
    return Entry(id="e", price=price, size=size, timestamp=ts, reason="x")


def _exit(price, size, ts, pnl):
    return Exit(id="x", price=price, size=size, timestamp=ts, reason="TP1", pnl=pnl)


def test_avg_remaining_inventory_after_pyramid_past_tp1():
    pos = Position(id="p", symbol="BTC/USDT", direction="LONG")
    pos.entries.append(_entry(100.0, 1.0, "2026-06-05T00:00:00"))     # initial
    pos.exits.append(_exit(110.0, 0.5, "2026-06-05T01:00:00", pnl=5.0))  # TP1 partial (avg was 100)
    pos.entries.append(_entry(90.0, 0.5, "2026-06-05T02:00:00"))      # pyramid add AFTER the exit
    # Remaining held = 0.5 @100 + 0.5 @90 → avg 95.0, NOT the all-entries 96.67.
    assert pos.avg_entry_price == pytest.approx(95.0)
    assert pos.remaining_size == pytest.approx(1.0)


def test_avg_unchanged_when_add_before_any_exit():
    pos = Position(id="p", symbol="BTC/USDT", direction="LONG")
    pos.entries.append(_entry(100.0, 1.0, "t0"))
    pos.entries.append(_entry(90.0, 0.5, "t1"))   # add BEFORE any exit
    assert pos.avg_entry_price == pytest.approx((100 * 1.0 + 90 * 0.5) / 1.5)  # 96.666…


def test_avg_unchanged_after_partial_with_no_later_add():
    pos = Position(id="p", symbol="BTC/USDT", direction="LONG")
    pos.entries.append(_entry(100.0, 1.0, "t0"))
    pos.exits.append(_exit(110.0, 0.5, "t1", pnl=5.0))   # partial, no add after
    assert pos.avg_entry_price == pytest.approx(100.0)


def test_avg_single_entry_unchanged():
    pos = Position(id="p", symbol="BTC/USDT", direction="LONG")
    pos.entries.append(_entry(100.0, 2.0, "t0"))
    assert pos.avg_entry_price == pytest.approx(100.0)
