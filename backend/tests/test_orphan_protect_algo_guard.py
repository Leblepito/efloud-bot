"""Orphan protection must SKIP when SL coverage can't be assessed (bug-hunt #9).

When the regular or algo open-orders fetch fails, the live id list is empty/
incomplete, so OrphanProtector.analyze_coverage would flag every orphan as
'missing_sl' and (under place_missing_sl mode + require_tp_present=false, the
prod config) place a DUPLICATE close-position STOP_MARKET SL on a position that
may already be protected by an algo-SL which merely failed to fetch. Gate
orphan-protect on (orders_fetch_ok and algo_fetch_ok) — mirroring the sibling
_repair path that is already guarded on algo_fetch_ok.
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
    return client


def _orphan_mgr(mock_client):
    """OrderManager with an orphan_protector and one exchange-only (orphan) position."""
    mgr = OrderManager(mock_client, dry_run=False)
    mgr.orphan_protector = MagicMock()
    mgr.orphan_protector.protect_cycle.return_value = []
    mgr.positions = []  # no local positions → the exchange position is an orphan
    mock_client.get_open_positions.return_value = [
        {"symbol": "BTC/USDT:USDT", "contracts": 0.01, "side": "short",
         "entryPrice": 60000.0, "unrealizedPnl": 0.0},
    ]
    return mgr


def test_orphan_protect_skipped_when_algo_fetch_fails(mock_client):
    mgr = _orphan_mgr(mock_client)
    mock_client.exchange.fetch_open_orders.return_value = []                       # orders OK
    mock_client.exchange.fapiPrivateGetOpenAlgoOrders.side_effect = Exception("algo 401")  # algo FAILS
    mgr.reconcile()
    # Coverage unknowable → must NOT run orphan protection (no duplicate SL).
    mgr.orphan_protector.protect_cycle.assert_not_called()


def test_orphan_protect_skipped_when_orders_fetch_fails(mock_client):
    mgr = _orphan_mgr(mock_client)
    mock_client.exchange.fetch_open_orders.side_effect = Exception("orders 500")   # orders FAIL
    mgr.reconcile()
    mgr.orphan_protector.protect_cycle.assert_not_called()


def test_orphan_protect_runs_when_both_fetches_ok(mock_client):
    mgr = _orphan_mgr(mock_client)
    mock_client.exchange.fetch_open_orders.return_value = []
    mock_client.exchange.fapiPrivateGetOpenAlgoOrders.return_value = []            # both OK
    mgr.reconcile()
    # Coverage assessable → orphan protection runs as normal.
    mgr.orphan_protector.protect_cycle.assert_called_once()
