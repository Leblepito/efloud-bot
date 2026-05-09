"""Unit tests for BinanceClient balance methods.

get_balance() returns totalMarginBalance (wallet + unrealized PnL).
get_available_margin() returns availableBalance (free margin not locked in positions).

Both must:
- Hit the futures endpoint for futures market_type
- Fall back to fetch_balance() for spot
- Return float (never None / dict)
- Never raise on transient API failure
"""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from exchange import BinanceClient


def _make_client(market_type: str = "futures") -> BinanceClient:
    """Construct a BinanceClient without hitting the real API.

    Bypass __init__ to avoid ccxt setup; inject a mock exchange directly.
    """
    c = BinanceClient.__new__(BinanceClient)
    c.market_type = market_type
    c.exchange = MagicMock()
    return c


class TestGetBalance:
    """Existing get_balance() — sanity checks that current behavior is preserved."""

    def test_futures_returns_total_margin_balance(self):
        c = _make_client("futures")
        c.exchange.fapiPrivateV2GetAccount.return_value = {
            "totalMarginBalance": "2156.32",
            "availableBalance": "1820.00",
        }
        assert c.get_balance() == pytest.approx(2156.32)

    def test_futures_falls_back_on_api_failure(self):
        c = _make_client("futures")
        c.exchange.fapiPrivateV2GetAccount.side_effect = RuntimeError("network")
        c.exchange.fetch_balance.return_value = {"USDT": {"total": 2100.0}}
        assert c.get_balance() == pytest.approx(2100.0)


class TestGetAvailableMargin:
    """New method. Mirrors get_balance() shape but returns availableBalance."""

    def test_futures_returns_available_balance(self):
        c = _make_client("futures")
        c.exchange.fapiPrivateV2GetAccount.return_value = {
            "totalMarginBalance": "2156.32",
            "availableBalance": "1820.00",
        }
        assert c.get_available_margin() == pytest.approx(1820.00)

    def test_futures_returns_float_not_string(self):
        c = _make_client("futures")
        c.exchange.fapiPrivateV2GetAccount.return_value = {"availableBalance": "1500.50"}
        result = c.get_available_margin()
        assert isinstance(result, float)
        assert result == pytest.approx(1500.50)

    def test_futures_handles_missing_field_returns_zero(self):
        """If Binance response is malformed, we must not crash — return 0.0."""
        c = _make_client("futures")
        c.exchange.fapiPrivateV2GetAccount.return_value = {"totalMarginBalance": "100"}
        # availableBalance missing → 0.0 (caller will see no margin → no new position)
        assert c.get_available_margin() == 0.0

    def test_futures_falls_back_on_api_failure(self):
        """If fapi endpoint fails, fall back to fetch_balance['USDT']['free']."""
        c = _make_client("futures")
        c.exchange.fapiPrivateV2GetAccount.side_effect = RuntimeError("network")
        c.exchange.fetch_balance.return_value = {"USDT": {"free": 1500.0, "total": 2100.0}}
        # Available margin maps to USDT 'free' on fallback
        assert c.get_available_margin() == pytest.approx(1500.0)

    def test_spot_uses_free_balance(self):
        c = _make_client("spot")
        c.exchange.fetch_balance.return_value = {"USDT": {"free": 800.0, "total": 1000.0}}
        assert c.get_available_margin() == pytest.approx(800.0)
