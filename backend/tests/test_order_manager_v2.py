"""Unit tests for OrderManager v2.2 — server-side TP/SL + reconciliation."""
from unittest.mock import MagicMock, patch

import pytest

from exchange import BinanceClient, OrderManager, Position


@pytest.fixture
def mock_client():
    """Mock BinanceClient with stubbed exchange + helpers."""
    client = MagicMock(spec=BinanceClient)
    client.exchange = MagicMock()
    client.market_type = "futures"
    client.testnet = True
    # Real BinanceClient.to_ccxt_symbol behavior — futures appends ':USDT'
    client.to_ccxt_symbol.side_effect = lambda s: (
        s if ":" in s or client.market_type != "futures" else f"{s}:USDT"
    )
    return client


@pytest.fixture
def mgr(mock_client):
    """OrderManager in live mode (dry_run=False) so we hit the server-side path."""
    return OrderManager(mock_client, dry_run=False)


class TestOpenPositionServerSideTPSL:
    """open_position must place 4 orders: market entry + SL + TP1 + TP2."""

    def test_long_places_four_orders(self, mgr, mock_client):
        # Arrange — exchange returns sequential order IDs
        mock_client.exchange.create_order.side_effect = [
            {"id": "ENTRY-1"},
            {"id": "SL-1"},
            {"id": "TP1-1"},
            {"id": "TP2-1"},
        ]

        # Act
        pos = mgr.open_position(
            symbol="BTC/USDT", direction="LONG",
            size=1.0, entry=95000, sl=94000,
            tp1=96000, tp2=97000,
        )

        # Assert
        assert pos is not None
        assert pos.order_id == "ENTRY-1"
        assert pos.sl_order_id == "SL-1"
        assert pos.tp1_order_id == "TP1-1"
        assert pos.tp2_order_id == "TP2-1"

        # 4 orders placed
        assert mock_client.exchange.create_order.call_count == 4

        # Inspect each call
        calls = mock_client.exchange.create_order.call_args_list

        # 1st: market buy — futures notation 'BTC/USDT:USDT'
        assert calls[0].args == ("BTC/USDT:USDT", "market", "buy", 1.0)

        # 2nd: STOP_MARKET sell (reverse side, full size, reduceOnly)
        assert calls[1].args[0] == "BTC/USDT:USDT"
        assert calls[1].args[1] == "STOP_MARKET"
        assert calls[1].args[2] == "sell"
        assert calls[1].args[3] == 1.0
        assert calls[1].kwargs["params"]["stopPrice"] == 94000
        assert calls[1].kwargs["params"]["reduceOnly"] is True

        # 3rd: TAKE_PROFIT_MARKET sell (half size, TP1, reduceOnly)
        assert calls[2].args[1] == "TAKE_PROFIT_MARKET"
        assert calls[2].args[2] == "sell"
        assert calls[2].args[3] == 0.5  # half
        assert calls[2].kwargs["params"]["stopPrice"] == 96000

        # 4th: TAKE_PROFIT_MARKET sell (other half, TP2)
        assert calls[3].args[1] == "TAKE_PROFIT_MARKET"
        assert calls[3].args[3] == 0.5  # other half
        assert calls[3].kwargs["params"]["stopPrice"] == 97000

    def test_short_uses_buy_for_close_orders(self, mgr, mock_client):
        mock_client.exchange.create_order.side_effect = [
            {"id": "E"}, {"id": "S"}, {"id": "T1"}, {"id": "T2"},
        ]

        pos = mgr.open_position(
            symbol="ETH/USDT", direction="SHORT",
            size=2.0, entry=2400, sl=2440,
            tp1=2360, tp2=2320,
        )

        assert pos.direction == "SHORT"
        calls = mock_client.exchange.create_order.call_args_list
        # Entry order: market sell
        assert calls[0].args[2] == "sell"
        # All close-side orders: buy (reverse)
        assert calls[1].args[2] == "buy"  # SL
        assert calls[2].args[2] == "buy"  # TP1
        assert calls[3].args[2] == "buy"  # TP2

    def test_dry_run_skips_orders(self, mock_client):
        mgr_dry = OrderManager(mock_client, dry_run=True)
        pos = mgr_dry.open_position("BTC/USDT", "LONG", 1.0, 95000, 94000, 96000, 97000)
        assert pos is not None
        # No exchange.create_order calls in dry run
        mock_client.exchange.create_order.assert_not_called()

    def test_event_callback_fires_on_open(self, mock_client):
        events = []
        mgr_cb = OrderManager(
            mock_client, dry_run=False,
            on_position_change=lambda evt, pos: events.append((evt, pos.symbol))
        )
        mock_client.exchange.create_order.side_effect = [
            {"id": "E"}, {"id": "S"}, {"id": "T1"}, {"id": "T2"},
        ]
        mgr_cb.open_position("BTC/USDT", "LONG", 1.0, 95000, 94000, 96000, 97000)
        assert events == [("position_opened", "BTC/USDT")]


