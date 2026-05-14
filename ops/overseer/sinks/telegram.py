"""Thin Telegram wrapper for overseer alerts.

Delegates the actual HTTP POST to ops.alerter.telegram_client.send_message so
that token/chat_id, retry semantics, and timeouts stay consistent with the
existing alerter pipeline (single source of truth for Telegram transport).

The wrapper's job is purely to (1) read env, (2) prepend a severity glyph
that makes triage glanceable in the chat, and (3) swallow any exception so
callers never crash on transient network errors.
"""
from __future__ import annotations

import logging
import os
from typing import Final

from ops.alerter.telegram_client import send_message

log = logging.getLogger("efloud.overseer.telegram")

_SEVERITY_PREFIX: Final[dict[str, str]] = {
    "INFO": "ℹ️",  # ℹ️
    "WARN": "⚠️",  # ⚠️
    "CRITICAL": "\U0001f6a8",  # 🚨
}


def send_overseer_message(text: str, *, severity: str = "INFO") -> bool:
    """Send an overseer alert to Telegram, prefixed by a severity glyph.

    Reuses ops.alerter.telegram_client.send_message — same EFLOUD_TELEGRAM_TOKEN
    and EFLOUD_TELEGRAM_CHAT_ID env vars as the rest of the alerter pipeline.
    Returns True if the underlying send succeeded; False on missing config or
    any transport-layer failure (caller decides whether to retry).
    """
    token = os.environ.get("EFLOUD_TELEGRAM_TOKEN", "")
    chat_id = os.environ.get("EFLOUD_TELEGRAM_CHAT_ID", "")
    prefix = _SEVERITY_PREFIX.get(severity.upper(), _SEVERITY_PREFIX["INFO"])
    decorated = f"{prefix} {text}"

    try:
        return bool(send_message(token, chat_id, decorated))
    except Exception as e:  # pragma: no cover — exercised via test double
        log.warning(f"overseer telegram send raised: {e}")
        return False
