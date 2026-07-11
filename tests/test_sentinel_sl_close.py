"""F3-F7 exchange fixes — sentinel SL, fallback close, TP dust (2026-07-11 batch).

Spec: docs/superpowers/specs/2026-07-11-tp-entry-anchored-targeting-and-bugfix-batch-design.md Bölüm 3.

F3: BE-SL taşımada "UNREACHABLE" sentineli order id gibi saklanıyordu →
    kalan yarım pozisyon stopsuz + repair kalıcı devre dışı.
F4: SL_REPAIR aynı sentinel bugı — fiyat SL'yi geçmişken korumasız pozisyon.
F5: _fallback_close başarısız close'u yutup sibling iptal ediyordu → çıplak pozisyon.
F6: fallback/manual close her zaman full size gönderiyordu (TP1 sonrası -2022).
F7: TP1/TP2 miktarları bağımsız truncate → dust kalıntısı, pozisyon tam kapanmaz.
"""

import math
from unittest.mock import Mock, MagicMock, patch

import pytest

from exchange import OrderManager, Position, _TP_UNREACHABLE_SENTINEL


def _om(step: float = 0.001):
    """dry_run=False OrderManager with a mocked ccxt client."""
    client = Mock()
    client.to_ccxt_symbol = Mock(side_effect=lambda s: s)
    client.get_price = Mock(return_value=100.0)
    exchange = Mock()
    exchange.amount_to_precision = Mock(
        side_effect=lambda s, a: f"{math.floor(float(a) / step + 1e-9) * step:.6f}"
    )
    exchange.price_to_precision = Mock(side_effect=lambda s, p: f"{float(p):.6f}")
    exchange.create_order = Mock(return_value={"id": "entry-1", "price": 100.0})
    exchange.fetch_positions = Mock(return_value=[])
    client.exchange = exchange
    om = OrderManager(client, dry_run=False)
    om.client = client
    om.hedge_mode = False
    om.max_entry_drift_pct = 0
    om._persist = Mock()
    om._emit = Mock()
    return om


def _pos(size=10.0, tp1_hit=False):
    p = Position("ETH/USDT", "LONG", 100.0, 99.0, 103.0, 106.0, size)
    p.order_id = "entry-1"
    p.sl_order_id = "sl-1"
    p.tp1_order_id = "tp1-1"
    p.tp2_order_id = "tp2-1"
    p.tp1_hit = tp1_hit
    return p


class TestF3BeSentinelClosesRemainder:
    def test_be_move_sentinel_market_closes_remainder(self):
        om = _om()
        pos = _pos(size=10.0, tp1_hit=True)
        om.positions.append(pos)
        om._record_close = Mock()
        om._cancel_position_siblings = Mock()

        with patch.object(om, "_cancel_order_any", Mock(return_value="ok")), \
             patch.object(om, "_retry_tp_order",
                          Mock(return_value=_TP_UNREACHABLE_SENTINEL)):
            om._move_sl_to_breakeven(pos)

        # Sentinel asla order id olarak saklanmamalı
        assert pos.sl_order_id != _TP_UNREACHABLE_SENTINEL, (
            "UNREACHABLE sentinel stored as SL order id → repair permanently "
            "suppressed, half position naked"
        )
        # Fail-closed: kalan yarım pozisyon market-close edilmeli
        close_calls = [
            c for c in om.client.exchange.create_order.call_args_list
            if c.args[1] == "market"
        ]
        assert close_calls, "remainder must be market-closed when BE-SL is unreachable"
        assert pos not in om.positions


class TestF4RepairSentinelClosesPosition:
    def test_sl_repair_sentinel_triggers_close(self):
        om = _om()
        pos = _pos(size=10.0)
        pos.sl_order_id = ""  # SL kayıp → repair yolu
        om.positions.append(pos)
        om._fallback_close = Mock(return_value=True)

        with patch.object(om, "_retry_tp_order",
                          Mock(return_value=_TP_UNREACHABLE_SENTINEL)):
            om._repair_missing_protection_orders(
                bn_order_ids={"tp1-1", "tp2-1"}, algo_fetch_ok=True,
            )

        assert pos.sl_order_id != _TP_UNREACHABLE_SENTINEL
        assert om._fallback_close.called, (
            "-2021 on SL repair = price already beyond stop → position must be closed"
        )