class TestReconciliation:
    """reconcile() must detect closes + TP1 fills from Binance state."""

    def test_position_closed_when_missing_from_binance(self, mgr, mock_client):
        # Arrange: 1 local position, Binance reports no positions
        pos = Position(symbol="BTC/USDT", direction="LONG", entry=95000,
                       sl=94000, tp1=96000, tp2=97000, size=1.0,
                       sl_order_id="SL-1", tp1_order_id="TP1-1",
                       tp2_order_id="TP2-1")
        mgr.positions = [pos]
        mock_client.get_open_positions.return_value = []
        # TP2 order'ı listeden eksik = filled
        mock_client.exchange.fetch_open_orders.return_value = [
            {"id": "SL-1"},  # SL hâlâ duruyor
            {"id": "TP1-1"}, # TP1 hâlâ duruyor
            # TP2-1 yok = filled
        ]

        # Act
        closed = mgr.reconcile()

        # Assert
        assert len(closed) == 1
        assert closed[0].exit_reason == "RECONCILED"
        assert closed[0].exit_price == 97000  # TP2 fiyatına eşit
        assert pos not in mgr.positions
        assert pos in mgr.closed_positions

    def test_tp1_hit_detected_and_sl_moved_to_breakeven(self, mgr, mock_client):
        pos = Position(symbol="BTC/USDT", direction="LONG", entry=95000,
                       sl=94000, tp1=96000, tp2=97000, size=1.0,
                       sl_order_id="SL-1", tp1_order_id="TP1-1",
                       tp2_order_id="TP2-1")
        mgr.positions = [pos]

        # Binance'de pozisyon hâlâ açık (yarı kapanmış olsa bile contracts > 0)
        mock_client.get_open_positions.return_value = [
            {"symbol": "BTC/USDT", "contracts": 0.5}
        ]
        # TP1-1 listeden eksik = filled
        mock_client.exchange.fetch_open_orders.return_value = [
            {"id": "SL-1"},
            {"id": "TP2-1"},
        ]
        # New SL order (break-even)
        mock_client.exchange.create_order.return_value = {"id": "SL-NEW"}

        # Act
        closed = mgr.reconcile()

        # Assert
        assert len(closed) == 0  # pozisyon hâlâ açık
        assert pos.tp1_hit is True
        assert pos.sl == pos.entry  # break-even'a kaymış
        assert pos.sl_order_id == "SL-NEW"

        # Eski SL cancel edildi
        mock_client.exchange.cancel_order.assert_called_once_with("SL-1", "BTC/USDT:USDT")

        # Yeni SL @ entry yerleştirildi
        mock_client.exchange.create_order.assert_called_once()
        new_sl_call = mock_client.exchange.create_order.call_args
        assert new_sl_call.args[1] == "STOP_MARKET"
        assert new_sl_call.args[2] == "sell"
        assert new_sl_call.args[3] == 0.5  # remaining half
        assert new_sl_call.kwargs["params"]["stopPrice"] == 95000  # entry

    def test_dry_run_reconcile_is_noop(self, mock_client):
        mgr_dry = OrderManager(mock_client, dry_run=True)
        mgr_dry.positions = [
            Position("BTC/USDT", "LONG", 95000, 94000, 96000, 97000, 1.0)
        ]
        result = mgr_dry.reconcile()
        assert result == []
        mock_client.get_open_positions.assert_not_called()


class TestKillSwitch:
    """kill_switch() must close all open positions + cancel pending orders."""

    def test_kill_switch_closes_all(self, mgr, mock_client):
        mgr.positions = [
            Position("BTC/USDT", "LONG", 95000, 94000, 96000, 97000, 1.0,
                     sl_order_id="SL1", tp1_order_id="T1A", tp2_order_id="T2A"),
            Position("ETH/USDT", "SHORT", 2400, 2440, 2360, 2320, 2.0,
                     sl_order_id="SL2", tp1_order_id="T1B", tp2_order_id="T2B"),
        ]
        mock_client.get_price.side_effect = [95500, 2380]

        count = mgr.kill_switch()

        assert count == 2
        assert mgr.positions == []
        assert len(mgr.closed_positions) == 2
        assert all(p.exit_reason == "KILL_SWITCH" for p in mgr.closed_positions)


class TestPnLCalculation:
    """_record_close must compute pnl_usdt correctly for both directions."""

    def test_long_winning_trade(self, mgr, mock_client):
        pos = Position("BTC/USDT", "LONG", 95000, 94000, 96000, 97000, 1.0)
        mgr.positions.append(pos)
        mgr._record_close(pos, exit_price=97000, reason="TP2")
        assert pos.pnl_usdt == pytest.approx(2000.0)  # (97000-95000)*1

    def test_short_winning_trade(self, mgr, mock_client):
        pos = Position("ETH/USDT", "SHORT", 2400, 2440, 2360, 2320, 2.0)
        mgr.positions.append(pos)
        mgr._record_close(pos, exit_price=2320, reason="TP2")
        assert pos.pnl_usdt == pytest.approx(160.0)  # (2400-2320)*2

    def test_long_losing_trade(self, mgr, mock_client):
        pos = Position("BTC/USDT", "LONG", 95000, 94000, 96000, 97000, 1.0)
        mgr.positions.append(pos)
        mgr._record_close(pos, exit_price=94000, reason="SL")
        assert pos.pnl_usdt == pytest.approx(-1000.0)  # (94000-95000)*1
