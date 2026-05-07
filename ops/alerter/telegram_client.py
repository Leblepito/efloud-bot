"""Minimal Telegram bot API client. Stdlib urllib; no `requests` dep.

Single-purpose: POST sendMessage to chat_id. Returns True on 2xx, False on
network/API error. Errors are logged WARNING — caller decides whether to
retry, escalate, or drop.
"""
from __future__ import annotations

import json
import logging
import urllib.error
import urllib.parse
import urllib.request

log = logging.getLogger("efloud.alerter.telegram")

API_BASE = "https://api.telegram.org"
TIMEOUT_SEC = 10


def send_message(
    token: str,
    chat_id: str,
    text: str,
    parse_mode: str = "HTML",
) -> bool:
    """POST sendMessage to Telegram. Returns True on 2xx, False on any error.

    Telegram rate limit is ~30 msg/sec; alerter's caller is expected to enforce
    a 50/min hard cap (spec §4.3) — this function does not throttle.
    """
    if not token or not chat_id:
        log.warning("send_message skipped: missing token or chat_id")
        return False

    url = f"{API_BASE}/bot{token}/sendMessage"
    payload = urllib.parse.urlencode({
        "chat_id": chat_id,
        "text": text,
        "parse_mode": parse_mode,
    }).encode("utf-8")

    req = urllib.request.Request(url, data=payload, method="POST")
    req.add_header("Content-Type", "application/x-www-form-urlencoded")

    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT_SEC) as resp:
            if 200 <= resp.status < 300:
                return True
            body = resp.read(500).decode("utf-8", errors="replace")
            log.warning(f"telegram sendMessage HTTP {resp.status}: {body}")
            return False
    except urllib.error.HTTPError as e:
        body = e.read(500).decode("utf-8", errors="replace") if e.fp else ""
        log.warning(f"telegram sendMessage HTTPError {e.code}: {body}")
        return False
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        log.warning(f"telegram sendMessage transport error: {e}")
        return False
