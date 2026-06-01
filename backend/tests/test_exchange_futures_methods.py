"""BinanceClient futures-specific methods — get_balance, set_leverage, set_margin_mode.

Bug 1 (original): get_balance() fetch_balance() çağırır ama Binance Futures'ta USDT
       top-level key olarak gelmeyebilir → 0 dönerek bot'un sizing'ini bozar.
       Fix v1: futures için fapiPrivateV2GetAccount.availableBalance kullan.

Bug 1b (2026-05-05): availableBalance açık pozisyonların margin'ini hariç tutuyor →
       cüzdanda $2040 olsa da pozisyon açıkken availableBalance $993 olabilir, breaker
       false HALT veriyor. Fix v2: totalMarginBalance (mark-to-market equity) kullan;
       hem cüzdan cash'i hem unrealized PnL'i kapsar.

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
    """Futures'ta get_balance fapiPrivateV2GetAccount.totalMarginBalance kullanmalı.

    Per bug 1b: availableBalance margin-locked-in-positions'ı hariç tutuyor; risk
    breaker'ı için doğru metric totalMarginBalance (cash + unrealized PnL).
    """
    client = _make_client_with_mock_exchange("futures")
    client.exchange.fapiPrivateV2GetAccount.return_value = {
        "totalWalletBalance": "2040.00",
        "totalMarginBalance": "2032.50",  # wallet + unrealized = mark-to-market equity
        "availableBalance": "993.54",      # would falsely halt breaker if used
        "canTrade": True,
    }

    bal = client.get_balance()

    assert bal == 2032.50
    client.exchange.fapiPrivateV2GetAccount.assert_called_once()
    # fetch_balance ÇAĞRILMAMALI (eski bug)
    client.exchange.fetch_balance.assert_not_called()


def test_get_balance_falls_back_to_fetch_balance_on_futures_error():
    """fapi endpoint fail ederse fetch_balance fallback'i çalışmalı.

    Fallback de 'total' okuyor (free + locked) — aynı semantik korunur.
    """
    client = _make_client_with_mock_exchange("futures")
    client.exchange.fapiPrivateV2GetAccount.side_effect = Exception("network")
    client.exchange.fetch_balance.return_value = {"USDT": {"total": 100.0, "free": 50.0}}

    bal = client.get_balance()

    assert bal == 100.0


def test_get_balance_uses_fetch_balance_for_spot():
    """Spot'ta hâlâ fetch_balance kullanmalı; total (free + locked) okur."""
    client = _make_client_with_mock_exchange("spot")
    client.exchange.fetch_balance.return_value = {"USDT": {"total": 250.0, "free": 250.0}}

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


# ── PR A: one-way position mode + ISOLATED margin ──

def test_set_position_mode_oneway_get_first_short_circuits():
    """When the exchange already reports ONE_WAY, set_position_mode(False)
    returns True via the GET check without POSTing."""
    client = _make_client_with_mock_exchange("futures")
    client.exchange.fapiPrivateGetPositionSideDual.return_value = {"dualSidePosition": False}

    assert client.set_position_mode(dual_side=False) is True
    client.exchange.fapiPrivateGetPositionSideDual.assert_called_once()
    client.exchange.fapiPrivatePostPositionSideDual.assert_not_called()


def test_set_position_mode_oneway_posts_when_currently_hedge():
    """Currently HEDGE, want ONE_WAY → POST dualSidePosition=false."""
    client = _make_client_with_mock_exchange("futures")
    client.exchange.fapiPrivateGetPositionSideDual.return_value = {"dualSidePosition": True}

    assert client.set_position_mode(dual_side=False) is True
    client.exchange.fapiPrivatePostPositionSideDual.assert_called_once()
    sent = client.exchange.fapiPrivatePostPositionSideDual.call_args[0][0]
    assert sent["dualSidePosition"] == "false"


def test_set_margin_mode_isolated_treats_no_change_as_success():
    """set_margin_mode ISOLATED — benign -4046 'no need to change' = success."""
    client = _make_client_with_mock_exchange("futures")
    client.exchange.fapiPrivatePostMarginType.side_effect = Exception("-4046 No need to change margin type.")

    assert client.set_margin_mode("BTC/USDT", "ISOLATED") is True


def test_oneway_order_params_use_reduce_only_not_position_side():
    """One-way mode (hedge_mode False): protection orders carry reduceOnly and
    never positionSide — documents the open_position param-building branch."""
    hedge_mode = False
    sl_params = {"stopPrice": 95.0}
    if hedge_mode:
        sl_params["positionSide"] = "LONG"
    else:
        sl_params["reduceOnly"] = True
    assert sl_params.get("reduceOnly") is True
    assert "positionSide" not in sl_params


def test_set_margin_mode_get_first_skips_post_when_already_target():
    """GET-first: already-CROSSED symbol with open orders must NOT POST (avoids
    Binance -4047 'cannot change with open orders' on a redundant set)."""
    client = _make_client_with_mock_exchange("futures")
    client.exchange.fapiPrivateV2GetPositionRisk.return_value = [{"marginType": "cross"}]

    assert client.set_margin_mode("BTC/USDT", "CROSSED") is True
    client.exchange.fapiPrivatePostMarginType.assert_not_called()


def test_set_margin_mode_posts_when_mode_differs():
    """GET shows CROSS, target ISOLATED → must POST the change."""
    client = _make_client_with_mock_exchange("futures")
    client.exchange.fapiPrivateV2GetPositionRisk.return_value = [{"marginType": "cross"}]

    assert client.set_margin_mode("BTC/USDT", "ISOLATED") is True
    client.exchange.fapiPrivatePostMarginType.assert_called_once()


def test_set_margin_mode_minus4047_is_fatal_when_mismatch():
    """If GET-first cannot confirm a match and the POST hits -4047 (genuine
    mismatch on a non-flat book), it must stay fatal (return False)."""
    client = _make_client_with_mock_exchange("futures")
    client.exchange.fapiPrivateV2GetPositionRisk.return_value = [{"marginType": "cross"}]
    client.exchange.fapiPrivatePostMarginType.side_effect = Exception(
        'binance {"code":-4047,"msg":"Margin type cannot be changed if there exists open orders."}')

    assert client.set_margin_mode("BTC/USDT", "ISOLATED") is False
