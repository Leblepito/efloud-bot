"""OrderManager slippage capture — actual fill price vs signal price.

Bug — open_position() stores `entry=<signal_price>` on Position, but the
       market order fills at the exchange's actual average price. PnL math
       and downstream analytics are then off by the slippage.

Fix — Read `average` (preferred) or `price` from the entry-order response;
      fall back to signal price if exchange returned nothing useful.
      Log the slippage delta for visibility.
"""
from __future__ import annotations

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


@pytest.fixture
def mgr(mock_client):
    return OrderManager(mock_client, dry_run=False)


def test_records_actual_fill_price_from_average_field(mgr, mock_client):
    """Position.entry must equal Binance's reported `average` fill price."""
    # Signal said 95000, exchange filled at 95012.5 (12.5 USDT slippage)
    mock_client.exchange.create_order.side_effect = [
        {"id": "ENTRY-1", "average": 95012.5, "price": 0, "filled": 1.0},
        {"id": "SL-1"}, {"id": "TP1-1"}, {"id": "TP2-1"},
    ]

    pos = mgr.open_position(
        symbol="BTC/USDT", direction="LONG",
        size=1.0, entry=95000, sl=94000, tp1=96000, tp2=97000,
    )

    assert pos is not None
    assert pos.entry == pytest.approx(95012.5), (
        f"Expected actual fill 95012.5, got {pos.entry} (signal price was 95000). "
        "open_position must capture the average fill from CCXT order response."
    )


def test_falls_back_to_price_field_when_average_missing(mgr, mock_client):
    """Some exchanges return `price` not `average` — use it as fallback."""
    mock_client.exchange.create_order.side_effect = [
        {"id": "E", "price": 2401.5, "filled": 2.0},
        {"id": "S"}, {"id": "T1"}, {"id": "T2"},
    ]
    pos = mgr.open_position(
        symbol="ETH/USDT", direction="SHORT",
        size=2.0, entry=2400, sl=2440, tp1=2360, tp2=2320,
    )
    assert pos.entry == pytest.approx(2401.5)


def test_falls_back_to_signal_when_no_fill_price_available(mgr, mock_client):
    """If exchange returns neither `average` nor `price`, keep signal entry."""
    mock_client.exchange.create_order.side_effect = [
        {"id": "ENTRY-1"},  # no avg/price
        {"id": "SL-1"}, {"id": "TP1-1"}, {"id": "TP2-1"},
    ]
    pos = mgr.open_position(
        symbol="BTC/USDT", direction="LONG",
        size=1.0, entry=95000, sl=94000, tp1=96000, tp2=97000,
    )
    assert pos.entry == 95000  # original signal value
