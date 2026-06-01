from exchange import BinanceClient


class _FakeExchange:
    def __init__(self, rows, raise_exc=None):
        self._rows = rows
        self._raise = raise_exc
        self.calls = []

    def market(self, ccxt_sym):
        return {"id": ccxt_sym.split(":")[0].replace("/", "")}

    def fapiPrivateGetIncome(self, params):
        self.calls.append(params)
        if self._raise:
            raise self._raise
        # Filter the shared row set by the requested incomeType so summing is real.
        want = params.get("incomeType")
        return [r for r in self._rows if r.get("incomeType") == want]


def _client_with(rows, raise_exc=None):
    c = BinanceClient.__new__(BinanceClient)   # bypass __init__ (no network)
    c.exchange = _FakeExchange(rows, raise_exc)
    c.market_type = "futures"
    return c


def test_fetch_realized_pnl_sums_by_type():
    rows = [
        {"symbol": "BTCUSDT", "incomeType": "REALIZED_PNL", "income": "10.0", "time": 1},
        {"symbol": "BTCUSDT", "incomeType": "COMMISSION",   "income": "-0.4", "time": 2},
        {"symbol": "BTCUSDT", "incomeType": "FUNDING_FEE",  "income": "-0.1", "time": 3},
    ]
    c = _client_with(rows)
    out = c.fetch_realized_pnl("BTC/USDT", since_ms=0)
    assert out["realized_pnl"] == 10.0
    assert out["commission"] == -0.4
    assert out["funding"] == -0.1
    assert round(out["net"], 6) == 9.5
    assert out["ok"] is True


def test_fetch_realized_pnl_soft_fails_to_zeros():
    c = _client_with([], raise_exc=RuntimeError("api down"))
    out = c.fetch_realized_pnl("BTC/USDT", since_ms=0)
    assert out["ok"] is False
    assert out["net"] == 0.0
