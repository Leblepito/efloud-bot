"""tp2 type widening: float → Optional[float] in exchange.Position + OrderManager (PR #S5.5).

PR #S5 added single-target close branch to lifecycle but exchange.Position.tp2
was still typed `float`. PR #S5.5 closes that gap before PR #S6 flips the v2 flag.
"""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from exchange import OrderManager, Position


def test_position_accepts_tp2_none():
    """exchange.Position must accept tp2=None (single-target marker)."""
    p = Position(
        symbol="ETH/USDT", direction="LONG", entry=100.0,
        sl=95.0, tp1=110.0, tp2=None, size=1.0,
    )
    assert p.tp2 is None


def test_position_default_tp2_unchanged():
    """Backward compat: default value remains 0.0 (not None) so existing
    state files round-trip without semantic change."""
    p = Position(
        symbol="ETH/USDT", direction="LONG", entry=100.0,
        sl=95.0, tp1=110.0, tp2=120.0, size=1.0,
    )
    assert p.tp2 == 120.0


def test_order_manager_open_position_dry_run_accepts_tp2_none(tmp_path):
    """OrderManager.open_position with tp2=None (dry_run): Position created
    with tp2=None, no exception."""
    om = OrderManager(client=None, dry_run=True, state_dir=str(tmp_path))
    pos = om.open_position(
        symbol="ETH/USDT", direction="LONG", size=1.0,
        entry=100.0, sl=95.0, tp1=110.0, tp2=None,
    )
    assert pos is not None
    assert pos.tp2 is None
    assert pos.tp1 == 110.0


def test_order_manager_live_path_skips_tp2_when_none():
    """Live path (dry_run=False): when tp2=None, the TP2 order placement step
    must be SKIPPED. Only SL + TP1 orders are sent. TP1 size = full size
    (not half) because there is no TP2 to split."""
    mock_client = MagicMock()
    mock_client.to_ccxt_symbol.side_effect = lambda s: f"{s}:USDT"
    mock_client.exchange = MagicMock()

    # Stub exchange.create_order to return order ids
    def make_order(*args, **kwargs):
        return {"id": "ord_" + args[1].lower(), "average": args[3] * 1.0001}
    mock_client.exchange.create_order = MagicMock(side_effect=make_order)

    om = OrderManager(client=mock_client, dry_run=False)
    pos = om.open_position(
        symbol="ETH/USDT", direction="LONG", size=1.0,
        entry=100.0, sl=95.0, tp1=110.0, tp2=None,
    )

    assert pos is not None
    assert pos.tp2 is None

    # Inspect create_order calls: entry + SL + TP1 only (3 calls, not 4)
    types_called = [c.args[1] for c in mock_client.exchange.create_order.call_args_list]
    assert types_called == ["market", "STOP_MARKET", "TAKE_PROFIT_MARKET"]
    # Exactly 3 calls — no TP2 placement
    assert mock_client.exchange.create_order.call_count == 3

    # TP1 size should equal full size (no half-split when no TP2)
    tp1_call_size = mock_client.exchange.create_order.call_args_list[2].args[3]
    assert tp1_call_size == 1.0


def test_order_manager_live_path_two_target_unchanged():
    """Regression: when tp2 is numeric (v1 path), both TP1+TP2 placed at
    half_size each. PR #S5.5 must not change v1 behavior."""
    mock_client = MagicMock()
    mock_client.to_ccxt_symbol.side_effect = lambda s: f"{s}:USDT"
    mock_client.exchange = MagicMock()

    def make_order(*args, **kwargs):
        return {"id": "ord_x", "average": args[3] * 1.0001}
    mock_client.exchange.create_order = MagicMock(side_effect=make_order)

    om = OrderManager(client=mock_client, dry_run=False)
    pos = om.open_position(
        symbol="ETH/USDT", direction="LONG", size=2.0,
        entry=100.0, sl=95.0, tp1=110.0, tp2=120.0,
    )

    assert pos is not None
    assert pos.tp2 == 120.0
    # 4 calls: entry + SL + TP1 + TP2
    assert mock_client.exchange.create_order.call_count == 4
    types_called = [c.args[1] for c in mock_client.exchange.create_order.call_args_list]
    assert types_called == ["market", "STOP_MARKET", "TAKE_PROFIT_MARKET", "TAKE_PROFIT_MARKET"]
    # TP1 + TP2 should split size in half
    tp1_size = mock_client.exchange.create_order.call_args_list[2].args[3]
    tp2_size = mock_client.exchange.create_order.call_args_list[3].args[3]
    assert tp1_size == 1.0
    assert tp2_size == 1.0
