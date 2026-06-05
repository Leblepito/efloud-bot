"""Max-holding force-close must close the EXCHANGE leg, not just the logical one.

Bug-hunt #2 (HIGH): STEP 5 called lifecycle.close_position (logical-only) for a
position past max_holding_hours, sending NO exchange order. The real Binance
position stayed open and invisible to the duplicate-direction guard → same-symbol
same-direction STACKING, plus phantom breaker PnL recorded at a price the position
never exited at. Fix mirrors _handle_reverse: market-close + cancel siblings on the
exchange first; on failure KEEP the logical position (never drop tracking while it
is still live on the exchange).
"""
from __future__ import annotations

from unittest.mock import MagicMock

from engine.notifications import NotificationManager
from engine.safe_orchestrator import SafeOrchestrator


def _orch(order_manager=None, notification_mgr=None):
    """Build a SafeOrchestrator with only the attributes _force_close_max_hold uses."""
    orch = SafeOrchestrator.__new__(SafeOrchestrator)
    orch.order_manager = order_manager
    orch.lifecycle = MagicMock()
    orch.notification_mgr = notification_mgr
    orch._journal_record_exit = MagicMock()
    return orch


def _pos(symbol="BTC/USDT", direction="SHORT"):
    p = MagicMock()
    p.symbol = symbol
    p.direction = direction
    p.id = "pos-1"
    return p


class TestForceCloseMaxHold:
    def test_closes_exchange_then_logical(self):
        ex_pos = MagicMock(symbol="BTC/USDT", direction="SHORT")
        om = MagicMock()
        om.positions = [ex_pos]
        orch = _orch(order_manager=om)
        pos = _pos()

        ok = orch._force_close_max_hold(pos, 100.0)

        assert ok is True
        om._fallback_close.assert_called_once_with(ex_pos, 100.0, "MAX_HOLD")
        orch.lifecycle.close_position.assert_called_once_with(pos, 100.0, "MANUAL")
        # The OrderManager path already journaled → no duplicate orchestrator row.
        orch._journal_record_exit.assert_not_called()

    def test_exchange_close_failure_keeps_logical_open(self):
        ex_pos = MagicMock(symbol="BTC/USDT", direction="SHORT")
        om = MagicMock()
        om.positions = [ex_pos]
        om._fallback_close.side_effect = RuntimeError("network")
        # spec=NotificationManager so a wrong-arity alert() call raises (catches
        # the (level, message) signature, not a silently-swallowed TypeError).
        notif = MagicMock(spec=NotificationManager)
        orch = _orch(order_manager=om, notification_mgr=notif)
        pos = _pos()

        ok = orch._force_close_max_hold(pos, 100.0)

        assert ok is False
        # CRITICAL: logical close must NOT run while the position is still live.
        orch.lifecycle.close_position.assert_not_called()
        # Operator alert fires with the correct (level, message) signature.
        notif.alert.assert_called_once()
        assert notif.alert.call_args.args[0] == "CRITICAL"

    def test_no_order_manager_falls_back_to_logical_close(self):
        # dry-run / no exchange manager → logical close + journal, returns True.
        orch = _orch(order_manager=None)
        pos = _pos()
        ok = orch._force_close_max_hold(pos, 100.0)
        assert ok is True
        orch.lifecycle.close_position.assert_called_once_with(pos, 100.0, "MANUAL")
        orch._journal_record_exit.assert_called_once()

    def test_no_matching_exchange_pos_logical_close_with_journal(self):
        # order_manager present but position not tracked there → logical close + journal.
        om = MagicMock()
        om.positions = []  # no match
        orch = _orch(order_manager=om)
        pos = _pos()
        ok = orch._force_close_max_hold(pos, 100.0)
        assert ok is True
        om._fallback_close.assert_not_called()
        orch.lifecycle.close_position.assert_called_once_with(pos, 100.0, "MANUAL")
        orch._journal_record_exit.assert_called_once()
