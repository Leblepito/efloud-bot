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

    def test_position_kept_when_binance_returns_ccxt_futures_symbol_format(
        self, mgr, mock_client
    ):
        """Reconcile must compare symbols regardless of CCXT futures notation.

        CCXT's fetch_positions returns symbols with the contract suffix
        (e.g. 'FIL/USDT:USDT'), while bot positions are tracked in slash
        form ('FIL/USDT'). Without normalization, the bot mistakenly thinks
        every position is closed and emits false RECONCILED events.
        Live observed 2026-05-08: FIL+RENDER positions falsely reported as
        closed with PnL=+$89 RECONCILED while still open on Binance.
        """
        pos = Position(
            symbol="FIL/USDT", direction="LONG", entry=1.10, sl=1.07,
            tp1=1.16, tp2=1.15, size=930.0,
            sl_order_id="SL-1", tp1_order_id="TP1-1", tp2_order_id="TP2-1",
        )
        mgr.positions = [pos]

        # Production reality: CCXT futures notation (not seen in old tests)
        mock_client.get_open_positions.return_value = [
            {"symbol": "FIL/USDT:USDT", "contracts": 930.0}
        ]
        mock_client.exchange.fetch_open_orders.return_value = [
            {"id": "SL-1"}, {"id": "TP1-1"}, {"id": "TP2-1"},
        ]

        closed = mgr.reconcile()

        assert closed == [], "Position falsely reconciled despite being open on Binance"
        assert pos in mgr.positions, "Position incorrectly removed from local list"

    def test_dry_run_reconcile_is_noop(self, mock_client):
        mgr_dry = OrderManager(mock_client, dry_run=True)
        mgr_dry.positions = [
            Position("BTC/USDT", "LONG", 95000, 94000, 96000, 97000, 1.0)
        ]
        result = mgr_dry.reconcile()
        assert result == []
        mock_client.get_open_positions.assert_not_called()

    def test_orphan_position_detected_and_warned(self, mgr, mock_client, caplog):
        """When exchange has positions not tracked locally, reconcile must
        emit a structured ORPHAN warning so an operator can investigate.

        Background: 2026-05-09 LTC/ADA incident — bot had 3 of 5 exchange
        positions in local state. Without orphan detection, the missing
        positions were invisible to ops monitoring; they had to be
        discovered by manually diffing exchange vs state.

        Behavior contract:
        - Orphan symbols MUST appear in WARNING-level logs with the
          'ORPHAN POSITION DETECTED' marker so log-search alerts fire.
        - Bot MUST NOT auto-import or auto-manage the orphan (no SL/TP
          context for an unknown trade).
        - Existing tracked positions MUST stay untouched.
        """
        import logging
        # Local state: only BTC tracked
        tracked = Position(symbol="BTC/USDT", direction="LONG", entry=95000,
                           sl=94000, tp1=96000, tp2=97000, size=1.0,
                           sl_order_id="SL-1", tp1_order_id="TP1-1",
                           tp2_order_id="TP2-1")
        mgr.positions = [tracked]

        # Exchange reports: BTC (tracked) + ETH (orphan) + LTC (orphan)
        mock_client.get_open_positions.return_value = [
            {"symbol": "BTC/USDT:USDT", "contracts": 1.0,
             "side": "long", "entryPrice": 95000, "unrealizedPnl": 0.0},
            {"symbol": "ETH/USDT:USDT", "contracts": 2.0,
             "side": "long", "entryPrice": 2400, "unrealizedPnl": 50.0},
            {"symbol": "LTC/USDT:USDT", "contracts": 55.434,
             "side": "long", "entryPrice": 58.18, "unrealizedPnl": 14.19},
        ]
        mock_client.exchange.fetch_open_orders.return_value = [
            {"id": "SL-1"}, {"id": "TP1-1"}, {"id": "TP2-1"},
        ]

        with caplog.at_level(logging.WARNING, logger="efloud.exchange"):
            closed = mgr.reconcile()

        # No closes — BTC still tracked, ETH+LTC are orphans not tracked
        assert closed == []
        # Tracked position untouched
        assert tracked in mgr.positions
        assert len(mgr.positions) == 1
        # Both orphans logged with the ORPHAN marker
        warning_messages = [r.message for r in caplog.records if r.levelname == "WARNING"]
        eth_warned = any("ORPHAN POSITION DETECTED" in m and "ETH/USDT" in m for m in warning_messages)
        ltc_warned = any("ORPHAN POSITION DETECTED" in m and "LTC/USDT" in m for m in warning_messages)
        assert eth_warned, f"ETH orphan not warned. Logs: {warning_messages}"
        assert ltc_warned, f"LTC orphan not warned. Logs: {warning_messages}"

    def test_no_orphan_warning_when_all_positions_tracked(self, mgr, mock_client, caplog):
        """When state matches exchange exactly, no orphan warning fires."""
        import logging
        pos = Position(symbol="BTC/USDT", direction="LONG", entry=95000,
                       sl=94000, tp1=96000, tp2=97000, size=1.0,
                       sl_order_id="SL-1", tp1_order_id="TP1-1",
                       tp2_order_id="TP2-1")
        mgr.positions = [pos]
        mock_client.get_open_positions.return_value = [
            {"symbol": "BTC/USDT:USDT", "contracts": 1.0,
             "side": "long", "entryPrice": 95000, "unrealizedPnl": 0.0},
        ]
        mock_client.exchange.fetch_open_orders.return_value = [
            {"id": "SL-1"}, {"id": "TP1-1"}, {"id": "TP2-1"},
        ]

        with caplog.at_level(logging.WARNING, logger="efloud.exchange"):
            mgr.reconcile()

        orphan_warnings = [r.message for r in caplog.records
                           if r.levelname == "WARNING" and "ORPHAN" in r.message]
        assert orphan_warnings == [], f"Unexpected orphan warning: {orphan_warnings}"


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
