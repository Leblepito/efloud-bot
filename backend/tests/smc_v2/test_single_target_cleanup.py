"""Orphan SL cleanup wiring on single-target TP1 fill (PR #S5.5 task 6).

PR #S5 added the lifecycle.partial_close single-target branch (full close
on TP1 when tp2=None). PR #S5.5 wires the exchange-side cleanup: when
_move_sl_to_breakeven is invoked on a single-target Position, it must
SKIP the BE move (full close already done) and instead cancel orphan SL.

Without this, a v2 single-target TP1 fill leaves an orphan reduceOnly SL
on Binance indefinitely (spec §6 risk).
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from exchange import OrderManager, Position


def _make_single_target_position():
    return Position(
        symbol="ETH/USDT", direction="LONG", entry=100.0,
        sl=95.0, tp1=110.0, tp2=None, size=1.0,
        order_id="entry_x",
        sl_order_id="sl_x",
        tp1_order_id="tp1_x",
        tp2_order_id="",  # single-target: no TP2 order
        tp1_hit=True,     # we're called post-TP1
        opened_at="2025-01-01T00:00:00",
    )


def _make_two_target_position():
    return Position(
        symbol="ETH/USDT", direction="LONG", entry=100.0,
        sl=95.0, tp1=110.0, tp2=120.0, size=1.0,
        order_id="entry_x",
        sl_order_id="sl_x",
        tp1_order_id="tp1_x",
        tp2_order_id="tp2_x",
        tp1_hit=True,
        opened_at="2025-01-01T00:00:00",
    )


def test_move_sl_to_breakeven_skips_be_and_cleans_siblings_for_single_target():
    """Single-target Position: _move_sl_to_breakeven must NOT move SL to BE,
    instead it must call _cancel_position_siblings."""
    mock_client = MagicMock()
    mock_client.to_ccxt_symbol.side_effect = lambda s: f"{s}:USDT"
    mock_client.exchange = MagicMock()
    mock_client.exchange.cancel_order = MagicMock(return_value={"id": "ok"})

    om = OrderManager(client=mock_client, dry_run=False)
    pos = _make_single_target_position()

    with patch.object(om, "_cancel_position_siblings") as spy_cleanup:
        spy_cleanup.return_value = {"cancelled": ["SL"], "failed": [], "missing": ["TP1", "TP2"]}
        om._move_sl_to_breakeven(pos)

        # Cleanup helper MUST have been called with TP1_FULL_CLOSE reason
        assert spy_cleanup.call_count == 1
        call_kwargs = spy_cleanup.call_args
        # Positional or kwargs — verify the reason regardless
        all_args = list(call_kwargs.args) + list(call_kwargs.kwargs.values())
        assert "TP1_FULL_CLOSE" in all_args

    # SL must NOT have been moved to BE (still original 95.0)
    assert pos.sl == 95.0
    # No new STOP_MARKET order placed (BE move skipped)
    assert mock_client.exchange.create_order.call_count == 0


def test_move_sl_to_breakeven_unchanged_for_two_target():
    """Regression: v1 two-target Position keeps legacy BE move behavior."""
    mock_client = MagicMock()
    mock_client.to_ccxt_symbol.side_effect = lambda s: f"{s}:USDT"
    mock_client.exchange = MagicMock()
    mock_client.exchange.cancel_order = MagicMock(return_value={"id": "ok"})
    mock_client.exchange.create_order = MagicMock(
        return_value={"id": "new_sl_id"}
    )

    om = OrderManager(client=mock_client, dry_run=False)
    pos = _make_two_target_position()

    with patch.object(om, "_cancel_position_siblings") as spy_cleanup:
        om._move_sl_to_breakeven(pos)

        # Cleanup helper MUST NOT have been called in v1 path
        assert spy_cleanup.call_count == 0

    # BE move must have happened: new STOP_MARKET order placed, sl updated
    assert pos.sl == 100.0  # moved to entry
    assert pos.sl_order_id == "new_sl_id"
    assert mock_client.exchange.create_order.call_count == 1


def test_move_sl_to_breakeven_dry_run_single_target_no_op():
    """Dry-run: still set pos.sl = entry as in v1 dry path; no cleanup
    call needed because there are no real exchange orders to cancel."""
    om = OrderManager(client=MagicMock(), dry_run=True)
    pos = _make_single_target_position()

    with patch.object(om, "_cancel_position_siblings") as spy_cleanup:
        om._move_sl_to_breakeven(pos)
        # dry_run path returns early — cleanup spy must NOT be called
        assert spy_cleanup.call_count == 0
