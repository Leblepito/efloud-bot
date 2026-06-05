"""PR #102 fix: Sentinel guard across all reconciliation / exit / cleanup sites.

Risk-ops review (https://github.com/Leblepito/efloud-bot/pull/102#issuecomment-4565448456)
identified 3 call-sites where the existing "truthy" check would misinterpret
the "UNREACHABLE" sentinel as a real Binance order id:

1. reconcile() TP1 fill detection (line ~1092):
   `if pos.tp1_order_id and not pos.tp1_hit:` — "UNREACHABLE" is truthy,
   `pos.tp1_order_id not in bn_order_ids` evaluates True → FALSE TP1 HIT
   → SL moved to break-even → position unprotected if price drops.

2. _estimate_exit_price() (line ~1277):
   `if pos.tp2_order_id and pos.tp2_order_id not in order_ids:` —
   returns pos.tp2 as exit price when in reality no order was placed.

3. _cancel_position_siblings() (line ~1163):
   `if not oid:` treats "UNREACHABLE" as real, tries cancel_order("UNREACHABLE")
   → wasteful API call, OrderNotFound caught, still works but noisy.

Fix: _is_real_oid(oid) helper → guards all 3 sites.
"""
from __future__ import annotations

import logging
from unittest.mock import MagicMock

import pytest

import ccxt as _ccxt
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
# Call-site #1: reconcile — no false TP1 hit on sentinel
# ─────────────────────────────────────────────────────────────


class TestSentinelGuardReconcileTP1:
    """reconcile must NOT declare TP1 filled when tp1_order_id is 'UNREACHABLE'."""

    def test_unreachable_tp1_does_not_trigger_breakeven_move(self, mgr, mock_client):
        """Position with tp1_order_id='UNREACHABLE' stays open, no BE move."""
        pos = Position(
            symbol="LINK/USDT", direction="SHORT",
            entry=23.0, sl=23.5, tp1=22.5, tp2=22.0,
            size=100.0,
            order_id="ENTRY-1", sl_order_id="SL-1",
            tp1_order_id="UNREACHABLE",
            tp2_order_id="TP2-1",
        )
        mgr.positions = [pos]

        # Binance still shows SL + TP2 as live orders — no fills.
        mock_client.get_open_positions.return_value = [
            {"symbol": "LINK/USDT:USDT", "contracts": 100.0, "side": "short"}
        ]
        mock_client.exchange.fetch_open_orders.return_value = [
            {"id": "SL-1"},
            {"id": "TP2-1"},
        ]
        mock_client.exchange.fapiPrivateGetOpenAlgoOrders.return_value = [
            {"algoId": "SL-1"},
            {"algoId": "TP2-1"},
        ]
        # No repair order should be placed (sentinel present)
        mock_client.exchange.create_order.return_value = {"id": "NOOP"}

        closed = mgr.reconcile()

        # Position stays open (no close declared)
        assert len(closed) == 0
        assert len(mgr.positions) == 1
        # tp1_hit NOT flipped → _move_sl_to_breakeven never called
        assert pos.tp1_hit is False
        assert pos.sl == 23.5  # Still at original SL, not at entry
        # Sentinel persists for next cycle
        assert pos.tp1_order_id == "UNREACHABLE"


# ─────────────────────────────────────────────────────────────
# Call-site #2: _estimate_exit_price — no phantom exit on sentinel
# ─────────────────────────────────────────────────────────────


class TestSentinelGuardEstimateExit:
    """_estimate_exit_price must not report a phantom TP2/TP1 hit when sentinel."""

    def test_unreachable_tp2_is_not_interpreted_as_tp2_hit(self, mgr, mock_client):
        """tp2_order_id='UNREACHABLE' → should NOT return pos.tp2 as exit."""
        pos = Position(
            symbol="LINK/USDT", direction="SHORT",
            entry=23.0, sl=23.5, tp1=22.5, tp2=22.0,
            size=100.0,
            order_id="ENTRY-1", sl_order_id="SL-1",
            tp1_order_id="TP1-1",
            tp2_order_id="UNREACHABLE",  # sentinel
        )
        # All real (non-sentinel) orders still present on Binance (algo-inclusive set).
        bn_order_ids = {"SL-1", "TP1-1"}  # TP2 never existed — "UNREACHABLE" was never real
        mock_client.get_price.return_value = 22.75  # current market

        exit_price = mgr._estimate_exit_price(pos, bn_order_ids)

        # Must fall through to current market price (fallback), NOT pos.tp2
        assert exit_price == 22.75
        assert exit_price != 22.0  # NOT pos.tp2

    def test_unreachable_tp1_is_not_interpreted_as_tp1_hit(self, mgr, mock_client):
        """tp1_order_id='UNREACHABLE' → should NOT return pos.tp1 as exit."""
        pos = Position(
            symbol="LINK/USDT", direction="SHORT",
            entry=23.0, sl=23.5, tp1=22.5, tp2=22.0,
            size=100.0,
            order_id="ENTRY-1", sl_order_id="SL-1",
            tp1_order_id="UNREACHABLE",
            tp2_order_id="UNREACHABLE",
        )
        bn_order_ids = {"SL-1"}
        mock_client.get_price.return_value = 22.80

        exit_price = mgr._estimate_exit_price(pos, bn_order_ids)

        # Must fall through to market price, not pos.tp1 or pos.tp2
        assert exit_price == 22.80


