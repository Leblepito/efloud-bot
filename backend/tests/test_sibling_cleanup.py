"""Unit tests for OrderManager._cancel_position_siblings — orphan order cleanup helper."""
from unittest.mock import MagicMock
import ccxt
import pytest

from exchange import BinanceClient, OrderManager, Position


@pytest.fixture
def mock_client():
    """Mock BinanceClient with stubbed exchange + helpers.

    Mirrors test_order_manager_v2.py fixture to keep test infrastructure consistent.
    """
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


@pytest.fixture
def position_with_all_orders():
    """A typical Position with all three sibling order IDs populated."""
    return Position(
        symbol="BTC/USDT", direction="LONG", entry=95000, sl=94000,
        tp1=96000, tp2=97000, size=1.0,
        sl_order_id="SL-1", tp1_order_id="TP1-1", tp2_order_id="TP2-1",
    )


class TestCancelPositionSiblings:
    """The helper must best-effort cancel SL + TP1 + TP2 reduceOnly orders.

    Behavior contract (spec §7.1):
    - Iterate [SL, TP1, TP2] in order; cancel each via ccxt cancel_order
    - Swallow ccxt.OrderNotFound (order already gone); count as 'missing'
    - Log + count other exceptions as 'failed'; never propagate
    - Return summary dict {cancelled: [...], failed: [...], missing: [...]}
    - Always log a single info line summarizing the result
    """

    def test_cancels_all_three_orders_when_present(
        self, mgr, mock_client, position_with_all_orders
    ):
        result = mgr._cancel_position_siblings(
            position_with_all_orders, "BTC/USDT:USDT", reason="TEST"
        )

        # All three cancel_order calls with the futures notation symbol
        assert mock_client.exchange.cancel_order.call_count == 3
        calls = mock_client.exchange.cancel_order.call_args_list
        assert calls[0].args == ("SL-1", "BTC/USDT:USDT")
        assert calls[1].args == ("TP1-1", "BTC/USDT:USDT")
        assert calls[2].args == ("TP2-1", "BTC/USDT:USDT")

        assert sorted(result["cancelled"]) == ["SL", "TP1", "TP2"]
        assert result["failed"] == []
        assert result["missing"] == []

    def test_skips_empty_order_ids(self, mgr, mock_client):
        """A Position with only SL+TP1 (no TP2) should only attempt 2 cancels."""
        pos = Position(
            symbol="BTC/USDT", direction="LONG", entry=95000, sl=94000,
            tp1=96000, tp2=97000, size=1.0,
            sl_order_id="SL-1", tp1_order_id="TP1-1", tp2_order_id="",
        )

        result = mgr._cancel_position_siblings(pos, "BTC/USDT:USDT", reason="TEST")

        # Only 2 cancel_order calls
        assert mock_client.exchange.cancel_order.call_count == 2
        assert sorted(result["cancelled"]) == ["SL", "TP1"]
        assert result["missing"] == ["TP2"]
        assert result["failed"] == []

    def test_all_missing_when_no_order_ids(self, mgr, mock_client):
        """A bare Position with no order IDs results in 0 cancel calls."""
        pos = Position(
            symbol="BTC/USDT", direction="LONG", entry=95000, sl=94000,
            tp1=96000, tp2=97000, size=1.0,
        )

        result = mgr._cancel_position_siblings(pos, "BTC/USDT:USDT", reason="TEST")

        assert mock_client.exchange.cancel_order.call_count == 0
        assert result["cancelled"] == []
        assert result["failed"] == []
        assert sorted(result["missing"]) == ["SL", "TP1", "TP2"]

    def test_swallows_order_not_found(
        self, mgr, mock_client, position_with_all_orders
    ):
        """If an order was already cancelled or filled, OrderNotFound must be silent."""
        # SL cancel succeeds; TP1 raises OrderNotFound; TP2 succeeds
        mock_client.exchange.cancel_order.side_effect = [
            None,
            ccxt.OrderNotFound("Order does not exist"),
            None,
        ]

        result = mgr._cancel_position_siblings(
            position_with_all_orders, "BTC/USDT:USDT", reason="TEST"
        )

        assert mock_client.exchange.cancel_order.call_count == 3
        assert sorted(result["cancelled"]) == ["SL", "TP2"]
        assert result["missing"] == ["TP1"]
        assert result["failed"] == []

    def test_logs_and_continues_on_generic_exception(
        self, mgr, mock_client, position_with_all_orders, caplog
    ):
        """Network/exchange errors on one cancel must not block the others."""
        import logging
        # SL succeeds; TP1 raises NetworkError; TP2 succeeds
        mock_client.exchange.cancel_order.side_effect = [
            None,
            ccxt.NetworkError("Connection reset"),
            None,
        ]

        with caplog.at_level(logging.WARNING):
            result = mgr._cancel_position_siblings(
                position_with_all_orders, "BTC/USDT:USDT", reason="TEST"
            )

        assert mock_client.exchange.cancel_order.call_count == 3
        assert sorted(result["cancelled"]) == ["SL", "TP2"]
        assert result["failed"] == ["TP1"]
        # Warning logged for the failed cancel
        warning_msgs = [r.message for r in caplog.records if r.levelno == logging.WARNING]
        assert any("failed to cancel TP1" in m for m in warning_msgs)


