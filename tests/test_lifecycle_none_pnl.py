"""Tests for engine/lifecycle.py realized_pnl None-skip (bug-hunt #14).

PR #168's breaker.py fix didn't catch the actual crash site. The full
traceback (caught via PR #169's exc_info=True) pointed at:
  engine/safe_orchestrator.py:944 -> breaker.record_trade(p.realized_pnl)
  engine/lifecycle.py:163 in realized_pnl: return sum(e.pnl for e in self.exits)

Repro: an exit is recorded with pnl=None (edge case from PR #164/#167 LOW
batch remaining-inventory cost-basis math when avg_entry_price has no
defined entries). sum() raised TypeError on int + None. Cycle crashed.

Run: python -m pytest tests/test_lifecycle_none_pnl.py -v
"""

import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from engine.lifecycle import PositionLifecycle, Exit, ExitReason, Position  # noqa: E402


def _make_position_with_exits(exits):
    """Build a Position with the given exit records."""
    pos = Position(
        id="test-001",
        symbol="BTC/USDT",
        direction="LONG",
        entries=[],
        exits=exits,
        opened_at=datetime.utcnow().isoformat(),
        sl=0.0,
        tp1=0.0,
        tp2=0.0,
    )
    return pos


def test_realized_pnl_skips_none_pnl():
    """Bug-hunt #14 regression: exit with pnl=None must not crash."""
    exits = [
        Exit("e1", price=100.0, size=0.1, timestamp="2026-01-01T00:00:00",
             reason="MANUAL", pnl=10.0),
        Exit("e2", price=110.0, size=0.1, timestamp="2026-01-01T01:00:00",
             reason="MANUAL", pnl=None),  # in-flight, no realized PnL
        Exit("e3", price=120.0, size=0.1, timestamp="2026-01-01T02:00:00",
             reason="MANUAL", pnl=5.0),
    ]
    pos = _make_position_with_exits(exits)
    # None skipped: 10.0 + 5.0 = 15.0
    assert pos.realized_pnl == 15.0


def test_realized_pnl_all_none_returns_zero():
    """All-None exits -> 0.0, no crash."""
    exits = [
        Exit("e1", price=100.0, size=0.1, timestamp="2026-01-01T00:00:00",
             reason="MANUAL", pnl=None),
        Exit("e2", price=110.0, size=0.1, timestamp="2026-01-01T01:00:00",
             reason="MANUAL", pnl=None),
    ]
    pos = _make_position_with_exits(exits)
    assert pos.realized_pnl == 0.0


def test_realized_pnl_no_exits_returns_zero():
    """No exits -> 0.0."""
    pos = _make_position_with_exits([])
    assert pos.realized_pnl == 0.0


def test_realized_pnl_legitimate_losses_sum_correctly():
    """Sanity: realized losses still sum correctly."""
    exits = [
        Exit("e1", price=100.0, size=0.1, timestamp="2026-01-01T00:00:00",
             reason="SL", pnl=-50.0),
        Exit("e2", price=90.0, size=0.1, timestamp="2026-01-01T01:00:00",
             reason="MANUAL", pnl=-30.0),
    ]
    pos = _make_position_with_exits(exits)
    assert pos.realized_pnl == -80.0


def test_old_buggy_behavior_would_crash():
    """Document the original bug for posterity — confirms the fix matters."""
    exits = [
        Exit("e1", price=100.0, size=0.1, timestamp="2026-01-01T00:00:00",
             reason="MANUAL", pnl=10.0),
        Exit("e2", price=110.0, size=0.1, timestamp="2026-01-01T01:00:00",
             reason="MANUAL", pnl=None),
    ]
    pos = _make_position_with_exits(exits)
    # If the fix is reverted, this should raise TypeError. With the fix,
    # it returns 10.0.
    try:
        result = pos.realized_pnl
        assert result == 10.0
    except TypeError as e:
        pytest.fail(f"realized_pnl crashed on None pnl (bug-hunt #14 regression): {e}")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
