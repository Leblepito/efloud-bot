"""notify_position_opened handles tp2=None (PR #S5.6 hotfix).

Notifier signature was `tp2: float` + `f"{tp2:.4f}"`. v2 single-target
setups (after PR #S6 flag flip) pass tp2=None → format crash, swallowed
by bot_runner._emit try/except → silent loss of Telegram alert.
"""
from __future__ import annotations

from unittest.mock import MagicMock

from backend.notifications import TelegramNotifier


def _make_notifier_with_capture():
    """Build a NotificationManager that captures send() calls instead of HTTP."""
    nm = TelegramNotifier()
    nm.enabled = True
    nm.send = MagicMock(return_value=None)
    return nm


def test_notify_position_opened_with_tp2_none_does_not_crash():
    nm = _make_notifier_with_capture()
    # Must not raise — historical bug was TypeError from f"{None:.4f}".
    nm.notify_position_opened(
        symbol="ETH/USDT", direction="LONG",
        entry=100.0, sl=95.0, tp1=110.0, tp2=None, size=1.0,
    )
    assert nm.send.call_count == 1


def test_notify_position_opened_tp2_none_message_contains_marker():
    nm = _make_notifier_with_capture()
    nm.notify_position_opened(
        symbol="ETH/USDT", direction="LONG",
        entry=100.0, sl=95.0, tp1=110.0, tp2=None, size=1.0,
    )
    sent_text = nm.send.call_args.args[0]
    assert "TP2:" in sent_text
    # The None case should produce a recognizable marker, not literal "None"
    assert "NONE" in sent_text or "single-target" in sent_text.lower() or "n/a" in sent_text.lower()


def test_notify_position_opened_with_tp2_numeric_unchanged():
    """Regression: numeric tp2 still formats to 4 decimals."""
    nm = _make_notifier_with_capture()
    nm.notify_position_opened(
        symbol="ETH/USDT", direction="LONG",
        entry=100.0, sl=95.0, tp1=110.0, tp2=120.0, size=1.0,
    )
    sent_text = nm.send.call_args.args[0]
    assert "120.0000" in sent_text  # `f"{120.0:.4f}"` → "120.0000"
