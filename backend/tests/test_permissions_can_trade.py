"""Permission manager tests — canTrade detection on Binance Futures.

Bug: fetch_balance() Binance'te /fapi/v2/balance çağırır ve `canTrade` field'ı
DÖNDÜRMEZ. Bot bunu False olarak okuyup tüm sembolleri readonly yapar.
Doğrusu: fapiPrivateV2GetAccount() (/fapi/v2/account) → canTrade field'ı içerir.

Bu testler permission manager'ın doğru endpoint'i kullandığını garanti eder.
"""
from __future__ import annotations

from unittest.mock import MagicMock

from engine.permissions import PermissionManager


def _mock_client(can_trade: bool, fetch_balance_returns_can_trade: bool = False):
    """Mocked BinanceClient — fetch_balance gerçeklik gibi canTrade DÖNDÜRMEZ."""
    client = MagicMock()
    client.market_type = "futures"

    # /fapi/v2/balance — sadece bakiye, canTrade YOK (gerçek Binance davranışı)
    if fetch_balance_returns_can_trade:
        client.exchange.fetch_balance.return_value = {"canTrade": can_trade, "info": {}}
    else:
        # Gerçek davranış: canTrade field'ı yok
        client.exchange.fetch_balance.return_value = {
            "USDT": {"free": 1000.0, "used": 0.0, "total": 1000.0},
            "info": {"totalWalletBalance": "1000.00"},
        }

    # /fapi/v2/account — canTrade dahil tüm permission flagleri burada
    client.exchange.fapiPrivateV2GetAccount.return_value = {
        "canTrade": can_trade,
        "canDeposit": True,
        "canWithdraw": False,
        "totalWalletBalance": "1000.00",
    }

    # Exchange info — basic mock with one symbol
    client.exchange.fapiPublicGetExchangeInfo.return_value = {
        "symbols": [
            {
                "symbol": "BTCUSDT",
                "status": "TRADING",
                "filters": [
                    {"filterType": "MIN_NOTIONAL", "notional": "5"},
                    {"filterType": "LOT_SIZE", "minQty": "0.001"},
                ],
            }
        ]
    }
    return client


def test_can_trade_true_when_account_endpoint_returns_true():
    """fapiPrivateV2GetAccount canTrade:True dönüyorsa, bot bunu yakalamalı."""
    client = _mock_client(can_trade=True)
    pm = PermissionManager(client)
    pm.detect_all(["BTC/USDT"], estimated_notional=100.0)
    assert pm.account_can_trade is True, (
        "Bot canTrade=True görmedi — yanlış endpoint okunuyor olabilir"
    )


def test_btc_is_tradeable_when_can_trade_true():
    """canTrade=True ve sembol TRADING ise, bot tradeable saymalı."""
    client = _mock_client(can_trade=True)
    pm = PermissionManager(client)
    pm.detect_all(["BTC/USDT"], estimated_notional=100.0)
    tradeable = pm.get_tradeable_symbols()
    assert "BTC/USDT" in tradeable, (
        f"BTC tradeable olmalı (canTrade=True), ama got readonly: "
        f"{pm.permissions['BTC/USDT'].reason}"
    )


def test_can_trade_false_when_account_endpoint_returns_false():
    """fapiPrivateV2GetAccount canTrade:False ise, bot da False görmeli."""
    client = _mock_client(can_trade=False)
    pm = PermissionManager(client)
    pm.detect_all(["BTC/USDT"], estimated_notional=100.0)
    assert pm.account_can_trade is False
    assert "BTC/USDT" in pm.get_readonly_symbols()


def test_does_not_rely_on_fetch_balance_for_can_trade():
    """fetch_balance canTrade DÖNDÜRMESE bile bot doğru çalışmalı (regression test)."""
    # Gerçek Binance davranışı: fetch_balance canTrade içermez
    client = _mock_client(can_trade=True, fetch_balance_returns_can_trade=False)
    pm = PermissionManager(client)
    pm.detect_all(["BTC/USDT"], estimated_notional=100.0)
    # Doğru endpoint (fapiPrivateV2GetAccount) çağrılmalı
    assert pm.account_can_trade is True, (
        "Bot fetch_balance'a güveniyor (canTrade yok). "
        "fapiPrivateV2GetAccount kullanmalı."
    )
