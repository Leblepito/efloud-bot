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
    # Size = 919. TP1 = 459.5, which is rounded to '460' via our mock, and TP2 = 459.5 rounded to '460'
    pos = om.open_position(
        symbol="ADA/USDT", direction="SHORT", size=919.0,
        entry=0.23, sl=0.25, tp1=0.21, tp2=0.20,
    )

    assert pos is not None
    assert mock_client.exchange.amount_to_precision.call_count >= 2

    # Check that create_order was called with rounded integer amounts (float 460.0) instead of raw 459.5
    call_args_list = mock_client.exchange.create_order.call_args_list
    assert call_args_list[2].args[3] == 460.0  # TP1 size
    assert call_args_list[3].args[3] == 460.0  # TP2 size


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