class TestEstimateExitPriceAlgoInclusive:
    """_estimate_exit_price must use the algo-inclusive id SET and gate on fetch_ok.

    CRITICAL regression: pos.sl/tp1/tp2_order_id are server-side ALGO ids. Reconcile
    used to pass the regular-orders-only list (bn_orders_raw), so every algo leg
    looked 'missing' → every close mis-attributed to TP2 (an SL-hit loss logged as a
    TP2 profit), feeding phantom PnL to the drawdown breaker.
    """

    def _pos(self):
        return Position(
            symbol="BTC/USDT", direction="SHORT",
            entry=100.0, sl=110.0, tp1=95.0, tp2=80.0, size=1.0,
            order_id="ENTRY-1", sl_order_id="SL-algo",
            tp1_order_id="TP1-algo", tp2_order_id="TP2-algo",
        )

    def test_sl_hit_returns_sl_not_tp2_when_tp2_still_live(self, mgr, mock_client):
        # SL fired (its algoId gone); TP1/TP2 algoIds still on the book.
        pos = self._pos()
        bn_order_ids = {"TP1-algo", "TP2-algo"}
        mock_client.get_price.return_value = 109.5
        exit_price = mgr._estimate_exit_price(pos, bn_order_ids)
        assert exit_price == pos.sl     # 110.0 — correct attribution
        assert exit_price != pos.tp2    # NOT 80.0 (the pre-fix phantom profit)

    def test_tp2_hit_returns_tp2(self, mgr, mock_client):
        pos = self._pos()
        bn_order_ids = {"SL-algo", "TP1-algo"}  # TP2 algoId gone → TP2 hit
        exit_price = mgr._estimate_exit_price(pos, bn_order_ids)
        assert exit_price == pos.tp2    # 80.0

    def test_failed_fetch_falls_through_to_market_not_phantom_tp2(self, mgr, mock_client):
        # A failed regular/algo fetch → set unreliable → must NOT attribute a leg.
        pos = self._pos()
        mock_client.get_price.return_value = 101.0
        exit_price = mgr._estimate_exit_price(pos, set(), fetch_ok=False)
        assert exit_price == 101.0      # current market price
        assert exit_price != pos.tp2    # NOT 80.0 phantom TP2


# ─────────────────────────────────────────────────────────────
# Call-site #3: _cancel_position_siblings — no wasteful cancel on sentinel
# ─────────────────────────────────────────────────────────────


