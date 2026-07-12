"""Unit tests for OrderManager symbol precision / stepSize rounding (Binance compatibility)."""
from __future__ import annotations

from unittest.mock import MagicMock
import pytest

from exchange import OrderManager, Position


def test_order_manager_rounds_tp_sizes_using_exchange_precision():
    """Live path (dry_run=False): when placing TP1/TP2, sizes must be rounded
    using the exchange's amount_to_precision method to prevent lot size / step size errors."""
    mock_client = MagicMock()
    mock_client.to_ccxt_symbol.side_effect = lambda s: f"{s}:USDT"
    mock_client.exchange = MagicMock()

    # Stub create_order to return mocked order dict
    def make_order(*args, **kwargs):
        return {"id": "ord_" + args[1].lower(), "average": args[3] * 1.0001}
    mock_client.exchange.create_order = MagicMock(side_effect=make_order)

    # Stub amount_to_precision to return formatted string matching mock stepSize = 1 (no decimals)
    def mock_amount_to_precision(symbol, amount):
        return f"{int(round(amount))}"
    mock_client.exchange.amount_to_precision = MagicMock(side_effect=mock_amount_to_precision)

    om = OrderManager(client=mock_client, dry_run=False)
    # Size = 919. F7 (2026-07-11, b912245): once TOPLAM precision'a cekilir (919),
    # TP1 = round(size/2) = 460, TP2 = KALAN = 919 - 460 = 459. Eski davranis
    # (TP1 ve TP2 bagimsiz round: 460+460 = 920 > 919) dust/oversize buguydu —
    # kalan-miktar semantigi toplamın pozisyonu asla asmamasini garantiler.
    pos = om.open_position(
        symbol="ADA/USDT", direction="SHORT", size=919.0,
        entry=0.23, sl=0.25, tp1=0.21, tp2=0.20,
    )

    assert pos is not None
    assert mock_client.exchange.amount_to_precision.call_count >= 2

    # Check that create_order was called with rounded integer amounts (float 460.0) instead of raw 459.5
    call_args_list = mock_client.exchange.create_order.call_args_list
    assert call_args_list[2].args[3] == 460.0  # TP1 size (round(size/2))
    assert call_args_list[3].args[3] == 459.0  # TP2 size = kalan (919 - 460), F7
    # Invariant: TP bacaklari toplami pozisyon boyutunu asamaz (dust/oversize yok)
    assert call_args_list[2].args[3] + call_args_list[3].args[3] == 919.0


def test_order_manager_reconcile_repair_rounds_sizes():
    """_repair_missing_protection_orders must also round the sizes of re-placed TP orders."""
    mock_client = MagicMock()
    mock_client.to_ccxt_symbol.side_effect = lambda s: f"{s}:USDT"
    mock_client.exchange = MagicMock()

    def mock_amount_to_precision(symbol, amount):
        return f"{int(round(amount))}"
    mock_client.exchange.amount_to_precision = MagicMock(side_effect=mock_amount_to_precision)
    mock_client.exchange.create_order.return_value = {"id": "repaired_tp"}

    om = OrderManager(client=mock_client, dry_run=False)
    # Create an active position that has missing TP orders (empty order IDs)
    missing_tp_pos = Position(
        symbol="ADA/USDT", direction="SHORT", entry=0.23,
        sl=0.25, tp1=0.21, tp2=0.20, size=919.0,
        sl_order_id="sl_1", tp1_order_id="", tp2_order_id="",
        opened_at="2026-05-28T00:00:00Z",
    )
    om.positions = [missing_tp_pos]

    # Run repair method
    om._repair_missing_protection_orders(bn_order_ids=set(["sl_1"]))

    # Both TP1 and TP2 repairs should call create_order with rounded amounts (float 460.0)
    calls = mock_client.exchange.create_order.call_args_list
    assert len(calls) == 2
    assert calls[0].args[3] == 460.0  # TP1 Repair amount
    assert calls[1].args[3] == 460.0  # TP2 Repair amount


def test_order_manager_move_sl_to_breakeven_rounds_remaining_size():
    """_move_sl_to_breakeven must round the remaining size when placing the break-even SL."""
    mock_client = MagicMock()
    mock_client.to_ccxt_symbol.side_effect = lambda s: f"{s}:USDT"
    mock_client.exchange = MagicMock()

    def mock_amount_to_precision(symbol, amount):
        return f"{int(round(amount))}"
    mock_client.exchange.amount_to_precision = MagicMock(side_effect=mock_amount_to_precision)
    mock_client.exchange.create_order.return_value = {"id": "new_sl_be"}

    om = OrderManager(client=mock_client, dry_run=False)
    pos = Position(
        symbol="ADA/USDT", direction="SHORT", entry=0.23,
        sl=0.25, tp1=0.21, tp2=0.20, size=919.0,
        sl_order_id="sl_1", tp1_order_id="tp1_1", tp2_order_id="tp2_1",
        opened_at="2026-05-28T00:00:00Z",
    )

    om._move_sl_to_breakeven(pos)

    # Rounded remaining size = 460.0 (half of 919.0)
    create_call = mock_client.exchange.create_order.call_args_list[0]
    assert create_call.args[3] == 460.0


