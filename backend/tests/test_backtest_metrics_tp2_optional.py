"""backtest.metrics.serialize_trade handles tp2=None (PR #S5.5 task 4).

`float(p.tp2)` with p.tp2=None raises TypeError.
"""
from __future__ import annotations

from engine.lifecycle import Position, Entry, Exit
from backtest.metrics import serialize_trade


def _make_closed_position(tp2):
    p = Position(
        id="x", symbol="ETH/USDT", direction="LONG",
        entries=[Entry(id="e1", price=100.0, size=1.0, timestamp="2025-01-01T00:00:00")],
        exits=[Exit(id="x1", price=110.0, size=1.0, timestamp="2025-01-01T01:00:00",
                    reason="TP1", pnl=10.0)],
        sl=95.0, tp1=110.0, tp2=tp2, initial_sl=95.0,
        opened_at="2025-01-01T00:00:00", closed_at="2025-01-01T01:00:00",
    )
    return p


def test_serialize_trade_handles_tp2_none():
    p = _make_closed_position(tp2=None)
    d = serialize_trade(p)
    assert d["tp2"] is None
    assert d["tp1"] == 110.0
    assert d["sl"] == 95.0


def test_serialize_trade_two_target_unchanged():
    p = _make_closed_position(tp2=120.0)
    d = serialize_trade(p)
    assert d["tp2"] == 120.0
