"""Unit tests for OrderManager._cancel_position_siblings — orphan order cleanup helper."""
from unittest.mock import MagicMock
import ccxt
import pytest

from exchange import BinanceClient, OrderManager, Position


@pytest.fixture
def mock_client():
    """Mock BinanceClient with stubbed exchange + helpers.

    Mirrors test_order_manager_v2.py fixture to keep test infrastructure consistent.
    """
    client = MagicMock(spec=BinanceClient)
    client.exchange = MagicMock()
    client.market_type = "futures"
    client.testnet = True
    client.to_ccxt_symbol.side_effect = lambda s: (
        s if ":" in s or client.market_type != "futures" else f"{s}:USDT"
    )
    return client


@pytest.fixture
def mgr(mock_client):
    return OrderManager(mock_client, dry_run=False)


@pytest.fixture
def position_with_all_orders():
    """A typical Position with all three sibling order IDs populated."""
    return Position(
        symbol="BTC/USDT", direction="LONG", entry=95000, sl=94000,
        tp1=96000, tp2=97000, size=1.0,
        sl_order_id="SL-1", tp1_order_id="TP1-1", tp2_order_id="TP2-1",
    )


class TestCancelPositionSiblings:
    """The helper must best-effort cancel SL + TP1 + TP2 reduceOnly orders.

    Behavior contract (spec §7.1):
    - Iterate [SL, TP1, TP2] in order; cancel each via ccxt cancel_order
    - Swallow ccxt.OrderNotFound (order already gone); count as 'missing'
    - Log + count other exceptions as 'failed'; never propagate
    - Return summary dict {cancelled: [...], failed: [...], missing: [...]}
    - Always log a single info line summarizing the result
    """

    def test_cancels_all_three_orders_when_present(
        self, mgr, mock_client, position_with_all_orders
    ):
        result = mgr._cancel_position_siblings(
            position_with_all_orders, "BTC/USDT:USDT", reason="TEST"
        )

        # All three cancel_order calls with the futures notation symbol
        assert mock_client.exchange.cancel_order.call_count == 3
        calls = mock_client.exchange.cancel_order.call_args_list
        assert calls[0].args == ("SL-1", "BTC/USDT:USDT")
        assert calls[1].args == ("TP1-1", "BTC/USDT:USDT")
        assert calls[2].args == ("TP2-1", "BTC/USDT:USDT")

        assert sorted(result["cancelled"]) == ["SL", "TP1", "TP2"]
        assert result["failed"] == []
        assert result["missing"] == []
