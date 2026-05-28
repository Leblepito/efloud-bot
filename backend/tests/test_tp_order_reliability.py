"""Tests for TP order retry, TP1-fail-TP2-continues, and repair_missing_protection_orders.

These tests encode the fix for the 2026-05 SL/TP missing orders bug:
1. TP1 failure must NOT early-return — TP2 must still be attempted
2. TP orders retry on transient API errors (3 attempts, exponential backoff)
3. _repair_missing_protection_orders re-sends missing TP orders during reconcile
"""
from __future__ import annotations

import logging
from unittest.mock import MagicMock, call, patch

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
# BUG #1: TP1 failure must NOT prevent TP2 from being attempted
# ─────────────────────────────────────────────────────────────


class TestTP1FailureTP2Continues:
    """TP1 failure should not cause early return — TP2 must be attempted."""

    def test_tp1_fails_tp2_still_attempted_and_succeeds(self, mgr, mock_client):
        """When TP1 fails (non-transient), TP2 should still be placed."""
        mock_client.exchange.create_order.side_effect = [
            {"id": "ENTRY-1", "filled": 1.0},     # entry
            {"id": "SL-1"},                         # SL
            ValueError("TP1 insufficient margin"),  # TP1 fails (non-transient)
            {"id": "TP2-1"},                         # TP2 succeeds
        ]

        pos = mgr.open_position(
            "BTC/USDT", "LONG", 1.0,
            entry=95000, sl=94000, tp1=96000, tp2=97000,
        )

        assert pos is not None
        assert pos.tp1_order_id == ""      # TP1 failed
        assert pos.tp2_order_id == "TP2-1"  # TP2 succeeded
        assert pos.sl_order_id == "SL-1"   # SL present

        # Verify 4 create_order calls: entry, SL, TP1 (failed), TP2
        assert mock_client.exchange.create_order.call_count == 4
        order_types = [
            c.args[1] for c in mock_client.exchange.create_order.call_args_list
        ]
        assert order_types == [
            "market", "STOP_MARKET", "TAKE_PROFIT_MARKET", "TAKE_PROFIT_MARKET"
        ]

    def test_both_tp1_and_tp2_fail_position_still_tracked(self, mgr, mock_client):
        """When both TP1 and TP2 fail, position should still be tracked with SL."""
        mock_client.exchange.create_order.side_effect = [
            {"id": "ENTRY-1", "filled": 1.0},
            {"id": "SL-1"},
            ValueError("TP1 bad params"),   # TP1 fails
            ValueError("TP2 bad params"),   # TP2 fails
        ]

        pos = mgr.open_position(
            "BTC/USDT", "LONG", 1.0,
            entry=95000, sl=94000, tp1=96000, tp2=97000,
        )

        assert pos is not None
        assert pos.sl_order_id == "SL-1"
        assert pos.tp1_order_id == ""
        assert pos.tp2_order_id == ""
        assert len(mgr.positions) == 1


# ─────────────────────────────────────────────────────────────
# BUG #2: Retry with backoff for transient API errors
# ─────────────────────────────────────────────────────────────


class TestTPRetryWithBackoff:
    """TP orders should retry on transient errors."""

    @patch("exchange._time.sleep")
    def test_transient_error_retries_and_succeeds(self, mock_sleep, mgr, mock_client):
        """TP1 fails with timeout on attempt 1, succeeds on attempt 2."""
        mock_client.exchange.create_order.side_effect = [
            {"id": "ENTRY-1", "filled": 1.0},
            {"id": "SL-1"},
            TimeoutError("Request timed out"),  # TP1 attempt 1 — transient
            {"id": "TP1-1"},                     # TP1 attempt 2 — success
            {"id": "TP2-1"},                     # TP2 — success
        ]

        pos = mgr.open_position(
            "BTC/USDT", "LONG", 1.0,
            entry=95000, sl=94000, tp1=96000, tp2=97000,
        )

        assert pos is not None
        assert pos.tp1_order_id == "TP1-1"
        assert pos.tp2_order_id == "TP2-1"
        # Verify retry sleep was called (1.0s backoff)
        mock_sleep.assert_called_once_with(1.0)

    @patch("exchange._time.sleep")
    def test_non_transient_error_does_not_retry(self, mock_sleep, mgr, mock_client):
        """Non-transient error (e.g. bad params) fails immediately, no retry."""
        mock_client.exchange.create_order.side_effect = [
            {"id": "ENTRY-1", "filled": 1.0},
            {"id": "SL-1"},
            ValueError("Insufficient margin"),  # TP1 — not transient
            {"id": "TP2-1"},                     # TP2
        ]

        pos = mgr.open_position(
            "BTC/USDT", "LONG", 1.0,
            entry=95000, sl=94000, tp1=96000, tp2=97000,
        )

        assert pos is not None
        assert pos.tp1_order_id == ""   # Failed, no retry
        assert pos.tp2_order_id == "TP2-1"
        mock_sleep.assert_not_called()  # No retry sleep

    @patch("exchange._time.sleep")
    def test_three_transient_failures_exhausts_retries(self, mock_sleep, mgr, mock_client):
        """3 consecutive transient errors exhaust retries, TP1 stays empty."""
        mock_client.exchange.create_order.side_effect = [
            {"id": "ENTRY-1", "filled": 1.0},
            {"id": "SL-1"},
            TimeoutError("timed out 1"),   # TP1 attempt 1
            TimeoutError("timed out 2"),   # TP1 attempt 2
            TimeoutError("timed out 3"),   # TP1 attempt 3 — exhausted
            {"id": "TP2-1"},               # TP2 — independent, succeeds
        ]

        pos = mgr.open_position(
            "BTC/USDT", "LONG", 1.0,
            entry=95000, sl=94000, tp1=96000, tp2=97000,
        )

        assert pos is not None
        assert pos.tp1_order_id == ""
        assert pos.tp2_order_id == "TP2-1"
        # 2 retry sleeps (after attempt 1 and 2, not after exhausted attempt 3)
        assert mock_sleep.call_count == 2

    def test_is_transient_error_detection(self):
        """_is_transient_error correctly classifies error types."""
        assert OrderManager._is_transient_error(
            TimeoutError("Request timed out")
        ) is True
        assert OrderManager._is_transient_error(
            RuntimeError("binance {-1001: Disconnected}")
        ) is True
        assert OrderManager._is_transient_error(
            RuntimeError("rate limit exceeded")
        ) is True
        assert OrderManager._is_transient_error(
            RuntimeError("503 Service Unavailable")
        ) is True
        # Non-transient
        assert OrderManager._is_transient_error(
            ValueError("Insufficient margin")
        ) is False
        assert OrderManager._is_transient_error(
            RuntimeError("Invalid symbol BTC/WRONG")
        ) is False


