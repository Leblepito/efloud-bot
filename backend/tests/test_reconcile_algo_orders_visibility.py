"""Regression: ``OrderManager.reconcile`` queries BOTH normal + algo open orders.

Bug history (2026-05-09 LTC/ADA reconcile incident): bot moved SL to break-even
on phantom TP1 hits because ccxt ``fetch_open_orders`` does NOT include
conditional algo orders (server-side STOP_MARKET / TAKE_PROFIT_MARKET). Every
reconcile cycle declared TP1 filled because the algo TP1 order id was "missing"
from the regular orders list.

Fix in ``exchange/__init__.py``: also call
``self.client.exchange.fapiPrivateGetOpenAlgoOrders({})`` and merge ``algoId``
values into ``bn_order_ids`` so the lookup set covers both endpoints.

These tests pin:
  * Both endpoints are queried each cycle (no skip when one is empty).
  * An algo-fetch failure is downgraded to a warning, not propagated.
  * dry_run mode short-circuits before any live API calls.
"""
from unittest.mock import MagicMock

import pytest

from exchange import BinanceClient, OrderManager


@pytest.fixture
def mock_client():
    client = MagicMock(spec=BinanceClient)
    client.exchange = MagicMock()
    client.market_type = "futures"
    client.testnet = True
    client.to_ccxt_symbol.side_effect = lambda s: (
        s if ":" in s or client.market_type != "futures" else f"{s}:USDT"
    )
    client.get_open_positions.return_value = []  # no live positions to iterate
    return client


def test_reconcile_calls_both_normal_and_algo_endpoints(mock_client, tmp_path):
    """Both endpoints MUST be queried each reconcile cycle."""
    mock_client.exchange.fetch_open_orders.return_value = []
    mock_client.exchange.fapiPrivateGetOpenAlgoOrders.return_value = []

    mgr = OrderManager(mock_client, dry_run=False, state_dir=str(tmp_path))
    mgr.reconcile()

    mock_client.exchange.fetch_open_orders.assert_called_once()
    mock_client.exchange.fapiPrivateGetOpenAlgoOrders.assert_called_once()


def test_reconcile_algo_fetch_failure_is_warned_not_raised(mock_client, tmp_path):
    """If algo fetch raises, reconcile completes — only a warning is logged.

    Without this, a transient 5xx on the algo endpoint would crash the
    reconcile cycle and re-trip the 2026-05-08 stacking bug.
    """
    mock_client.exchange.fetch_open_orders.return_value = [{"id": "STD-1"}]
    mock_client.exchange.fapiPrivateGetOpenAlgoOrders.side_effect = Exception(
        "/fapi/v1/algo/open-orders 401"
    )

    mgr = OrderManager(mock_client, dry_run=False, state_dir=str(tmp_path))
    closed = mgr.reconcile()

    assert closed == []
    mock_client.exchange.fetch_open_orders.assert_called_once()
    mock_client.exchange.fapiPrivateGetOpenAlgoOrders.assert_called_once()


def test_reconcile_dry_run_skips_live_api(mock_client, tmp_path):
    """Dry-run skips all fetches — no live API hits in paper mode."""
    mgr = OrderManager(mock_client, dry_run=True, state_dir=str(tmp_path))
    closed = mgr.reconcile()

    assert closed == []
    mock_client.get_open_positions.assert_not_called()
    mock_client.exchange.fetch_open_orders.assert_not_called()
    mock_client.exchange.fapiPrivateGetOpenAlgoOrders.assert_not_called()