class TestReconcileFullClose:
    """When reconcile detects a position closed on Binance (size==0),
    it MUST cancel the sibling SL/TP orders before removing the
    local Position from state.

    Before this PR, reconcile silently removed the Position and left
    orphan reduceOnly orders on Binance Open Orders.
    """

    def test_full_close_cancels_all_siblings(self, mgr, mock_client):
        pos = Position(
            symbol="BTC/USDT", direction="LONG", entry=95000, sl=94000,
            tp1=96000, tp2=97000, size=1.0,
            sl_order_id="SL-1", tp1_order_id="TP1-1", tp2_order_id="TP2-1",
        )
        mgr.positions = [pos]

        # Exchange returns no open positions (fully closed)
        mock_client.get_open_positions.return_value = []
        # Open orders list also reflects the close (TP2 was the trigger)
        mock_client.exchange.fetch_open_orders.return_value = [
            {"id": "SL-1"},
            {"id": "TP1-1"},
        ]

        closed = mgr.reconcile()

        # Position recorded closed
        assert len(closed) == 1
        assert closed[0].symbol == "BTC/USDT"
        assert pos not in mgr.positions

        # All 3 sibling cancels attempted
        cancel_calls = mock_client.exchange.cancel_order.call_args_list
        cancelled_ids = [c.args[0] for c in cancel_calls]
        assert "SL-1" in cancelled_ids
        assert "TP1-1" in cancelled_ids
        assert "TP2-1" in cancelled_ids
        # Symbol is in CCXT futures notation
        for c in cancel_calls:
            assert c.args[1] == "BTC/USDT:USDT"

    def test_partial_close_does_not_trigger_cleanup(self, mgr, mock_client):
        """If position is still open on Binance (size > 0), no sibling cancels."""
        pos = Position(
            symbol="BTC/USDT", direction="LONG", entry=95000, sl=94000,
            tp1=96000, tp2=97000, size=1.0,
            sl_order_id="SL-1", tp1_order_id="TP1-1", tp2_order_id="TP2-1",
        )
        mgr.positions = [pos]

        # Still open with original size
        mock_client.get_open_positions.return_value = [
            {"symbol": "BTC/USDT", "contracts": 1.0}
        ]
        mock_client.exchange.fetch_open_orders.return_value = [
            {"id": "SL-1"}, {"id": "TP1-1"}, {"id": "TP2-1"},
        ]

        closed = mgr.reconcile()

        assert closed == []
        # No cancel_order calls
        assert mock_client.exchange.cancel_order.call_count == 0

    def test_full_close_with_already_cancelled_orders_does_not_propagate(
        self, mgr, mock_client
    ):
        """Even if every sibling cancel raises OrderNotFound, reconcile completes."""
        pos = Position(
            symbol="BTC/USDT", direction="LONG", entry=95000, sl=94000,
            tp1=96000, tp2=97000, size=1.0,
            sl_order_id="SL-1", tp1_order_id="TP1-1", tp2_order_id="TP2-1",
        )
        mgr.positions = [pos]

        mock_client.get_open_positions.return_value = []
        mock_client.exchange.fetch_open_orders.return_value = []
        # Every cancel raises OrderNotFound (already gone)
        mock_client.exchange.cancel_order.side_effect = ccxt.OrderNotFound(
            "Order does not exist"
        )

        closed = mgr.reconcile()  # MUST NOT raise

        assert len(closed) == 1
        assert pos not in mgr.positions
        # Attempted to cancel all 3
        assert mock_client.exchange.cancel_order.call_count == 3

    def test_multiple_positions_all_closed_in_one_cycle(self, mgr, mock_client):
        """If 3 positions all flip to closed in the same reconcile cycle,
        every one of them must have its sibling orders cancelled.

        Guards against a future loop-variable bug or batching shortcut that
        would only clean up the first close.
        """
        pos_a = Position(
            symbol="BTC/USDT", direction="LONG", entry=95000, sl=94000,
            tp1=96000, tp2=97000, size=1.0,
            sl_order_id="A-SL", tp1_order_id="A-TP1", tp2_order_id="A-TP2",
        )
        pos_b = Position(
            symbol="ETH/USDT", direction="SHORT", entry=2400, sl=2440,
            tp1=2360, tp2=2320, size=2.0,
            sl_order_id="B-SL", tp1_order_id="B-TP1", tp2_order_id="B-TP2",
        )
        pos_c = Position(
            symbol="SOL/USDT", direction="LONG", entry=150, sl=145,
            tp1=160, tp2=170, size=10.0,
            sl_order_id="C-SL", tp1_order_id="C-TP1", tp2_order_id="C-TP2",
        )
        mgr.positions = [pos_a, pos_b, pos_c]

        # All three closed on Binance
        mock_client.get_open_positions.return_value = []
        mock_client.exchange.fetch_open_orders.return_value = []

        closed = mgr.reconcile()

        assert len(closed) == 3
        assert mgr.positions == []

        # 9 total cancel attempts (3 positions × 3 sibling orders each)
        assert mock_client.exchange.cancel_order.call_count == 9
        cancelled_ids = [c.args[0] for c in mock_client.exchange.cancel_order.call_args_list]
        for expected in ["A-SL", "A-TP1", "A-TP2",
                         "B-SL", "B-TP1", "B-TP2",
                         "C-SL", "C-TP1", "C-TP2"]:
            assert expected in cancelled_ids

    def test_dry_run_reconcile_skips_entirely(self, mock_client):
        """Dry-run reconcile returns [] without touching exchange or local state.

        This pins the existing dry-run early-return guard at exchange/__init__.py
        ~line 566 (`if self.dry_run: return []`). The cleanup wiring added by
        this PR sits BELOW that guard, so dry-run cannot trigger any
        cancel_order calls — paper trading invariant.
        """
        mgr_dry = OrderManager(mock_client, dry_run=True)
        pos = Position(
            symbol="BTC/USDT", direction="LONG", entry=95000, sl=94000,
            tp1=96000, tp2=97000, size=1.0,
            sl_order_id="SL-1", tp1_order_id="TP1-1", tp2_order_id="TP2-1",
        )
        mgr_dry.positions = [pos]
        mock_client.get_open_positions.return_value = []

        closed = mgr_dry.reconcile()

        # Dry-run guard returns immediately
        assert closed == []
        # Position untouched in local state
        assert pos in mgr_dry.positions
        # No exchange interaction at all
        assert mock_client.get_open_positions.call_count == 0
        assert mock_client.exchange.cancel_order.call_count == 0


