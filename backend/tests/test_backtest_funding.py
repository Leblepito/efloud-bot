"""S2b: wire funding into the backtest using sim-time holding duration.

S2 (#130) deferred funding because the backtest could not derive per-8h holding
duration (lifecycle opened_at/closed_at are wall-clock) and the cache has no
funding-rate series. S2b adds sim-time open/close tracking in the engine loop
and applies funding from it.

Funding here is a SYMMETRIC AVERAGE DRAG (magnitude): cost = rate × notional ×
completed-8h-periods, subtracted from pnl. A constant rate cannot model real
funding sign flips; a per-symbol funding-rate series is a further follow-up
(S2c). Default rate 0 → no change (backward-compatible).
"""
import pytest

from backtest.metrics import apply_funding_costs, serialize_trade
from engine.lifecycle import Entry, Exit, Position


def test_funding_subtracts_per_completed_8h_period():
    trades = [{"id": "a", "pnl": 100.0}, {"id": "b", "pnl": 50.0}]
    holding_hours = {"a": 17.0, "b": 4.0}        # a → 2 completed 8h periods, b → 0
    notional = {"a": 1000.0, "b": 500.0}
    net, bal, total = apply_funding_costs(trades, 2000.0, 0.01, holding_hours, notional)
    a_cost = 0.0001 * 1000.0 * 2                  # rate 0.01% × $1000 × 2 periods
    assert net[0]["pnl"] == pytest.approx(100.0 - a_cost)
    assert net[1]["pnl"] == 50.0                  # < 8h held → no funding event
    assert net[0]["funding"] == pytest.approx(a_cost)
    assert total == pytest.approx(a_cost)
    assert bal == pytest.approx(2000.0 - a_cost)


def test_zero_funding_is_noop():
    trades = [{"id": "a", "pnl": 100.0}]
    net, bal, total = apply_funding_costs(trades, 2000.0, 0.0, {"a": 100.0}, {"a": 1000.0})
    assert total == 0.0
    assert bal == 2000.0
    assert net[0]["pnl"] == 100.0


def test_serialize_trade_includes_id():
    p = Position(
        id="trade-xyz", symbol="BTC/USDT", direction="LONG",
        entries=[Entry(id="e1", price=100.0, size=2.0, timestamp="t", reason="initial")],
        exits=[Exit(id="x1", price=110.0, size=2.0, timestamp="t", reason="TP2", pnl=20.0)],
        sl=95.0, tp1=110.0, tp2=120.0, initial_sl=95.0, opened_at="t", closed_at="t",
    )
    assert serialize_trade(p)["id"] == "trade-xyz"
