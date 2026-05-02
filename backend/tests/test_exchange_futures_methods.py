"""BinanceClient futures-specific methods — get_balance, set_leverage, set_margin_mode.

Bug 1: get_balance() fetch_balance() çağırır ama Binance Futures'ta USDT
       top-level key olarak gelmeyebilir → 0 dönerek bot'un sizing'ini bozar.
       Fix: futures için fapiPrivateV2GetAccount.availableBalance kullan.

Bug 2: set_leverage / set_margin_mode CCXT method'ları "linear/inverse only"
       hatası veriyor (symbol parse). Direct fapi endpoint'leri ile çöz.
"""
from __future__ import annotations

from unittest.mock import MagicMock

from exchange import BinanceClient


def _make_client_with_mock_exchange(market_type: str = "futures"):
    """Real BinanceClient ama exchange mock'lanmış."""
    client = BinanceClient.__new__(BinanceClient)
    client.market_type = market_type
    client.testnet = False
    client.exchange = MagicMock()
    return client


def test_get_balance_uses_fapi_account_for_futures():
    """Futures'ta get_balance fapiPrivateV2GetAccount.availableBalance kullanmalı."""
    client = _make_client_with_mock_exchange("futures")
    client.exchange.fapiPrivateV2GetAccount.return_value = {
        "totalWalletBalance": "1000.50",
        "availableBalance": "987.25",
        "canTrade": True,
    }

    bal = client.get_balance()

    assert bal == 987.25
    client.exchange.fapiPrivateV2GetAccount.assert_called_once()
    # fetch_balance ÇAĞRILMAMALI (eski bug)
    client.exchange.fetch_balance.assert_not_called()


def test_get_balance_falls_back_to_fetch_balance_on_futures_error():
    """fapi endpoint fail ederse fetch_balance fallback'i çalışmalı."""
    client = _make_client_with_mock_exchange("futures")
    client.exchange.fapiPrivateV2GetAccount.side_effect = Exception("network")
    client.exchange.fetch_balance.return_value = {"USDT": {"free": 100.0}}

    bal = client.get_balance()

    assert bal == 100.0


def test_get_balance_uses_fetch_balance_for_spot():
    """Spot'ta hâlâ fetch_balance kullanmalı (eski davranış korunsun)."""
    client = _make_client_with_mock_exchange("spot")
    client.exchange.fetch_balance.return_value = {"USDT": {"free": 250.0}}

    bal = client.get_balance()

    assert bal == 250.0
    client.exchange.fapiPrivateV2GetAccount.assert_not_called()


def test_set_leverage_uses_direct_fapi_endpoint():
    """set_leverage CCXT'nin set_leverage'ını DEĞİL, direct fapi'yi kullanmalı."""
    client = _make_client_with_mock_exchange("futures")
    client.set_leverage("BTC/USDT", 3)

    # Direct fapi çağrılmalı
    client.exchange.fapiPrivatePostLeverage.assert_called_once_with({
        "symbol": "BTCUSDT",  # slashless format
        "leverage": 3,
    })
    # CCXT'nin generic set_leverage çağrılmamalı (eski bug source)
    client.exchange.set_leverage.assert_not_called()


def test_set_margin_mode_uses_direct_fapi_endpoint():
    """set_margin_mode direct fapi çağırmalı."""
    client = _make_client_with_mock_exchange("futures")
    result = client.set_margin_mode("ETH/USDT", "ISOLATED")

    assert result is True
    client.exchange.fapiPrivatePostMarginType.assert_called_once_with({
        "symbol": "ETHUSDT",
        "marginType": "ISOLATED",
    })


def test_set_margin_mode_handles_already_set_error():
    """-4046 (zaten ISOLATED modda) hatası başarı olarak yorumlanmalı."""
    client = _make_client_with_mock_exchange("futures")
    client.exchange.fapiPrivatePostMarginType.side_effect = Exception(
        "binance -4046 No need to change margin type"
    )

    result = client.set_margin_mode("BTC/USDT", "ISOLATED")

    # Hata bastırılmalı, True dönmeli (zaten istenen modda)
    assert result is True


def test_set_leverage_skips_for_spot_market():
    """Spot client'ta set_leverage no-op olmalı."""
    client = _make_client_with_mock_exchange("spot")
    client.set_leverage("BTC/USDT", 3)
    client.exchange.fapiPrivatePostLeverage.assert_not_called()


def test_to_ccxt_symbol_appends_collateral_for_futures():
    """Futures'ta 'BTC/USDT' → 'BTC/USDT:USDT' (linear collateral notation)."""
    client = _make_client_with_mock_exchange("futures")
    assert client.to_ccxt_symbol("BTC/USDT") == "BTC/USDT:USDT"
    assert client.to_ccxt_symbol("ETH/USDT") == "ETH/USDT:USDT"


def test_to_ccxt_symbol_passthrough_for_spot():
    """Spot'ta symbol değişmeden geçer."""
    client = _make_client_with_mock_exchange("spot")
    assert client.to_ccxt_symbol("BTC/USDT") == "BTC/USDT"


def test_to_ccxt_symbol_idempotent_when_already_formatted():
    """Zaten ':USDT' suffix'i varsa tekrar ekleme."""
    client = _make_client_with_mock_exchange("futures")
    assert client.to_ccxt_symbol("BTC/USDT:USDT") == "BTC/USDT:USDT"
