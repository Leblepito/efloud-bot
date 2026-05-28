"""OrderManager atomicity tests for entry + protective order placement.

These tests encode the 2026-05-11 incident failure mode: market entry can
succeed while SL/TP placement fails. The manager must not leave unprotected or
untracked exchange positions behind.
"""
from __future__ import annotations

import logging
from unittest.mock import MagicMock

import pytest

from exchange import BinanceClient, OrderManager


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


def _open_long(mgr, symbol="BTC/USDT", size=1.0):
    return mgr.open_position(
        symbol=symbol,
        direction="LONG",
        size=size,
        entry=95000,
        sl=94000,
        tp1=96000,
        tp2=97000,
    )


def _open_short(mgr, symbol="ETH/USDT", size=2.0):
    return mgr.open_position(
        symbol=symbol,
        direction="SHORT",
        size=size,
        entry=2400,
        sl=2440,
        tp1=2360,
        tp2=2320,
    )


def test_entry_failure_returns_none_without_rollback(mgr, mock_client):
    mock_client.exchange.create_order.side_effect = RuntimeError("entry rejected")

    pos = _open_long(mgr)

    assert pos is None
    assert mgr.positions == []
    assert mock_client.exchange.create_order.call_count == 1


def test_entry_success_sl_failure_rolls_back_reduce_only_market_close(mgr, mock_client):
    mock_client.exchange.create_order.side_effect = [
        {"id": "ENTRY-1", "average": 95012.5, "filled": 0.75},
        RuntimeError("SL failed — insufficient margin"),
        {"id": "ROLLBACK-1"},
    ]

    pos = _open_long(mgr)

    assert pos is None
    assert mgr.positions == []
    calls = mock_client.exchange.create_order.call_args_list
    assert len(calls) == 3
    assert calls[2].args == ("BTC/USDT:USDT", "market", "sell", 0.75)
    assert calls[2].kwargs["params"]["reduceOnly"] is True


def test_sl_failure_does_not_place_tp_orders(mgr, mock_client):
    mock_client.exchange.create_order.side_effect = [
        {"id": "ENTRY-1", "filled": 1.0},
        RuntimeError("SL failed"),
        {"id": "ROLLBACK-1"},
    ]

    pos = _open_long(mgr)

    assert pos is None
    order_types = [c.args[1] for c in mock_client.exchange.create_order.call_args_list]
    assert order_types == ["market", "STOP_MARKET", "market"]
    assert "TAKE_PROFIT_MARKET" not in order_types


def test_sl_failure_rollback_failure_logs_critical_and_returns_none(mgr, mock_client, caplog):
    caplog.set_level(logging.CRITICAL, logger="efloud.exchange")
    mock_client.exchange.create_order.side_effect = [
        {"id": "ENTRY-1", "filled": 1.0},
        RuntimeError("SL failed"),
        RuntimeError("rollback close failed"),
    ]

    pos = _open_long(mgr)

    assert pos is None
    assert mgr.positions == []
    assert any(
        "entry_rollback_failed" in r.message
        or getattr(r, "event", "") == "order_manager.entry_rollback_failed"
        for r in caplog.records
    )


def test_sl_success_tp1_failure_keeps_position_tracked_with_sl_order_id(mgr, mock_client, caplog):
    caplog.set_level(logging.WARNING, logger="efloud.exchange")
    mock_client.exchange.create_order.side_effect = [
        {"id": "ENTRY-1", "average": 95001.0, "filled": 1.0},
        {"id": "SL-1"},
        RuntimeError("TP1 placement failed — market data delayed"),
    ]

    pos = _open_long(mgr)

    assert pos is not None
    assert mgr.positions == [pos]
    assert pos.order_id == "ENTRY-1"
    assert pos.entry == pytest.approx(95001.0)
    assert pos.sl_order_id == "SL-1"
    assert pos.tp1_order_id == ""
    assert pos.tp2_order_id == ""
    assert any(
        "tp_placement_failed_after_sl" in r.message
        or getattr(r, "event", "") == "order_manager.tp_placement_failed_after_sl"
        for r in caplog.records
    )


def test_sl_success_tp2_failure_keeps_position_tracked_with_sl_and_tp1(mgr, mock_client, caplog):
    caplog.set_level(logging.WARNING, logger="efloud.exchange")
    mock_client.exchange.create_order.side_effect = [
        {"id": "ENTRY-1", "filled": 1.0},
        {"id": "SL-1"},
        {"id": "TP1-1"},
        RuntimeError("TP2 placement failed — market data delayed"),
    ]

    pos = _open_long(mgr)

    assert pos is not None
    assert mgr.positions == [pos]
    assert pos.sl_order_id == "SL-1"
    assert pos.tp1_order_id == "TP1-1"
    assert pos.tp2_order_id == ""
    assert any(
        "tp_placement_failed_after_sl" in r.message
        or getattr(r, "event", "") == "order_manager.tp_placement_failed_after_sl"
        for r in caplog.records
    )


def test_success_path_unchanged_all_four_orders_and_position_opened(mgr, mock_client):
    mock_client.exchange.create_order.side_effect = [
        {"id": "ENTRY-1", "filled": 1.0},
        {"id": "SL-1"},
        {"id": "TP1-1"},
        {"id": "TP2-1"},
    ]

    pos = _open_long(mgr)

    assert pos is not None
    assert mgr.positions == [pos]
    assert pos.order_id == "ENTRY-1"
    assert pos.sl_order_id == "SL-1"
    assert pos.tp1_order_id == "TP1-1"
    assert pos.tp2_order_id == "TP2-1"
    assert [c.args[1] for c in mock_client.exchange.create_order.call_args_list] == [
        "market", "STOP_MARKET", "TAKE_PROFIT_MARKET", "TAKE_PROFIT_MARKET"
    ]


def test_rollback_uses_actual_filled_amount_when_available(mgr, mock_client):
    mock_client.exchange.create_order.side_effect = [
        {"id": "ENTRY-1", "filled": 0.42},
        RuntimeError("SL failed"),
        {"id": "ROLLBACK-1"},
    ]

    _open_long(mgr, size=1.0)

    rollback_call = mock_client.exchange.create_order.call_args_list[2]
    assert rollback_call.args[3] == pytest.approx(0.42)


def test_rollback_falls_back_to_requested_size_when_no_fill_amount(mgr, mock_client):
    mock_client.exchange.create_order.side_effect = [
        {"id": "ENTRY-1"},
        RuntimeError("SL failed"),
        {"id": "ROLLBACK-1"},
    ]

    _open_long(mgr, size=1.23)

    rollback_call = mock_client.exchange.create_order.call_args_list[2]
    assert rollback_call.args[3] == pytest.approx(1.23)


def test_short_entry_sl_failure_rolls_back_with_buy_side(mgr, mock_client):
    mock_client.exchange.create_order.side_effect = [
        {"id": "ENTRY-1", "filled": 2.0},
        RuntimeError("SL failed"),
        {"id": "ROLLBACK-1"},
    ]

    pos = _open_short(mgr)

    assert pos is None
    rollback_call = mock_client.exchange.create_order.call_args_list[2]
    assert rollback_call.args == ("ETH/USDT:USDT", "market", "buy", 2.0)
    assert rollback_call.kwargs["params"]["reduceOnly"] is True
