from exchange import Position, OrderManager
import pandas as pd


def test_position_has_reconciliation_fields_with_defaults():
    pos = Position(
        symbol="BTC/USDT", direction="LONG", entry=100.0, sl=95.0,
        tp1=110.0, tp2=120.0, size=1.0,
    )
    assert pos.realized_pnl_exchange == 0.0
    assert pos.commission_paid == 0.0
    assert pos.funding_paid == 0.0
    assert pos.pnl_source == "estimated"


class _FakeClient:
    def __init__(self, net=None, ok=True):
        self._net = net
        self._ok = ok
        self.called_with = None

    def fetch_realized_pnl(self, symbol, since_ms, until_ms=None):
        self.called_with = (symbol, since_ms)
        if self._net is None:
            return {"ok": False, "net": 0.0, "realized_pnl": 0.0,
                    "commission": 0.0, "funding": 0.0}
        return {"ok": self._ok, "net": self._net, "realized_pnl": self._net + 0.5,
                "commission": -0.4, "funding": -0.1}


def _mgr(client):
    m = OrderManager.__new__(OrderManager)
    m.client = client
    m.closed_positions = []
    m.trade_journal = None
    m.on_position_change = None
    return m


def _pos():
    return Position(symbol="BTC/USDT", direction="LONG", entry=100.0, sl=95.0,
                    tp1=110.0, tp2=120.0, size=1.0,
                    opened_at=pd.Timestamp("2026-06-01T00:00:00Z").isoformat())


def test_record_close_uses_exchange_net_when_available():
    m = _mgr(_FakeClient(net=8.7, ok=True))
    pos = _pos()
    m._record_close(pos, exit_price=109.0, reason="TP1")
    assert pos.pnl_source == "exchange"
    assert pos.pnl_usdt == 8.7
    assert pos.realized_pnl_exchange == 9.2   # net + 0.5 per fake


def test_record_close_falls_back_to_estimate_on_soft_fail():
    m = _mgr(_FakeClient(net=None))   # ok=False
    pos = _pos()
    m._record_close(pos, exit_price=109.0, reason="TP1")
    assert pos.pnl_source == "estimated"
    # gross estimate = (109 - 100) * 1.0 = 9.0
    assert pos.pnl_usdt == 9.0