class TestFallbackCloseRefactor:
    """_fallback_close must continue to cancel all siblings after the
    refactor that replaces its inline loop with the new helper.

    This test pins the behavior so the refactor cannot silently change it.
    """

    def test_fallback_close_cancels_all_siblings(self, mgr, mock_client):
        pos = Position(
            symbol="BTC/USDT", direction="LONG", entry=95000, sl=94000,
            tp1=96000, tp2=97000, size=1.0,
            sl_order_id="SL-1", tp1_order_id="TP1-1", tp2_order_id="TP2-1",
        )
        mgr.positions = [pos]

        # Market close succeeds
        mock_client.exchange.create_order.return_value = {"id": "CLOSE-1"}

        mgr._fallback_close(pos, price=94500, reason="SL_POLL")

        # Position removed
        assert pos not in mgr.positions

        # Market close was placed
        market_calls = [
            c for c in mock_client.exchange.create_order.call_args_list
            if c.args[1] == "market"
        ]
        assert len(market_calls) == 1

        # All 3 sibling cancels attempted
        cancel_calls = mock_client.exchange.cancel_order.call_args_list
        cancelled_ids = [c.args[0] for c in cancel_calls]
        assert sorted(cancelled_ids) == ["SL-1", "TP1-1", "TP2-1"]
