"""BinanceClient must hand CCXT the canonical singular defaultType string.

CCXT 4.5.40 binance.py only recognizes 'spot|future|margin|delivery|option'
for options.defaultType. Passing 'futures' (plural — the bot's internal name)
silently routes fetch_open_orders to the spot endpoint, which is the 2026-05-08
reconcile-blindspot bug.
"""
import pytest
from unittest.mock import patch, MagicMock

from exchange import BinanceClient


def _make_client(market_type: str) -> BinanceClient:
    """Construct a BinanceClient without making network calls."""
    with patch("exchange.ccxt.binance") as mock_ctor:
        mock_ctor.return_value = MagicMock()
        mock_ctor.return_value.options = {}
        client = BinanceClient(
            api_key="k", api_secret="s",
            testnet=False, market_type=market_type,
        )
        # Capture the opts dict that was passed to ccxt.binance(...)
        client._captured_opts = mock_ctor.call_args.args[0] if mock_ctor.call_args.args else mock_ctor.call_args.kwargs
        return client


def test_market_type_futures_passes_singular_to_ccxt():
    """market_type='futures' (bot internal name) → CCXT receives 'future' (singular)."""
    client = _make_client(market_type="futures")
    opts = client._captured_opts
    assert opts["options"]["defaultType"] == "future", (
        f"Expected 'future' (singular CCXT canonical) but got "
        f"{opts['options']['defaultType']!r}. Bug: 'futures' routes to spot endpoint."
    )


def test_internal_market_type_unchanged():
    """self.market_type keeps the bot's internal 'futures' label so existing
    `client.market_type == "futures"` comparisons (40+ sites) keep working."""
    client = _make_client(market_type="futures")
    assert client.market_type == "futures"


def test_market_type_spot_passes_through():
    """Non-futures market_type values are passed to CCXT unchanged."""
    client = _make_client(market_type="spot")
    opts = client._captured_opts
    assert opts["options"]["defaultType"] == "spot"
    assert client.market_type == "spot"
