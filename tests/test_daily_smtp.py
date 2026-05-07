"""SMTP client — stdlib smtplib wrapper for daily report send."""
from __future__ import annotations

from unittest import mock

from ops.daily_report.smtp_client import send_email


def test_send_email_success_returns_true():
    """Mock SMTP connection that accepts send_message. Returns True."""
    with mock.patch("ops.daily_report.smtp_client.smtplib.SMTP") as smtp_cls:
        smtp_inst = smtp_cls.return_value.__enter__.return_value
        smtp_inst.send_message = mock.MagicMock()
        ok = send_email(
            host="smtp.example.com", port=587,
            username="bot@example.com", password="appPASS",
            from_addr="bot@example.com", to_addr="ops@example.com",
            subject="Test report", body="Body content",
        )
        assert ok is True
        smtp_inst.starttls.assert_called_once()
        smtp_inst.login.assert_called_once_with("bot@example.com", "appPASS")
        smtp_inst.send_message.assert_called_once()


def test_send_email_smtp_error_returns_false():
    """Mock SMTP raising on connect → send_email logs and returns False (no raise)."""
    import smtplib
    with mock.patch(
        "ops.daily_report.smtp_client.smtplib.SMTP",
        side_effect=smtplib.SMTPException("connection refused"),
    ):
        ok = send_email(
            host="smtp.example.com", port=587,
            username="bot@example.com", password="appPASS",
            from_addr="bot@example.com", to_addr="ops@example.com",
            subject="Test report", body="Body content",
        )
        assert ok is False
