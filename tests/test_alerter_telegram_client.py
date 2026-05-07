"""Telegram client — stdlib urllib HTTP wrapper."""
from __future__ import annotations

from unittest import mock

from ops.alerter.telegram_client import send_message


def test_send_message_success_returns_true():
    """Mock urllib.request.urlopen to return a 200 response."""
    fake_response = mock.MagicMock()
    fake_response.__enter__.return_value.status = 200
    fake_response.__enter__.return_value.read.return_value = b'{"ok":true}'
    with mock.patch("ops.alerter.telegram_client.urllib.request.urlopen",
                    return_value=fake_response) as urlopen:
        ok = send_message(token="TOK", chat_id="123", text="hello")
        assert ok is True
        # Verify the URL contains the bot token
        call_arg = urlopen.call_args[0][0]
        assert hasattr(call_arg, "full_url")
        assert "/botTOK/sendMessage" in call_arg.full_url


def test_send_message_http_error_returns_false():
    """Mock urlopen to raise URLError; send_message must return False (NOT raise)."""
    import urllib.error
    with mock.patch(
        "ops.alerter.telegram_client.urllib.request.urlopen",
        side_effect=urllib.error.URLError("network unreachable"),
    ):
        ok = send_message(token="TOK", chat_id="123", text="hello")
        assert ok is False
