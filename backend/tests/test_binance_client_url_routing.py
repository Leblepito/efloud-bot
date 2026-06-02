"""Regression: BinanceClient(market_type='futures') must produce a CCXT
exchange whose fetch_open_orders() hits fapi.binance.com (futures), not
api.binance.com (spot). Tests by intercepting the HTTP call before it
goes out — no live exchange, no auth, no markets reload over the network.

H1: the shared_markets fixture previously called boot.load_markets(), a LIVE
api.binance.com/exchangeInfo call → HTTP 451 on GitHub's US runners (the test
was --ignore'd in CI). It now loads vendored markets metadata from
backend/tests/fixtures/binance_markets.json (FIL/USDT spot + FIL/USDT:USDT
linear) — fully offline / hermetic.
"""
import json
from pathlib import Path

import ccxt
import pytest

from exchange import BinanceClient

_MARKETS_FIXTURE = Path(__file__).parent / "fixtures" / "binance_markets.json"


@pytest.fixture(scope="module")
def shared_markets():
    """Vendored Binance markets metadata — NO network (see H1)."""
    data = json.loads(_MARKETS_FIXTURE.read_text(encoding="utf-8"))
    boot = ccxt.binance({"options": {"defaultType": "spot"}})
    boot.markets = data["markets"]
    boot.markets_by_id = data["markets_by_id"]
    boot.symbols = data["symbols"]
    boot.ids = data["ids"]
    return boot


def _capture_fetch_open_orders_url(client: BinanceClient, symbol=None) -> str:
    """Run fetch_open_orders against the BinanceClient's exchange and return the
    URL CCXT was about to hit. Network is intercepted before any real call."""
    ex = client.exchange
    captured = []

    def fake_fetch(url, *a, **kw):
        captured.append(url)
        raise RuntimeError("intercepted")

    ex.fetch = fake_fetch
    try:
        if symbol:
            ex.fetch_open_orders(symbol)
        else:
            ex.fetch_open_orders()
    except RuntimeError as e:
        if "intercepted" not in str(e):
            raise
    return captured[-1] if captured else ""


def _client_with_markets(market_type: str, shared_markets) -> BinanceClient:
    client = BinanceClient(
        api_key="dummy", api_secret="dummy",
        testnet=False, market_type=market_type,
    )
    # Inject pre-loaded markets so load_markets() does not hit the network
    client.exchange.markets = shared_markets.markets
    client.exchange.markets_by_id = shared_markets.markets_by_id
    client.exchange.symbols = shared_markets.symbols
    client.exchange.ids = shared_markets.ids
    return client


def test_futures_client_routes_no_symbol_to_fapi(shared_markets):
    client = _client_with_markets("futures", shared_markets)
    url = _capture_fetch_open_orders_url(client)
    assert "fapi.binance.com/fapi/v1/openOrders" in url, (
        f"Expected futures URL but got: {url}\n"
        "Regression: defaultType normalization broken — routing to spot."
    )
    assert "/api/v3/openOrders" not in url


def test_futures_client_routes_with_slash_symbol_to_fapi(shared_markets):
    """Even with bot's slash-only symbol form, routing must go to fapi.

    With buggy defaultType='futures', symbol='FIL/USDT' (slash-only) loads as
    spot market and hits /api/v3/openOrders. The fix forces fapi via the
    canonical 'future' string."""
    client = _client_with_markets("futures", shared_markets)
    url = _capture_fetch_open_orders_url(client, symbol="FIL/USDT:USDT")
    assert "fapi.binance.com/fapi/v1/openOrders" in url
    assert "symbol=FILUSDT" in url
