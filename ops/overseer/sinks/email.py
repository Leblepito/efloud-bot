"""Thin SMTP wrapper for overseer daily-style reports.

Delegates the actual SMTP send to ops.daily_report.smtp_client.send_email so
TLS, login, and timeout policy stay consistent with the daily-report cron
(single source of truth for outbound SMTP).

Reads SMTP config from env (same vars as ops.daily_report.report); body is
treated as markdown but currently shipped as plain text — a follow-up can
render full HTML once the overseer body templates settle.
"""
from __future__ import annotations

import logging
import os
from typing import Optional

from ops.daily_report.smtp_client import send_email

log = logging.getLogger("efloud.overseer.email")


def _markdown_to_plain(body_markdown: str) -> str:
    """Strip leading heading hashes so SMTP plain-text stays legible.

    Full markdown→HTML render is a follow-up; this keeps the wire payload
    readable in any client without pulling a markdown dep and without
    mangling heading text (case + content preserved).
    """
    out_lines = []
    for line in body_markdown.splitlines():
        if line.lstrip().startswith("#"):
            out_lines.append(line.lstrip("#").lstrip())
        else:
            out_lines.append(line)
    return "\n".join(out_lines)


def send_overseer_email(
    subject: str,
    body_markdown: str,
    *,
    to: Optional[str] = None,
) -> bool:
    """Send an overseer report via SMTP. Returns True on success, False otherwise.

    `to=None` falls back to EFLOUD_SMTP_TO so the cron path stays env-driven;
    an explicit `to` argument overrides for ad-hoc routing (e.g. tests, on-call
    handoff). Any exception from the underlying SMTP client is swallowed and
    converted to False so the caller can decide whether to escalate.
    """
    host = os.environ.get("EFLOUD_SMTP_HOST", "smtp.gmail.com")
    port = int(os.environ.get("EFLOUD_SMTP_PORT", "587"))
    username = os.environ.get("EFLOUD_SMTP_USERNAME", "")
    password = os.environ.get("EFLOUD_SMTP_PASSWORD", "")
    from_addr = os.environ.get("EFLOUD_SMTP_FROM", username)
    to_addr = to if to is not None else os.environ.get("EFLOUD_SMTP_TO", "")

    if not to_addr:
        log.warning("send_overseer_email skipped: no recipient (EFLOUD_SMTP_TO unset)")
        return False

    body_plain = _markdown_to_plain(body_markdown)

    try:
        return bool(
            send_email(
                host=host,
                port=port,
                username=username,
                password=password,
                from_addr=from_addr,
                to_addr=to_addr,
                subject=subject,
                body=body_plain,
            )
        )
    except Exception as e:  # pragma: no cover — exercised via test double
        log.warning(f"overseer email send raised: {e}")
        return False