# ─────────────────────────────────────────────────────────────
# BUG #3: _repair_missing_protection_orders
# ─────────────────────────────────────────────────────────────


class TestRepairMissingProtectionOrders:
    """reconcile should detect and re-send missing TP orders."""

    def test_repair_sends_missing_tp1(self, mgr, mock_client, caplog):
        """Position with empty tp1_order_id gets repaired during reconcile."""
        caplog.set_level(logging.CRITICAL, logger="efloud.exchange")

        # Pre-populate a position with missing TP1
        pos = Position(
            symbol="BTC/USDT", direction="LONG",
            entry=95000, sl=94000, tp1=96000, tp2=97000,
            size=1.0,
            order_id="ENTRY-1", sl_order_id="SL-1",
            tp1_order_id="", tp2_order_id="TP2-1",
        )
        mgr.positions.append(pos)

        # Mock repair order success
        mock_client.exchange.create_order.return_value = {"id": "TP1-REPAIR"}

        mgr._repair_missing_protection_orders(bn_order_ids={"SL-1", "TP2-1"})

        assert pos.tp1_order_id == "TP1-REPAIR"
        # Verify order was placed with correct params
        repair_call = mock_client.exchange.create_order.call_args
        assert repair_call.args[1] == "TAKE_PROFIT_MARKET"
        assert repair_call.kwargs["params"]["stopPrice"] == 96000
        assert repair_call.kwargs["params"]["reduceOnly"] is True

    def test_repair_sends_missing_tp2(self, mgr, mock_client):
        """Position with empty tp2_order_id gets repaired."""
        pos = Position(
            symbol="ETH/USDT", direction="SHORT",
            entry=2400, sl=2440, tp1=2360, tp2=2320,
            size=2.0,
            order_id="ENTRY-1", sl_order_id="SL-1",
            tp1_order_id="TP1-1", tp2_order_id="",
        )
        mgr.positions.append(pos)

        mock_client.exchange.create_order.return_value = {"id": "TP2-REPAIR"}

        mgr._repair_missing_protection_orders(bn_order_ids={"SL-1", "TP1-1"})

        assert pos.tp2_order_id == "TP2-REPAIR"

    def test_repair_skips_single_target_tp2(self, mgr, mock_client):
        """Single-target position (tp2=None) should NOT attempt TP2 repair."""
        pos = Position(
            symbol="SOL/USDT", direction="LONG",
            entry=100, sl=95, tp1=110, tp2=None,
            size=1.0,
            order_id="ENTRY-1", sl_order_id="SL-1",
            tp1_order_id="TP1-1", tp2_order_id="",
        )
        mgr.positions.append(pos)

        mgr._repair_missing_protection_orders(bn_order_ids=set())

        # No create_order calls since TP1 is already present and TP2 is single-target
        mock_client.exchange.create_order.assert_not_called()

    def test_repair_skips_tp1_hit_positions(self, mgr, mock_client):
        """After TP1 hit, don't repair TP1 (already filled) or TP2 (lifecycle manages)."""
        pos = Position(
            symbol="BTC/USDT", direction="LONG",
            entry=95000, sl=95000, tp1=96000, tp2=97000,
            size=1.0,
            order_id="ENTRY-1", sl_order_id="SL-BE",
            tp1_order_id="", tp2_order_id="TP2-1",
            tp1_hit=True,
        )
        mgr.positions.append(pos)

        mgr._repair_missing_protection_orders(bn_order_ids=set())

        # No repair attempted — TP1 already hit
        mock_client.exchange.create_order.assert_not_called()

    def test_repair_handles_failed_repair_gracefully(self, mgr, mock_client):
        """Failed repair attempt doesn't crash; tp1_order_id stays empty."""
        pos = Position(
            symbol="BTC/USDT", direction="LONG",
            entry=95000, sl=94000, tp1=96000, tp2=97000,
            size=1.0,
            order_id="ENTRY-1", sl_order_id="SL-1",
            tp1_order_id="", tp2_order_id="TP2-1",
        )
        mgr.positions.append(pos)

        # All repair attempts fail
        mock_client.exchange.create_order.side_effect = ValueError("bad params")

        mgr._repair_missing_protection_orders(bn_order_ids=set())

        assert pos.tp1_order_id == ""  # Still empty, but no crash