class TestSentinelGuardCancelSiblings:
    """_cancel_position_siblings must treat sentinel as missing, not attempt cancel."""

    def test_unreachable_sl_treated_as_missing_no_cancel_call(self, mgr, mock_client):
        """sl_order_id='UNREACHABLE' → counted as missing, no cancel_order call."""
        pos = Position(
            symbol="LINK/USDT", direction="SHORT",
            entry=23.0, sl=23.5, tp1=22.5, tp2=22.0,
            size=100.0,
            order_id="ENTRY-1", sl_order_id="UNREACHABLE",
            tp1_order_id="TP1-1",
            tp2_order_id="TP2-1",
        )
        ccxt_sym = "LINK/USDT:USDT"

        result = mgr._cancel_position_siblings(pos, ccxt_sym, reason="TEST")

        # SL must be in "missing" bucket, NOT in "cancelled" or "failed"
        assert "SL" in result["missing"]
        assert "SL" not in result["cancelled"]
        assert "SL" not in result["failed"]
        # cancel_order was NOT called with "UNREACHABLE" id
        for call in mock_client.exchange.cancel_order.call_args_list:
            args, kwargs = call
            assert args[0] != "UNREACHABLE", "Should not attempt to cancel sentinel id"

    def test_unreachable_tp1_treated_as_missing(self, mgr, mock_client):
        """tp1_order_id='UNREACHABLE' → counted as missing."""
        pos = Position(
            symbol="LINK/USDT", direction="SHORT",
            entry=23.0, sl=23.5, tp1=22.5, tp2=22.0,
            size=100.0,
            order_id="ENTRY-1", sl_order_id="SL-1",
            tp1_order_id="UNREACHABLE",
            tp2_order_id="TP2-1",
        )
        result = mgr._cancel_position_siblings(pos, "LINK/USDT:USDT", reason="TEST")

        assert "TP1" in result["missing"]
        assert "TP1" not in result["cancelled"]

    def test_real_order_ids_still_cancel_normally(self, mgr, mock_client):
        """Real truthy non-sentinel order IDs must still be cancelled."""
        pos = Position(
            symbol="LINK/USDT", direction="SHORT",
            entry=23.0, sl=23.5, tp1=22.5, tp2=22.0,
            size=100.0,
            order_id="ENTRY-1", sl_order_id="SL-1",
            tp1_order_id="TP1-1",
            tp2_order_id="TP2-1",
        )
        result = mgr._cancel_position_siblings(pos, "LINK/USDT:USDT", reason="TEST")

        assert set(result["cancelled"]) == {"SL", "TP1", "TP2"}
        assert mock_client.exchange.cancel_order.call_count == 3


# ─────────────────────────────────────────────────────────────
# Helper: _is_real_oid contract
# ─────────────────────────────────────────────────────────────


class TestIsRealOid:
    """_is_real_oid(oid) helper contract."""

    def test_empty_string_is_not_real(self):
        assert OrderManager._is_real_oid("") is False

    def test_none_is_not_real(self):
        assert OrderManager._is_real_oid(None) is False

    def test_unreachable_is_not_real(self):
        assert OrderManager._is_real_oid("UNREACHABLE") is False

    def test_real_order_id_is_real(self):
        assert OrderManager._is_real_oid("SL-123") is True
        assert OrderManager._is_real_oid("TP1-987654321") is True
        # Edge case: numeric-looking ids
        assert OrderManager._is_real_oid("3000001670196915") is True


# ─────────────────────────────────────────────────────────────
# Integration: full cycle after sentinel set
# ─────────────────────────────────────────────────────────────


class TestSentinelFullCycle:
    """End-to-end: sentinel set → subsequent cycles skip cleanly."""

    def test_reconcile_cycle_after_sentinel_set_is_quiet(
        self, mgr, mock_client, caplog
    ):
        """After sentinel set, subsequent reconcile cycles must NOT:
        - Re-attempt TP repair
        - Flag TP1 hit
        - Move SL to break-even
        """
        caplog.set_level(logging.INFO, logger="efloud.exchange")

        pos = Position(
            symbol="LINK/USDT", direction="SHORT",
            entry=23.0, sl=23.5, tp1=22.5, tp2=22.0,
            size=100.0,
            order_id="ENTRY-1", sl_order_id="SL-1",
            tp1_order_id="UNREACHABLE",  # set by prior cycle
            tp2_order_id="TP2-1",
        )
        mgr.positions = [pos]

        # Binance still shows SL + TP2 live
        mock_client.get_open_positions.return_value = [
            {"symbol": "LINK/USDT:USDT", "contracts": 100.0, "side": "short"}
        ]
        mock_client.exchange.fetch_open_orders.return_value = [
            {"id": "SL-1"}, {"id": "TP2-1"}
        ]
        mock_client.exchange.fapiPrivateGetOpenAlgoOrders.return_value = [
            {"algoId": "SL-1"}, {"algoId": "TP2-1"}
        ]

        closed = mgr.reconcile()

        # No closes
        assert len(closed) == 0
        # No repair attempt (no create_order called from repair path)
        # (only other calls allowed are from orphan protection)
        for call in mock_client.exchange.create_order.call_args_list:
            args, kwargs = call
            assert args[1] not in ("TAKE_PROFIT_MARKET", "STOP_MARKET"), \
                f"Should not attempt protection order repair, got: {call}"
        # tp1_hit NOT flipped
        assert pos.tp1_hit is False
        # SL unchanged (no BE move)
        assert pos.sl == 23.5
        # Sentinel persists
        assert pos.tp1_order_id == "UNREACHABLE"
        # No reconcile spam about tp_unreachable (already handled once)
        assert not any(
            "tp_unreachable" in msg
            for msg in caplog.text.splitlines()
        ), "tp_unreachable should only log ONCE when sentinel is set, not on every cycle"
