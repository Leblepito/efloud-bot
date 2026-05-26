"""Unit tests to verify ExchangeAdapter protocol compliance.

Guarantees that BinanceClient, MT5Client, and OandaClient satisfy the
structural subtyping contract (duck-typing) defined by the ExchangeAdapter Protocol.
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Any
from unittest.mock import MagicMock, patch

import pytest

from exchange import BinanceClient
from exchange.adapter import ExchangeAdapter
from exchange.mt5 import MT5Client
from exchange.oanda import OandaClient


def is_exchange_adapter(obj: Any) -> bool:
    """Helper to verify runtime protocol compliance by inspecting attributes."""
    methods = [
        "fetch_ohlcv",
        "to_ccxt_symbol",
        "get_balance",
        "get_available_margin",
        "get_price",
        "set_leverage",
        "set_margin_mode",
        "set_position_mode",
        "get_open_positions",
    ]
    properties = ["exchange", "market_type", "testnet"]

    # Check methods
    for m in methods:
        if not hasattr(obj, m) or not callable(getattr(obj, m)):
            return False

    # Check properties
    for p in properties:
        if not hasattr(obj, p):
            return False

    return True


# ─────────────────────────────────────────────────────────────────────────────
# Compliance Tests
# ─────────────────────────────────────────────────────────────────────────────

def test_binance_client_compliance():
    """Verify BinanceClient implements the ExchangeAdapter protocol interface."""
    # Build a minimal mocked BinanceClient
    with patch("ccxt.binance") as mock_ccxt:
        client = BinanceClient(api_key="key", api_secret="sec", testnet=True)
        assert is_exchange_adapter(client) is True
        assert client.market_type == "futures"
        assert client.testnet is True


def test_mt5_client_compliance():
    """Verify MT5Client implements the ExchangeAdapter protocol interface."""
    client = MT5Client(login=123, password="pwd", server="srv", testnet=True)
    assert is_exchange_adapter(client) is True
    assert client.market_type == "forex"
    assert client.testnet is True

    # Test mock fetch_ohlcv fallback (when MT5 package is not available)
    df = client.fetch_ohlcv("EURUSD", "15m", limit=10)
    assert len(df) == 10
    assert list(df.columns) == ["open", "high", "low", "close", "volume"]


def test_oanda_client_compliance():
    """Verify OandaClient implements the ExchangeAdapter protocol interface."""
    client = OandaClient(account_id="acc", api_token="tok", testnet=True)
    assert is_exchange_adapter(client) is True
    assert client.market_type == "forex"
    assert client.testnet is True

    # Test mock fetch_ohlcv fallback (when oandapyV20 is not available)
    df = client.fetch_ohlcv("EUR/USD", "15m", limit=5)
    assert len(df) == 5
    assert list(df.columns) == ["open", "high", "low", "close", "volume"]
