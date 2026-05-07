"""SMTP send — stdlib smtplib + email.message wrapper for daily report.

Uses STARTTLS (port 587 default). Returns True on 2xx-equivalent success,
False on any exception. Errors logged WARNING; caller (the cron command)
relies on exit code to trigger the failure-to-send Telegram fallback.
"""
from __future__ import annotations

import logging
import smtplib
from email.message import EmailMessage

log = logging.getLogger("efloud.daily_report.smtp")

TIMEOUT_SEC = 30


def send_email(
    host: str,
    port: int,
    username: str,
    password: str,
    from_addr: str,
    to_addr: str,
    subject: str,
    body: str,
) -> bool:
    """Send a plain-text email. Returns True on success, False on any error."""
    if not host or not username or not password or not to_addr:
        log.warning("send_email skipped: missing required SMTP config")
        return False

    msg = EmailMessage()
    msg["From"] = from_addr
    msg["To"] = to_addr
    msg["Subject"] = subject
    msg.set_content(body, subtype="plain", charset="utf-8")

    try:
        with smtplib.SMTP(host, port, timeout=TIMEOUT_SEC) as smtp:
            smtp.starttls()
            smtp.login(username, password)
            smtp.send_message(msg)
        return True
    except (smtplib.SMTPException, OSError) as e:
        log.warning(f"send_email failed via {host}:{port}: {e}")
        return False
