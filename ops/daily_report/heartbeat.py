"""Heartbeat staleness check for daily report.

Reads `state/alerter_heartbeat.json` (written by Step 4 alerter every 60s) and
determines whether the alerter is alive. Stale heartbeat → daily report adds
'ALERTER DOWN' subject prefix per spec §4.3.
"""
from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import Optional, Tuple

log = logging.getLogger("efloud.daily_report.heartbeat")

# Spec §4.3: alerter writes every 60s; >2h since last write means alerter died
HEARTBEAT_STALE_AFTER_SEC = 2 * 60 * 60


def check_alerter_heartbeat(path: str) -> Tuple[bool, Optional[int]]:
    """Return (stale, age_sec).

    - stale=True if file missing OR ts is older than HEARTBEAT_STALE_AFTER_SEC.
    - age_sec is None if the file is missing or unreadable; otherwise the
      number of seconds since the last heartbeat write.
    """
    p = Path(path)
    if not p.exists():
        log.warning(f"alerter heartbeat file missing: {path}")
        return (True, None)
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        ts = int(data["alerter_heartbeat_ts"])
    except (json.JSONDecodeError, KeyError, TypeError, ValueError) as e:
        log.warning(f"alerter heartbeat file corrupt/malformed ({path}): {e}")
        return (True, None)

    age = int(time.time()) - ts
    stale = age >= HEARTBEAT_STALE_AFTER_SEC
    return (stale, age)
