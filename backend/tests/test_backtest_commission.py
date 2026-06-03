"""S2: wire taker commission into the backtest cost model.

The backtest applied slippage but NO commission, so net returns / profit factor
were overstated (on a 1000+-trade strategy the ~0.08% round-trip taker drag is
material). This makes per-trade pnl AND the final balance net of commission, so
PF / win_rate / total_return all reflect real cost — a prerequisite for a
trustworthy net-PF (e.g. the S1 conf-50-vs-80 comparison).

Funding is intentionally NOT wired here: the backtest's opened_at/closed_at are
wall-clock (lifecycle uses datetime.utcnow, microseconds apart for the whole
run), so per-8h holding duration is uncomputable from trade records, and the
OHLCV cache carries no funding-rate series. Funding needs a separate
sim-time-tracking + funding-data follow-up (S2b).
"""
import pytest

from backtest.metrics import apply_commission_costs, serialize_trade
from engine.lifecycle import Entry, Exit, Position


def test_commission_reduces_each_trade_pnl_and_final_balance():
    trades = [
        {"pnl": 100.0, "size": 1.0, "entry": 100.0, "exit": 110.0},
        {"pnl": -50.0, "size": 2.0, "entry": 50.0, "exit": 48.0},
    ]
    net, bal, total = apply_commission_costs(trades, balance=2000.0, commission_pct=0.04)
    c0 = 0.0004 * 1.0 * (100.0 + 110.0)   # round-trip: entry leg + exit leg
    c1 = 0.0004 * 2.0 * (50.0 + 48.0)
    assert net[0]["pnl"] == pytest.approx(100.0 - c0)
    assert net[1]["pnl"] == pytest.approx(-50.0 - c1)
    assert net[0]["commission"] == pytest.approx(c0)
    assert total == pytest.approx(c0 + c1)
    assert bal == pytest.approx(2000.0 - total)


def test_zero_commission_is_noop():
    trades = [{"pnl": 100.0, "size": 1.0, "entry": 100.0, "exit": 110.0}]
    net, bal, total = apply_commission_costs(trades, 2000.0, 0.0)
    assert total == 0.0
    assert bal == 2000.0
    assert net[0]["pnl"] == 100.0


def test_serialize_trade_includes_size():
    p = Position(
        id="t1", symbol="BTC/USDT", direction="LONG",
        entries=[Entry(id="e1", price=100.0, size=2.0, timestamp="t", reason="initial")],
        exits=[Exit(id="x1", price=110.0, size=2.0, timestamp="t", reason="TP2", pnl=20.0)],
        sl=95.0, tp1=110.0, tp2=120.0, initial_sl=95.0,
        opened_at="t", closed_at="t",
    )
    d = serialize_trade(p)
    assert d["size"] == pytest.approx(2.0), "serialize_trade must expose size for commission"
