"""_handle_reverse must verify the exchange before flipping on a desync (bug-hunt #8).

When order_manager has NO matching tracked position (exchange_pos is None), the old
code closed the logical position and returned True, so the caller opened the opposite
side. If the position was actually still LIVE on Binance (lifecycle-vs-order_manager
desync after a restart / manual injection), that opposite order triggers an
uncontrolled auto-flip under hedge-off/ISOLATED, with no bot SL/TP. Fix: when
untracked, check the live exchange; if a live opposite exists, ABORT the reverse
(return False). Also fixes the (level, message) arity of the close-failure alert.
"""
from __future__ import annotations

from unittest.mock import MagicMock

from engine.notifications import NotificationManager
from engine.safe_orchestrator import SafeOrchestrator


def _orch(order_manager=None, notification_mgr=None):
    orch = SafeOrchestrator.__new__(SafeOrchestrator)
    orch.order_manager = order_manager
    orch.lifecycle = MagicMock()
    orch.notification_mgr = notification_mgr
    orch._journal_record_exit = MagicMock()
    return orch


def _opp(direction="SHORT"):
    return MagicMock(direction=direction, id="opp-1")


class TestHandleReverseLiveCheck:
    def test_aborts_when_live_opposite_untracked(self):
        om = MagicMock()
        om.positions = []  # order_manager doesn't track it...
        om.client.get_open_positions.return_value = [   # ...but it IS live on Binance
            {"symbol": "BTC/USDT:USDT", "side": "short", "contracts": 0.01},
        ]
        notif = MagicMock(spec=NotificationManager)
        orch = _orch(order_manager=om, notification_mgr=notif)

        ok = orch._handle_reverse(_opp("SHORT"), "BTC/USDT", 60000.0)

        assert ok is False  # abort — must NOT auto-flip a live untracked position
        orch.lifecycle.close_position.assert_not_called()
        om._fallback_close.assert_not_called()
        notif.alert.assert_called_once()
        assert notif.alert.call_args.args[0] == "CRITICAL"

    def test_proceeds_when_exchange_flat(self):
        om = MagicMock()
        om.positions = []
        om.client.get_open_positions.return_value = []  # genuinely flat on exchange
        orch = _orch(order_manager=om)

        ok = orch._handle_reverse(_opp("SHORT"), "BTC/USDT", 60000.0)

        assert ok is True
        orch.lifecycle.close_position.assert_called_once_with(
            orch.lifecycle.close_position.call_args.args[0], 60000.0, "REVERSE"
        )
        orch._journal_record_exit.assert_called_once()  # no exchange path → journal here

    def test_aborts_fail_safe_when_live_check_errors(self):
        om = MagicMock()
        om.positions = []
        om.client.get_open_positions.side_effect = Exception("network")
        orch = _orch(order_manager=om)

        ok = orch._handle_reverse(_opp("SHORT"), "BTC/USDT", 60000.0)

        assert ok is False  # can't verify exchange → fail safe (abort, no flip)
        orch.lifecycle.close_position.assert_not_called()

    def test_tracked_position_closed_unchanged(self):
        ex_pos = MagicMock(symbol="BTC/USDT", direction="SHORT")
        om = MagicMock()
        om.positions = [ex_pos]
        orch = _orch(order_manager=om)

        ok = orch._handle_reverse(_opp("SHORT"), "BTC/USDT", 60000.0)

        assert ok is True
        om._fallback_close.assert_called_once_with(ex_pos, 60000.0, "REVERSE")
        orch.lifecycle.close_position.assert_called_once()
        orch._journal_record_exit.assert_not_called()  # exchange path journaled
        om.client.get_open_positions.assert_not_called()  # no live check when tracked

    def test_tracked_close_failure_alerts_with_level(self):
        ex_pos = MagicMock(symbol="BTC/USDT", direction="SHORT")
        om = MagicMock()
        om.positions = [ex_pos]
        om._fallback_close.side_effect = RuntimeError("close fail")
        notif = MagicMock(spec=NotificationManager)
        orch = _orch(order_manager=om, notification_mgr=notif)

        ok = orch._handle_reverse(_opp("SHORT"), "BTC/USDT", 60000.0)

        assert ok is False
        notif.alert.assert_called_once()
        assert notif.alert.call_args.args[0] == "CRITICAL"  # (level, message) arity fix
