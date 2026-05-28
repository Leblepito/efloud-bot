"""PR #102a: Handle Binance -2021 'Order would immediately trigger' for TP repairs.

Production bug (2026-05-28 14:41 UTC — LINK/USDT SHORT):
  - Position SL-protected (PR #99 success)
  - Price already passed TP1 target (karlı bölge)
  - _repair_missing_protection_orders her cycle TP1_REPAIR deniyor
  - Binance -2021 döndürüyor → log.warning → tp1_order_id="" kalır
  - Sonraki cycle tekrar dener → infinite loop (90 warning/saat)

Fix:
  - _is_unreachable_error() yeni helper: -2021, "would immediately trigger"
  - _retry_tp_order: _is_unreachable_error durumunda "UNREACHABLE" sentinel döner
  - _repair_missing_protection_orders:
    - "UNREACHABLE" tp1_order_id → subsequent cycles skip
    - Sentinel set edildiğinde notification + log.critical (operator aware)
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch
import pytest

from exchange import BinanceClient, OrderManager, Position


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


# ─────────────────────────────────────────────────────────────
# PHASE 1: _is_unreachable_error detection
# ─────────────────────────────────────────────────────────────


class TestIsUnreachableError:
    """-2021 and 'would immediately trigger' should be classified unreachable."""

    def test_2021_is_unreachable(self):
        """Binance -2021 code → Order would immediately trigger."""
        exc = Exception('binance {"code":-2021,"msg":"Order would immediately trigger."}')
        assert OrderManager._is_unreachable_error(exc) is True

    def test_would_immediately_trigger_text(self):
        """Text-only variant (no code)."""
        exc = Exception("Order would immediately trigger")
        assert OrderManager._is_unreachable_error(exc) is True

    def test_stop_price_invalid(self):
        """Some exchanges return this phrasing."""
        exc = Exception("Stop price is too close to market price")
        # Currently not in the unreachable list — document this behavior
        # If operators report it, we can add it later.
        assert OrderManager._is_unreachable_error(exc) is False

    def test_transient_error_is_not_unreachable(self):
        """Network timeout is transient, not unreachable."""
        exc = TimeoutError("connection timed out")
        assert OrderManager._is_unreachable_error(exc) is False

    def test_balance_error_is_not_unreachable(self):
        """Insufficient margin is a different category."""
        exc = ValueError("Insufficient margin")
        assert OrderManager._is_unreachable_error(exc) is False


# ─────────────────────────────────────────────────────────────
# PHASE 2: _retry_tp_order returns sentinel on unreachable
# ─────────────────────────────────────────────────────────────


class TestRetryTPUnreachableSentinel:
    """-2021 (unreachable) must return 'UNREACHABLE' sentinel, not ''."""

    def test_unreachable_returns_sentinel_on_first_attempt(self, mgr, mock_client):
        """First try hits -2021 → immediate UNREACHABLE, no retry."""
        mock_client.exchange.create_order.side_effect = Exception(
            'binance {"code":-2021,"msg":"Order would immediately trigger."}'
        )
        result = mgr._retry_tp_order(
            ccxt_sym="LINK/USDT:USDT",
            order_type="TAKE_PROFIT_MARKET",
            side="buy",
            amount=100.0,
            params={"stopPrice": 22.5, "reduceOnly": True},
            label="TP1_REPAIR",
            symbol="LINK/USDT",
            direction="SHORT",
            entry_order_id="ENTRY-1",
            sl_order_id="SL-1",
            price_display=22.5,
        )
        assert result == "UNREACHABLE"
        # Only 1 attempt (non-transient, no retry)
        assert mock_client.exchange.create_order.call_count == 1

    def test_transient_then_unreachable_returns_sentinel(self, mgr, mock_client):
        """Timeout then -2021 → sentinel after retries exhausted."""
        mock_client.exchange.create_order.side_effect = [
            TimeoutError("connection timed out"),  # transient, retries
            Exception('binance {"code":-2021,"msg":"Order would immediately trigger."}'),
        ]
        with patch("exchange._time.sleep"):
            result = mgr._retry_tp_order(
                ccxt_sym="LINK/USDT:USDT",
                order_type="TAKE_PROFIT_MARKET",
                side="buy",
                amount=100.0,
                params={"stopPrice": 22.5, "reduceOnly": True},
                label="TP1_REPAIR",
                symbol="LINK/USDT",
                direction="SHORT",
                entry_order_id="ENTRY-1",
                sl_order_id="SL-1",
                price_display=22.5,
            )
        assert result == "UNREACHABLE"

    def test_success_returns_real_oid(self, mgr, mock_client):
        """Normal success path unchanged — returns order id."""
        mock_client.exchange.create_order.return_value = {"id": "TP1-OK"}
        result = mgr._retry_tp_order(
            ccxt_sym="LINK/USDT:USDT",
            order_type="TAKE_PROFIT_MARKET",
            side="buy",
            amount=100.0,
            params={"stopPrice": 22.5, "reduceOnly": True},
            label="TP1_REPAIR",
            symbol="LINK/USDT",
            direction="SHORT",
            entry_order_id="ENTRY-1",
            sl_order_id="SL-1",
            price_display=22.5,
        )
        assert result == "TP1-OK"

    def test_non_unreachable_non_transient_returns_empty(self, mgr, mock_client):
        """Normal non-transient error (e.g. bad symbol) still returns ''."""
        mock_client.exchange.create_order.side_effect = ValueError("Invalid symbol")
        result = mgr._retry_tp_order(
            ccxt_sym="LINK/USDT:USDT",
            order_type="TAKE_PROFIT_MARKET",
            side="buy",
            amount=100.0,
            params={"stopPrice": 22.5, "reduceOnly": True},
            label="TP1_REPAIR",
            symbol="LINK/USDT",
            direction="SHORT",
            entry_order_id="ENTRY-1",
            sl_order_id="SL-1",
            price_display=22.5,
        )
        assert result == ""


# ─────────────────────────────────────────────────────────────
# PHASE 3: _repair_missing_protection_orders sentinel handling
# ─────────────────────────────────────────────────────────────


class TestRepairSkipsUnreachable:
    """Sentinel 'UNREACHABLE' tp1_order_id must stop subsequent repair attempts."""

    def test_sentinel_tp1_skips_repair(self, mgr, mock_client):
        """tp1_order_id == 'UNREACHABLE' → no repair attempt."""
        pos = Position(
            symbol="LINK/USDT", direction="SHORT",
            entry=23.0, sl=23.5, tp1=22.5, tp2=22.0,
            size=100.0,
            order_id="ENTRY-1", sl_order_id="SL-1",
            tp1_order_id="UNREACHABLE",  # Sentinel from prior cycle
            tp2_order_id="TP2-1",
        )
        mgr.positions = [pos]

        mgr._repair_missing_protection_orders(bn_order_ids={"SL-1", "TP2-1"})

        # No order placed — sentinel means we already know it's unreachable
        mock_client.exchange.create_order.assert_not_called()

    def test_sentinel_tp2_skips_repair(self, mgr, mock_client):
        """tp2_order_id == 'UNREACHABLE' → no repair attempt for TP2."""
        pos = Position(
            symbol="LINK/USDT", direction="SHORT",
            entry=23.0, sl=23.5, tp1=22.5, tp2=22.0,
            size=100.0,
            order_id="ENTRY-1", sl_order_id="SL-1",
            tp1_order_id="TP1-1",
            tp2_order_id="UNREACHABLE",  # Sentinel
        )
        mgr.positions = [pos]

        mgr._repair_missing_protection_orders(bn_order_ids={"SL-1", "TP1-1"})

        # Only TP2 repair would have been attempted, but skipped due to sentinel
        mock_client.exchange.create_order.assert_not_called()

    def test_repair_sets_sentinel_on_unreachable(self, mgr, mock_client):
        """First time -2021 encountered → tp1_order_id set to 'UNREACHABLE'."""
        pos = Position(
            symbol="LINK/USDT", direction="SHORT",
            entry=23.0, sl=23.5, tp1=22.5, tp2=22.0,
            size=100.0,
            order_id="ENTRY-1", sl_order_id="SL-1",
            tp1_order_id="",  # Empty → needs repair
            tp2_order_id="TP2-1",
        )
        mgr.positions = [pos]

        # Simulate -2021 on repair attempt
        mock_client.exchange.create_order.side_effect = Exception(
            'binance {"code":-2021,"msg":"Order would immediately trigger."}'
        )

        mgr._repair_missing_protection_orders(bn_order_ids={"SL-1", "TP2-1"})

        # Sentinel set — subsequent cycles will skip
        assert pos.tp1_order_id == "UNREACHABLE"

    def test_sentinel_emits_critical_log(self, mgr, mock_client, caplog):
        """Sentinel assignment must emit CRITICAL log for operator awareness."""
        import logging
        caplog.set_level(logging.CRITICAL, logger="efloud.exchange")

        pos = Position(
            symbol="LINK/USDT", direction="SHORT",
            entry=23.0, sl=23.5, tp1=22.5, tp2=22.0,
            size=100.0,
            order_id="ENTRY-1", sl_order_id="SL-1",
            tp1_order_id="",
            tp2_order_id="TP2-1",
        )
        mgr.positions = [pos]

        mock_client.exchange.create_order.side_effect = Exception(
            'binance {"code":-2021,"msg":"Order would immediately trigger."}'
        )

        mgr._repair_missing_protection_orders(bn_order_ids={"SL-1", "TP2-1"})

        assert any(
            "tp_unreachable" in msg
            for msg in caplog.text.splitlines()
        ), f"Expected tp_unreachable event in logs, got: {caplog.text}"
