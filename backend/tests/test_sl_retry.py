"""Tests for SL placement retry, repair, and breakeven SL retry mechanisms.

SL placement previously had no retry — transient API errors caused immediate
rollback or orphan positions with no SL protection.

These tests validate the fixes:
1. SL placement retries on transient errors (3 attempts, exponential backoff)
2. _repair_missing_protection_orders also repairs missing SL orders
3. _move_sl_to_breakeven retries new SL placement
4. On exhaustion, sl_order_id='' for reconcile repair
"""
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
# BUG #2: SL placement should retry transient errors
# ─────────────────────────────────────────────────────────────


class TestSLRetry:
    """SL placement should retry transient errors like TP does."""

    @patch("exchange._time.sleep")
    def test_sl_transient_error_retries_and_succeeds(self, mock_sleep, mgr, mock_client):
        """SL fails with timeout on attempt 1, succeeds on attempt 2."""
        mock_client.exchange.create_order.side_effect = [
            {"id": "ENTRY-1", "filled": 1.0, "average": 95000},
            TimeoutError("Request timed out"),  # SL attempt 1
            {"id": "SL-1"},                     # SL attempt 2 — success
            {"id": "TP1-1"},                    # TP1
            {"id": "TP2-1"},                    # TP2
        ]

        pos = mgr.open_position(
            "BTC/USDT", "LONG", 1.0,
            entry=95000, sl=94000, tp1=96000, tp2=97000,
        )

        assert pos is not None
        assert pos.sl_order_id == "SL-1"
        assert pos.tp1_order_id == "TP1-1"
        assert pos.tp2_order_id == "TP2-1"
        # Verify retry sleep was called
        mock_sleep.assert_called_once_with(1.0)

    @patch("exchange._time.sleep")
    def test_sl_non_transient_error_fails_immediately(self, mock_sleep, mgr, mock_client):
        """Non-transient SL error fails immediately → rollback."""
        mock_client.exchange.create_order.side_effect = [
            {"id": "ENTRY-1", "filled": 1.0, "average": 95000},
            ValueError("Insufficient margin"),  # SL — non-transient → immediate fail
            {"id": "ROLLBACK-1"},               # rollback close
        ]

        pos = mgr.open_position(
            "BTC/USDT", "LONG", 1.0,
            entry=95000, sl=94000, tp1=96000, tp2=97000,
        )

        assert pos is None  # Rollback succeeded
        mock_sleep.assert_not_called()

    @patch("exchange._time.sleep")
    def test_sl_three_transient_failures_exhausts_retries(self, mock_sleep, mgr, mock_client):
        """3 consecutive transient errors exhaust retries → rollback."""
        mock_client.exchange.create_order.side_effect = [
            {"id": "ENTRY-1", "filled": 1.0, "average": 95000},
            TimeoutError("timed out 1"),    # SL attempt 1
            TimeoutError("timed out 2"),    # SL attempt 2
            TimeoutError("timed out 3"),    # SL attempt 3 — exhausted
            {"id": "ROLLBACK-1"},           # rollback close succeeds
        ]

        pos = mgr.open_position(
            "BTC/USDT", "LONG", 1.0,
            entry=95000, sl=94000, tp1=96000, tp2=97000,
        )

        assert pos is None
        assert mock_sleep.call_count == 2  # After attempts 1 and 2


class TestSLRepair:
    """reconcile should detect and re-send missing SL orders."""

    def test_repair_sends_missing_sl(self, mgr, mock_client, caplog):
        """Position with empty sl_order_id gets repaired during reconcile."""
        import logging
        caplog.set_level(logging.CRITICAL, logger="efloud.exchange")

        pos = Position(
            symbol="BTC/USDT", direction="LONG",
            entry=95000, sl=94000, tp1=96000, tp2=97000,
            size=1.0,
            order_id="ENTRY-1", sl_order_id="",  # Missing SL!
            tp1_order_id="TP1-1", tp2_order_id="TP2-1",
        )
        mgr.positions.append(pos)

        mock_client.exchange.create_order.return_value = {"id": "SL-REPAIR"}

        mgr._repair_missing_protection_orders(bn_order_ids={"TP1-1", "TP2-1"})

        assert pos.sl_order_id == "SL-REPAIR"
        repair_call = mock_client.exchange.create_order.call_args
        assert repair_call.args[1] == "STOP_MARKET"
        assert repair_call.kwargs["params"]["stopPrice"] == 94000

    def test_repair_skips_when_sl_present(self, mgr, mock_client):
        """Don't repair SL when sl_order_id is already set."""
        pos = Position(
            symbol="BTC/USDT", direction="LONG",
            entry=95000, sl=94000, tp1=96000, tp2=97000,
            size=1.0,
            order_id="ENTRY-1", sl_order_id="SL-1",  # Present
            tp1_order_id="TP1-1", tp2_order_id="TP2-1",
        )
        mgr.positions.append(pos)

        mgr._repair_missing_protection_orders(bn_order_ids={"SL-1", "TP1-1", "TP2-1"})

        # No orders placed since nothing is missing
        mock_client.exchange.create_order.assert_not_called()


