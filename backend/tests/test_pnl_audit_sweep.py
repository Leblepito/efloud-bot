from engine.journal import TradeSnapshot


def _snap(**over):
    base = dict(
        trade_id="t1", symbol="BTC/USDT", direction="LONG", timeframe="",
        entry_timestamp="2026-06-01T00:00:00Z", entry_price=100.0,
        sl_initial=95.0, tp1_initial=110.0, tp2_initial=120.0,
        position_size=1.0, htf_bias="", intent_score_entry=0,
        intent_label_entry="", confluence_score=0,
    )
    base.update(over)
    return TradeSnapshot(**base)


def test_tradesnapshot_has_pnl_source_field():
    snap = _snap()
    assert hasattr(snap, "pnl_source")
    assert snap.pnl_source == "estimated"
    assert hasattr(snap, "realized_pnl_exchange")


from exchange import OrderManager, Position
import pandas as pd


class _AuditClient:
    def __init__(self, net):
        self._net = net

    def fetch_realized_pnl(self, symbol, since_ms, until_ms=None):
        return {"ok": True, "net": self._net, "realized_pnl": self._net,
                "commission": 0.0, "funding": 0.0}


def _audit_mgr(client):
    m = OrderManager.__new__(OrderManager)
    m.client = client
    m.closed_positions = []
    m.trade_journal = None
    m.on_position_change = None
    return m


def _recent_pos(**over):
    now = pd.Timestamp.now(tz="UTC")
    base = dict(symbol="SOL/USDT", direction="LONG", entry=82.0, sl=80.0,
                tp1=85.0, tp2=88.0, size=1.0,
                opened_at=(now - pd.Timedelta(hours=2)).isoformat(),
                closed_at=(now - pd.Timedelta(hours=1)).isoformat())
    base.update(over)
    return Position(**base)


def test_audit_upgrades_estimated_closed_positions():
    m = _audit_mgr(_AuditClient(net=-2.5))
    pos = _recent_pos(pnl_usdt=3.0, pnl_source="estimated")
    m.closed_positions.append(pos)

    corrected = m.audit_realized_pnl(window_hours=24)

    assert corrected == 1
    assert pos.pnl_source == "exchange"
    assert pos.pnl_usdt == -2.5


def test_audit_skips_already_reconciled():
    m = _audit_mgr(_AuditClient(net=99.0))
    pos = _recent_pos(pnl_usdt=5.0, pnl_source="exchange")
    m.closed_positions.append(pos)

    corrected = m.audit_realized_pnl(window_hours=24)

    assert corrected == 0
    assert pos.pnl_usdt == 5.0   # untouched


def test_reconcile_runs_audit_every_n_cycles(monkeypatch):
    m = _audit_mgr(_AuditClient(net=0.0))
    m.enable_pnl_audit = True
    m.pnl_audit_every_cycles = 3
    m._pnl_audit_cycle = 0

    calls = {"n": 0}
    monkeypatch.setattr(m, "audit_realized_pnl",
                        lambda **k: calls.__setitem__("n", calls["n"] + 1) or 0)

    for _ in range(7):
        m._maybe_run_pnl_audit()

    assert calls["n"] == 2   # cycles 3 and 6


def test_audit_disabled_never_runs():
    m = _audit_mgr(_AuditClient(net=0.0))
    m.enable_pnl_audit = False
    m.pnl_audit_every_cycles = 1
    m._pnl_audit_cycle = 0
    calls = {"n": 0}
    m.audit_realized_pnl = lambda **k: calls.__setitem__("n", calls["n"] + 1) or 0
    for _ in range(5):
        m._maybe_run_pnl_audit()
    assert calls["n"] == 0
