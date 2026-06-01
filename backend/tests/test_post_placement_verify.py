from exchange import OrderManager


def _bare_mgr():
    m = OrderManager.__new__(OrderManager)
    m.on_position_change = None
    m.positions = []
    return m


def test_verify_config_defaults_present():
    m = _bare_mgr()
    m.enable_post_placement_verify = True
    m.verify_delay_sec = 2.5
    m.verify_max_attempts = 3
    m.rollback_on_sl_failure = True
    assert m.enable_post_placement_verify is True
    assert m.verify_delay_sec == 2.5
    assert m.verify_max_attempts == 3
    assert m.rollback_on_sl_failure is True


class _OrdersExchange:
    """Mirrors the real reconcile shape: fetch_open_orders(sym) -> list of
    {id}; fapiPrivateGetOpenAlgoOrders({}) -> list of {algoId}."""
    def __init__(self, open_orders, algo_orders, raise_exc=None):
        self._open = open_orders
        self._algo = algo_orders
        self._raise = raise_exc

    def fetch_open_orders(self, ccxt_sym):
        if self._raise:
            raise self._raise
        return self._open

    def fapiPrivateGetOpenAlgoOrders(self, params=None):
        return self._algo


class _OrdersClient:
    def __init__(self, exchange):
        self.exchange = exchange

    def to_ccxt_symbol(self, s):
        return s


def test_fetch_protection_order_ids_merges_open_and_algo():
    ex = _OrdersExchange(
        open_orders=[{"id": "111"}, {"id": "222"}],
        algo_orders=[{"algoId": "333"}],
    )
    m = _bare_mgr()
    m.client = _OrdersClient(ex)
    ids, ok = m._fetch_protection_order_ids("BTC/USDT")
    assert ok is True
    assert {"111", "222", "333"}.issubset(ids)


def test_fetch_protection_order_ids_soft_fails():
    ex = _OrdersExchange([], [], raise_exc=RuntimeError("api down"))
    m = _bare_mgr()
    m.client = _OrdersClient(ex)
    ids, ok = m._fetch_protection_order_ids("BTC/USDT")
    assert ok is False
    assert ids == set()


# ── Task 3: _verify_and_repair_protection ──
import exchange as exch_mod
from exchange import Position
import pandas as pd


def _verify_mgr(snapshots):
    """Manager whose _fetch_protection_order_ids returns fixed snapshots and
    whose _retry_tp_order / rollback / persist are recorded."""
    m = _bare_mgr()
    m.enable_post_placement_verify = True
    m.verify_delay_sec = 0.0          # no real sleep in tests
    m.verify_max_attempts = 2
    m.rollback_on_sl_failure = True
    m.hedge_mode = False
    m.dry_run = False

    state = {"snapshots": list(snapshots), "retries": [], "rollback": 0}

    def _snap(symbol):
        return state["snapshots"].pop(0) if state["snapshots"] else (set(), True)
    m._fetch_protection_order_ids = _snap

    def _retry(**kw):
        state["retries"].append(kw["label"])
        return "999"
    m._retry_tp_order = _retry

    def _rollback(**kw):
        state["rollback"] += 1
    m._rollback_entry_after_protection_failure = _rollback

    m._persist = lambda: None
    m.client = type("C", (), {"to_ccxt_symbol": staticmethod(lambda s: s),
                              "exchange": type("E", (), {})()})()
    m._state = state
    return m


def _vpos(sl_oid="SL1", tp1_oid="TP1", tp2_oid="TP2"):
    return Position(symbol="BTC/USDT", direction="LONG", entry=100.0, sl=95.0,
                    tp1=110.0, tp2=120.0, size=2.0,
                    order_id="E1", sl_order_id=sl_oid, tp1_order_id=tp1_oid,
                    tp2_order_id=tp2_oid,
                    opened_at=pd.Timestamp("2026-06-01T00:00:00Z").isoformat())


def test_verify_noop_when_all_orders_present():
    m = _verify_mgr([({"SL1", "TP1", "TP2"}, True)])
    pos = _vpos()
    m.positions = [pos]
    result = m._verify_and_repair_protection(pos)
    assert result["sl_ok"] is True
    assert m._state["retries"] == []      # nothing re-placed
    assert m._state["rollback"] == 0


def test_verify_repairs_missing_tp_then_keeps_position():
    # attempt 1: TP1 missing → repair; attempt 2: all present
    m = _verify_mgr([({"SL1", "TP2"}, True), ({"SL1", "TP1", "TP2"}, True)])
    pos = _vpos()
    m.positions = [pos]
    m._verify_and_repair_protection(pos)
    assert "TP1" in m._state["retries"]
    assert m._state["rollback"] == 0
    assert pos in m.positions             # position kept


def test_verify_rolls_back_when_sl_never_confirmed():
    m = _verify_mgr([({"TP1", "TP2"}, True), ({"TP1", "TP2"}, True)])
    pos = _vpos()
    m.positions = [pos]

    def _retry(**kw):
        m._state["retries"].append(kw["label"])
        return "" if kw["label"] == "SL" else "999"   # SL re-place fails
    m._retry_tp_order = _retry

    result = m._verify_and_repair_protection(pos)
    assert m._state["rollback"] == 1
    assert pos not in m.positions         # local tracking removed
    assert result["sl_ok"] is False


def test_verify_tolerates_permanent_unreachable_tp():
    m = _verify_mgr([({"SL1", "TP2"}, True), ({"SL1", "TP2"}, True)])
    pos = _vpos()
    m.positions = [pos]

    def _retry(**kw):
        m._state["retries"].append(kw["label"])
        return exch_mod._TP_UNREACHABLE_SENTINEL if kw["label"] == "TP1" else "999"
    m._retry_tp_order = _retry

    m._verify_and_repair_protection(pos)
    assert m._state["rollback"] == 0
    assert pos in m.positions
    assert pos.tp1_order_id == ""         # blanked → reconcile keeps retrying


def test_verify_noop_when_disabled():
    m = _verify_mgr([({"SL1", "TP1", "TP2"}, True)])
    m.enable_post_placement_verify = False
    pos = _vpos()
    m.positions = [pos]
    result = m._verify_and_repair_protection(pos)
    assert result["skipped"] is True
    assert m._state["retries"] == []
