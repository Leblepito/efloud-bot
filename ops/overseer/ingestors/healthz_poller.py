"""Bot healthz endpoint poller — feeds rule_bot_unhealthy.

Adapts ops/alerter/alerter.py _poll_healthz (L133-149) but adds explicit
streak/last-ok tracking so the rule layer can read structured state without
having to scan history. Uses urllib.request (stdlib only, no aiohttp/httpx
dependency — alerter precedent).

Network failures are NEVER propagated: any exception during poll_once()
collapses to status_code=0 / ok=False, and consecutive_failures bumps.
"""
from __future__ import annotations

import logging
import time
import urllib.error
import urllib.request
from typing import Optional

log = logging.getLogger("efloud.overseer.healthz")


class HealthzPoller:
    """Polls a bot healthz URL on demand; tracks streaks for downstream rules.

    State is purely in-memory — the overseer process is long-lived so we don't
    need to persist across restarts (a fresh start naturally rebuilds the
    streak as it polls). This keeps the poller free of file/DB coupling.
    """

    def __init__(self, url: str, timeout_sec: float = 5.0):
        self.url = url
        self.timeout_sec = timeout_sec
        self._last_status_code: int = 0
        self._last_ok_ts: Optional[int] = None
        self._consecutive_failures: int = 0

    def poll_once(self) -> dict:
        """Single HTTP GET. Returns:
            {"status_code": int, "ok": bool, "checked_at": int}
        Updates streak counters. Network/HTTP errors collapse to
        status_code=0 (no response received) and ok=False.
        """
        checked_at = int(time.time())
        status_code = 0
        try:
            req = urllib.request.Request(self.url)
            with urllib.request.urlopen(req, timeout=self.timeout_sec) as resp:
                # urllib HTTPResponse exposes both .status (Py3.9+) and .code
                status_code = int(getattr(resp, "status", None) or resp.code)
                # Drain body so the connection can be reused / closed cleanly;
                # we don't parse it here (the rule layer doesn't need payload).
                resp.read()
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            log.debug(f"healthz poll network error: {e}")
            status_code = 0
        except Exception as e:  # pragma: no cover — defensive net
            log.warning(f"healthz poll unexpected error: {e}")
            status_code = 0

        ok = status_code == 200
        self._last_status_code = status_code
        if ok:
            self._last_ok_ts = checked_at
            self._consecutive_failures = 0
        else:
            self._consecutive_failures += 1

        return {
            "status_code": status_code,
            "ok": ok,
            "checked_at": checked_at,
        }

    def state(self) -> dict:
        """Snapshot of accumulated state for the rules state-dict.

        Shape matches rules.py expectations:
            {"status_code", "last_ok_ts", "consecutive_failures"}
        """
        return {
            "status_code": self._last_status_code,
            "last_ok_ts": self._last_ok_ts,
            "consecutive_failures": self._consecutive_failures,
        }