def test_order_manager_handles_amount_to_precision_exceptions_gracefully():
    """If amount_to_precision is not mocked or raises TypeError, it should gracefully
    fall back to the raw unrounded sizes without crashing."""
    mock_client = MagicMock()
    mock_client.to_ccxt_symbol.side_effect = lambda s: f"{s}:USDT"
    mock_client.exchange = MagicMock()

    # Stub create_order
    mock_client.exchange.create_order.return_value = {"id": "ord_ok"}
    # Stub amount_to_precision to raise a TypeError (simulating float(MagicMock()) in typical unmocked unit tests)
    mock_client.exchange.amount_to_precision.side_effect = TypeError("Mock error")

    om = OrderManager(client=mock_client, dry_run=False)
    # Open position with size = 919.0. Should fallback gracefully to 459.5 for TPs.
    pos = om.open_position(
        symbol="ADA/USDT", direction="SHORT", size=919.0,
        entry=0.23, sl=0.25, tp1=0.21, tp2=0.20,
    )

    assert pos is not None
    # TP1 and TP2 were placed successfully using fallbacks
    assert pos.tp1_order_id == "ord_ok"
    assert pos.tp2_order_id == "ord_ok"
    
    # Check that create_order was called with raw float 459.5
    call_args_list = mock_client.exchange.create_order.call_args_list
    assert call_args_list[2].args[3] == 459.5
    assert call_args_list[3].args[3] == 459.5


def test_order_manager_rounds_tp_and_sl_prices_using_exchange_precision():
    """Live path (dry_run=False): when placing entries, SL, or TPs, prices must be rounded
    using the exchange's price_to_precision method to prevent Binance PRICE_FILTER errors."""
    mock_client = MagicMock()
    mock_client.to_ccxt_symbol.side_effect = lambda s: f"{s}:USDT"
    mock_client.exchange = MagicMock()

    # Stub create_order to return mocked order dict
    mock_client.exchange.create_order.return_value = {"id": "ord_ok", "average": 0.230005}

    # Stub price_to_precision to round to 4 decimals
    def mock_price_to_precision(symbol, price):
        return f"{price:.4f}"
    mock_client.exchange.price_to_precision = MagicMock(side_effect=mock_price_to_precision)

    om = OrderManager(client=mock_client, dry_run=False)

    # We pass entry, sl, tp1, tp2 with 6 decimals (e.g. 0.231234)
    pos = om.open_position(
        symbol="ADA/USDT", direction="SHORT", size=100.0,
        entry=0.231234, sl=0.251234, tp1=0.211234, tp2=0.201234,
    )

    assert pos is not None
    # price_to_precision should be called for entry, sl, tp1, tp2 when opening position
    assert mock_client.exchange.price_to_precision.call_count >= 4

    # The actual stopPrice parameters sent to create_order must be float strings rounded to 4 decimals
    calls = mock_client.exchange.create_order.call_args_list
    
    # Let's find STOP_MARKET call
    sl_call = next(c for c in calls if c.args[1] == "STOP_MARKET")
    assert sl_call.kwargs['params']['stopPrice'] == 0.2512

    # Let's find TAKE_PROFIT_MARKET calls
    tp_calls = [c for c in calls if c.args[1] == "TAKE_PROFIT_MARKET"]
    assert tp_calls[0].kwargs['params']['stopPrice'] == 0.2112
    assert tp_calls[1].kwargs['params']['stopPrice'] == 0.2012


