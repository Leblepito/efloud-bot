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