class TestF5FallbackCloseAbortsOnFailure:
    def test_failed_close_preserves_orders_and_tracking(self):
        om = _om()
        pos = _pos(size=10.0)
        om.positions.append(pos)
        om._record_close = Mock()
        om._cancel_position_siblings = Mock()
        om.client.exchange.create_order = Mock(side_effect=Exception("binance down"))

        result = om._fallback_close(pos, 99.0, "SL_POLL")

        assert result is False
        assert pos in om.positions, "tracking must be preserved on failed close"
        assert not om._cancel_position_siblings.called, (
            "SL/TP siblings must NOT be cancelled when close failed (naked position)"
        )
        assert not om._record_close.called

    def test_successful_close_returns_true(self):
        om = _om()
        pos = _pos(size=10.0)
        om.positions.append(pos)
        om._record_close = Mock()
        om._cancel_position_siblings = Mock()

        result = om._fallback_close(pos, 99.0, "SL_POLL")

        assert result is True
        assert pos not in om.positions
        assert om._record_close.called


class TestF6RemainingSizeClose:
    def test_close_after_tp1_sends_half_size(self):
        om = _om()
        pos = _pos(size=10.0, tp1_hit=True)
        om.positions.append(pos)
        om._record_close = Mock()
        om._cancel_position_siblings = Mock()

        om._fallback_close(pos, 104.0, "TP2_POLL")

        args = om.client.exchange.create_order.call_args
        sent_amount = float(args.args[3])
        assert sent_amount == pytest.approx(5.0), (
            f"TP1 sonrası kalan {10.0/2} gönderilmeli (full 10.0 reduceOnly'de "
            f"-2022 alır); gönderilen: {sent_amount}"
        )

    def test_close_before_tp1_sends_full_size(self):
        om = _om()
        pos = _pos(size=10.0, tp1_hit=False)
        om.positions.append(pos)
        om._record_close = Mock()
        om._cancel_position_siblings = Mock()

        om._fallback_close(pos, 99.0, "SL_POLL")

        args = om.client.exchange.create_order.call_args
        assert float(args.args[3]) == pytest.approx(10.0)


class TestF7TpSizesNoDust:
    def test_tp1_tp2_sum_equals_entry_size(self):
        # step=0.002, size=0.007: eski davranış entry=0.007 (raw), TP'ler
        # trunc(0.0035)=0.002 + trunc(0.0035)=0.002 → 0.004 ≠ dolan miktar.
        # Yeni: size→0.006, TP1=trunc(0.003)=0.002, TP2=0.006-0.002=0.004 → toplam 0.006.
        om = _om(step=0.002)
        captured = []

        def fake_retry(**kw):
            captured.append((kw.get("label"), float(kw.get("amount"))))
            return f"oid-{kw.get('label')}"

        with patch.object(om, "_retry_tp_order", Mock(side_effect=fake_retry)):
            pos = om.open_position(
                symbol="ETH/USDT", direction="LONG", size=0.007,
                entry=100.0, sl=99.0, tp1=103.0, tp2=106.0,
            )

        entry_call = om.client.exchange.create_order.call_args_list[0]
        entry_amount = float(entry_call.args[3])
        tp_amounts = {lbl: amt for lbl, amt in captured if lbl in ("TP1", "TP2")}
        assert tp_amounts, f"TP orders not captured: {captured}"
        total_tp = sum(tp_amounts.values())
        assert total_tp == pytest.approx(entry_amount), (
            f"dust: entry={entry_amount} ≠ TP1+TP2={total_tp} ({tp_amounts})"
        )
