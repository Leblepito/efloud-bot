"""B-1 (2026-07-17 review): reconcile TP1/TP2 "missing" tespiti algo_fetch_ok
gate'i olmadan çalışıyordu.

Canlı SL/TP emirleri algoId'dir (modül invariant'ı, satır ~728 ve ~1322
yorumları): bn_order_ids'in algo yarısı fapiPrivateGetOpenAlgoOrders'tan gelir.
Regular fetch başarılı ama ALGO fetch geçici olarak başarısızsa (5xx, rate
limit) bn_order_ids'te hiç algoId yoktur → her canlı TP1/TP2 "kayıp" görünür →
id'ler temizlenir → aynı cycle'daki repair, borsada HÂLÂ CANLI olan orijinal
emirlerin yanına duplicate TAKE_PROFIT_MARKET basar (2026-05-08 stacking sınıfı;
SL yolu `sl_absent_on_exchange` ile korunmuştu, TP yolları korunmamıştı).

RED→GREEN: bu testler fix'ten önce FAIL eder (id'ler temizlenir), fix'ten sonra
geçer. Kontrol testi mevcut davranışı korur: algo fetch BAŞARILIYKEN gerçekten
kayıp TP hâlâ temizlenir (repair tetiklenir).
"""

import math
from unittest.mock import Mock

import pytest

from exchange import OrderManager, Position


def _om():
    client = Mock()
    client.to_ccxt_symbol = Mock(side_effect=lambda s: s)
    client.get_price = Mock(return_value=100.0)
    exchange = Mock()
    exchange.amount_to_precision = Mock(
        side_effect=lambda s, a: f"{math.floor(float(a) / 0.001 + 1e-9) * 0.001:.6f}"
    )
    exchange.price_to_precision = Mock(side_effect=lambda s, p: f"{float(p):.6f}")
    exchange.create_order = Mock(return_value={"id": "new-1", "price": 100.0})
    client.exchange = exchange
    om = OrderManager(client, dry_run=False)
    om.client = client
    om.hedge_mode = False
    om._persist = Mock()
    om._emit = Mock()
    # Repair'i izole et: reconcile'ın temizleme kararını test ediyoruz,
    # emir basma zincirini değil.
    om._repair_missing_protection_orders = Mock()
    return om


def _pos(size=10.0):
    p = Position("ETH/USDT", "LONG", 100.0, 99.0, 103.0, 106.0, size)
    p.order_id = "entry-1"
    p.sl_order_id = "sl-1"
    p.tp1_order_id = "tp1-1"
    p.tp2_order_id = "tp2-1"
    return p


def _bn_open(size=10.0):
    return [{"symbol": "ETH/USDT", "contracts": size, "side": "LONG"}]


class TestAlgoFetchFailurePreservesTpIds:
    def test_tp_ids_not_cleared_when_algo_fetch_fails(self):
        om = _om()
        pos = _pos()
        om.positions.append(pos)
        om.client.get_open_positions = Mock(return_value=_bn_open())
        # Regular orders fetch OK (boş liste yeterli — TP'ler zaten algoId),
        # ALGO fetch geçici hata veriyor.
        om.client.exchange.fetch_open_orders = Mock(return_value=[])
        om.client.exchange.fapiPrivateGetOpenAlgoOrders = Mock(
            side_effect=Exception("binance 5xx")
        )

        om.reconcile()

        assert pos.tp1_order_id == "tp1-1", (
            "algo fetch başarısızken TP1 id temizlendi → aynı cycle'da repair "
            "duplicate TP1 basar (2026-05-08 stacking sınıfı)"
        )
        assert pos.tp2_order_id == "tp2-1", (
            "algo fetch başarısızken TP2 id temizlendi → duplicate TP2 riski"
        )
        assert pos.tp1_hit is False

    def test_repair_still_called_with_algo_flag_false(self):
        """Repair çağrısı yapılır ama algo_fetch_ok=False taşır (SL yolu için)."""
        om = _om()
        pos = _pos()
        om.positions.append(pos)
        om.client.get_open_positions = Mock(return_value=_bn_open())
        om.client.exchange.fetch_open_orders = Mock(return_value=[])
        om.client.exchange.fapiPrivateGetOpenAlgoOrders = Mock(
            side_effect=Exception("binance 5xx")
        )

        om.reconcile()

        assert om._repair_missing_protection_orders.called
        _, kwargs = om._repair_missing_protection_orders.call_args
        assert kwargs.get("algo_fetch_ok") is False


class TestAlgoFetchOkKeepsExistingBehavior:
    def test_genuinely_missing_tp_still_cleared_and_repaired(self):
        """Kontrol: algo fetch BAŞARILI + TP algo listede yok + boyut tam →
        id temizlenir (repair'in yeniden basabilmesi için) — mevcut davranış."""
        om = _om()
        pos = _pos()
        om.positions.append(pos)
        om.client.get_open_positions = Mock(return_value=_bn_open())
        om.client.exchange.fetch_open_orders = Mock(return_value=[])
        om.client.exchange.fapiPrivateGetOpenAlgoOrders = Mock(return_value=[])

        om.reconcile()

        assert pos.tp1_order_id == ""
        assert pos.tp2_order_id == ""

    def test_live_tp_in_algo_set_untouched(self):
        om = _om()
        pos = _pos()
        om.positions.append(pos)
        om.client.get_open_positions = Mock(return_value=_bn_open())
        om.client.exchange.fetch_open_orders = Mock(return_value=[])
        om.client.exchange.fapiPrivateGetOpenAlgoOrders = Mock(
            return_value=[{"algoId": "tp1-1"}, {"algoId": "tp2-1"}, {"algoId": "sl-1"}]
        )

        om.reconcile()

        assert pos.tp1_order_id == "tp1-1"
        assert pos.tp2_order_id == "tp2-1"