class TestSLRepairIntegration:
    """End-to-end test: position with missing SL repaired during reconcile."""

    def test_reconcile_detects_and_repairs_missing_sl(self, mgr, mock_client):
        """Full reconcile cycle repairs missing SL."""
        pos = Position(
            symbol="BTC/USDT", direction="LONG",
            entry=95000, sl=94000, tp1=96000, tp2=97000,
            size=1.0,
            order_id="ENTRY-1", sl_order_id="",
            tp1_order_id="TP1-1", tp2_order_id="TP2-1",
        )
        mgr.positions = [pos]

        mock_client.get_open_positions.return_value = [
            {"symbol": "BTC/USDT:USDT", "contracts": 1.0, "side": "long"}
        ]
        mock_client.exchange.fetch_open_orders.return_value = [
            {"id": "TP1-1", "type": "TAKE_PROFIT_MARKET"},
            {"id": "TP2-1", "type": "TAKE_PROFIT_MARKET"},
        ]
        try:
            mock_client.exchange.fapiPrivateGetOpenAlgoOrders.return_value = [
                {"algoId": "TP1-1"},
                {"algoId": "TP2-1"},
            ]
        except Exception:
            pass
        # Mock SL repair order
        mock_client.exchange.create_order.return_value = {"id": "SL-REPAIRED"}

        closed = mgr.reconcile()

        assert pos.sl_order_id == "SL-REPAIRED"
        assert len(closed) == 0


# ─────────────────────────────────────────────────────────────
# BUG #3: _move_sl_to_breakeven should retry
# ─────────────────────────────────────────────────────────────


class TestBreakevenSLRetry:
    """_move_sl_to_breakeven should retry new SL placement."""

    @patch("exchange._time.sleep")
    def test_be_sl_retry_on_transient_failure(self, mock_sleep, mgr, mock_client):
        """New SL fails transiently, then succeeds on retry."""
        pos = Position(
            symbol="BTC/USDT", direction="LONG",
            entry=95000, sl=94000, tp1=96000, tp2=97000,
            size=1.0,
            order_id="ENTRY-1", sl_order_id="SL-OLD",
            tp1_order_id="TP1-1", tp2_order_id="TP2-1",
            tp1_hit=True,
        )
        mgr.positions.append(pos)

        # Old SL cancel succeeds, new SL fails then succeeds
        mock_client.exchange.cancel_order.return_value = True
        mock_client.exchange.create_order.side_effect = [
            TimeoutError("timed out"),  # New SL attempt 1
            {"id": "SL-NEW"},           # New SL attempt 2 — success
        ]

        mgr._move_sl_to_breakeven(pos)

        assert pos.sl_order_id == "SL-NEW"
        assert pos.sl == 95000

    @patch("exchange._time.sleep")
    def test_be_sl_exhausted_leaves_empty_for_repair(self, mock_sleep, mgr, mock_client):
        """If all retries fail, sl_order_id='' → reconcile repairs."""
        pos = Position(
            symbol="BTC/USDT", direction="LONG",
            entry=95000, sl=94000, tp1=96000, tp2=97000,
            size=1.0,
            order_id="ENTRY-1", sl_order_id="SL-OLD",
            tp1_order_id="TP1-1", tp2_order_id="TP2-1",
            tp1_hit=True,
        )
        mgr.positions.append(pos)

        mock_client.exchange.cancel_order.return_value = True
        mock_client.exchange.create_order.side_effect = TimeoutError("timed out")

        mgr._move_sl_to_breakeven(pos)

        assert pos.sl_order_id == ""
        assert pos.sl == 95000  # Logical SL still updated

    @patch("exchange._time.sleep")
    def test_be_sl_succeeds_first_try(self, mock_sleep, mgr, mock_client):
        """Happy path: new SL succeeds immediately after cancel."""
        pos = Position(
            symbol="BTC/USDT", direction="LONG",
            entry=95000, sl=94000, tp1=96000, tp2=97000,
            size=1.0,
            order_id="ENTRY-1", sl_order_id="SL-OLD",
            tp1_order_id="TP1-1", tp2_order_id="TP2-1",
            tp1_hit=True,
        )
        mgr.positions.append(pos)

        mock_client.exchange.cancel_order.return_value = True
        mock_client.exchange.create_order.return_value = {"id": "SL-BE"}

        mgr._move_sl_to_breakeven(pos)

        assert pos.sl_order_id == "SL-BE"
        assert pos.sl == 95000
        mock_sleep.assert_not_called()