def test_reconcile_tp1_missing_unfilled_keeps_active_and_resets_id():
    """If TP1 order is missing but exchange position size is NOT reduced, reconcile
    must NOT mark tp1_hit=True. Instead, it resets tp1_order_id to empty to trigger repair."""
    mock_client = MagicMock()
    mock_client.to_ccxt_symbol.side_effect = lambda s: f"{s}:USDT"
    mock_client.exchange = MagicMock()

    # Mock fetch_open_orders to return SL and TP2 (TP1 missing)
    mock_client.exchange.fetch_open_orders = MagicMock(
        return_value=[
            {"id": "sl_1", "symbol": "ADA/USDT"},
            {"id": "tp2_1", "symbol": "ADA/USDT"},
        ]
    )
    mock_client.exchange.fapiPrivateGetOpenAlgoOrders = MagicMock(return_value=[])

    # Mock get_open_positions to return full position size (contracts = 919.0)
    mock_client.get_open_positions = MagicMock(
        return_value=[{"symbol": "ADA/USDT", "contracts": 919.0, "side": "short"}]
    )

    om = OrderManager(client=mock_client, dry_run=False)
    pos = Position(
        symbol="ADA/USDT", direction="SHORT", entry=0.23,
        sl=0.25, tp1=0.21, tp2=0.20, size=919.0,
        sl_order_id="sl_1", tp1_order_id="tp1_1", tp2_order_id="tp2_1",
        opened_at="2026-05-28T00:00:00Z",
    )
    om.positions = [pos]

    om.reconcile()

    # TP1 should NOT be marked hit, and tp1_order_id should be cleared so it can be repaired
    assert not pos.tp1_hit
    assert pos.tp1_order_id == ""
    # SL should not be moved (it remains "sl_1")
    assert pos.sl_order_id == "sl_1"


def test_reconcile_tp1_missing_filled_triggers_tp1_hit():
    """If TP1 order is missing and exchange position size IS reduced to <= 70%, reconcile
    marks tp1_hit=True and triggers break-even SL shift."""
    mock_client = MagicMock()
    mock_client.to_ccxt_symbol.side_effect = lambda s: f"{s}:USDT"
    mock_client.exchange = MagicMock()
    mock_client.exchange.amount_to_precision = MagicMock(side_effect=lambda s, a: f"{a:.1f}")
    mock_client.exchange.price_to_precision = MagicMock(side_effect=lambda s, p: f"{p:.4f}")
    mock_client.exchange.create_order.return_value = {"id": "new_sl_be"}

    # Mock fetch_open_orders to return only SL and TP2 (TP1 missing)
    mock_client.exchange.fetch_open_orders = MagicMock(
        return_value=[
            {"id": "sl_1", "symbol": "ADA/USDT"},
            {"id": "tp2_1", "symbol": "ADA/USDT"},
        ]
    )
    mock_client.exchange.fapiPrivateGetOpenAlgoOrders = MagicMock(return_value=[])

    # Mock get_open_positions to return reduced position size (contracts = 459.5)
    mock_client.get_open_positions = MagicMock(
        return_value=[{"symbol": "ADA/USDT", "contracts": 459.5, "side": "short"}]
    )

    om = OrderManager(client=mock_client, dry_run=False)
    pos = Position(
        symbol="ADA/USDT", direction="SHORT", entry=0.23,
        sl=0.25, tp1=0.21, tp2=0.20, size=919.0,
        sl_order_id="sl_1", tp1_order_id="tp1_1", tp2_order_id="tp2_1",
        opened_at="2026-05-28T00:00:00Z",
    )
    om.positions = [pos]

    om.reconcile()

    # TP1 should be marked hit, and SL moved to break-even (new SL ID placed)
    assert pos.tp1_hit
    assert pos.sl_order_id == "new_sl_be"


def test_reconcile_tp2_missing_resets_id():
    """If TP2 order is missing from exchange orders, reconcile clears tp2_order_id to trigger repair."""
    mock_client = MagicMock()
    mock_client.to_ccxt_symbol.side_effect = lambda s: f"{s}:USDT"
    mock_client.exchange = MagicMock()

    # Mock fetch_open_orders to return only SL and TP1 (TP2 missing)
    mock_client.exchange.fetch_open_orders = MagicMock(
        return_value=[
            {"id": "sl_1", "symbol": "ADA/USDT"},
            {"id": "tp1_1", "symbol": "ADA/USDT"},
        ]
    )
    mock_client.exchange.fapiPrivateGetOpenAlgoOrders = MagicMock(return_value=[])

    # Position is still fully open
    mock_client.get_open_positions = MagicMock(
        return_value=[{"symbol": "ADA/USDT", "contracts": 919.0, "side": "short"}]
    )

    om = OrderManager(client=mock_client, dry_run=False)
    pos = Position(
        symbol="ADA/USDT", direction="SHORT", entry=0.23,
        sl=0.25, tp1=0.21, tp2=0.20, size=919.0,
        sl_order_id="sl_1", tp1_order_id="tp1_1", tp2_order_id="tp2_1",
        opened_at="2026-05-28T00:00:00Z",
    )
    om.positions = [pos]

    om.reconcile()

    # tp2_order_id should be cleared, tp1_order_id remains set
    assert pos.tp2_order_id == ""
    assert pos.tp1_order_id == "tp1_1"


