"""Telegram alerter — main loop.

Inputs:
- Bot's JSON log file (tailed, per spec §4.3)
- Bot's /healthz endpoint (polled every 30s)

Outputs:
- Telegram messages on rule matches (deduplicated via SQLite)
- Heartbeat written to state/alerter_heartbeat.json every 60s

Run as: python -m ops.alerter.alerter
"""
from __future__ import annotations

import json
import logging
import os
import time
import urllib.error
import urllib.request
from collections import deque
from pathlib import Path

from ops.alerter.dedup import Dedup
from ops.alerter.rules import RULES, Rule
from ops.alerter.telegram_client import send_message
from ops.alerter.formatter import format_alert_with_ai

# Configure logging — alerter has its own simple text format, distinct from bot's JSON
logging.basicConfig(
    level=os.environ.get("LOG_LEVEL", "INFO"),
    format="%(asctime)s | %(name)-22s | %(levelname)-5s | %(message)s",
)
log = logging.getLogger("efloud.alerter")

# Cadences
LOG_TAIL_INTERVAL_SEC = 1.0
HEALTHZ_POLL_INTERVAL_SEC = 30.0
HEARTBEAT_INTERVAL_SEC = 60.0

# Rate limit (spec §4.3): 50 messages/min hard cap
RATE_LIMIT_MAX_PER_MIN = 50

# Configurable via env
LOG_FILE = os.environ.get("EFLOUD_LOG_FILE", "/app/logs/efloud_bot.log")
HEALTHZ_URL = os.environ.get("EFLOUD_HEALTHZ_URL", "http://efloud-bot:8080/healthz")
DEDUP_DB = os.environ.get("EFLOUD_ALERTER_DEDUP_DB", "/app/state/alerter_dedup.sqlite")
HEARTBEAT_FILE = os.environ.get(
    "EFLOUD_ALERTER_HEARTBEAT_FILE", "/app/state/alerter_heartbeat.json"
)
TELEGRAM_TOKEN = os.environ.get("EFLOUD_TELEGRAM_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("EFLOUD_TELEGRAM_CHAT_ID", "")


class Alerter:
    def __init__(self):
        self.dedup = Dedup(db_path=DEDUP_DB)
        self.log_offset = 0  # byte offset in log file
        self.healthz_history: dict = {}  # rule.match_health scratchpad
        # Rate limit: rolling 60-second window of message timestamps
        self.send_timestamps: deque = deque()
        # Cadence trackers
        self.next_healthz_poll = 0.0
        self.next_heartbeat = 0.0
        # Stat counters (logged hourly)
        self.stat_log_lines = 0
        self.stat_alerts_fired = 0
        self.stat_alerts_deduped = 0
        self.stat_alerts_rate_limited = 0
        self.next_stats_log = time.time() + 3600

    def run(self) -> None:
        log.info(f"alerter starting — log_file={LOG_FILE} healthz={HEALTHZ_URL}")
        if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
            log.warning(
                "EFLOUD_TELEGRAM_TOKEN or EFLOUD_TELEGRAM_CHAT_ID not set — "
                "alerts will be matched but NOT sent (dry-run mode)"
            )
        # Initial offset: skip existing log content (we don't want to alert on
        # historical events at startup; new lines from now on are what matters)
        self._init_log_offset()

        while True:
            now = time.monotonic()
            self._tail_logs()
            if now >= self.next_healthz_poll:
                self._poll_healthz()
                self.next_healthz_poll = now + HEALTHZ_POLL_INTERVAL_SEC
            if now >= self.next_heartbeat:
                self._write_heartbeat()
                self.next_heartbeat = now + HEARTBEAT_INTERVAL_SEC
            if time.time() >= self.next_stats_log:
                self._log_hourly_stats()
            time.sleep(LOG_TAIL_INTERVAL_SEC)

    def _init_log_offset(self) -> None:
        try:
            self.log_offset = Path(LOG_FILE).stat().st_size
        except FileNotFoundError:
            self.log_offset = 0

    def _tail_logs(self) -> None:
        try:
            stat = Path(LOG_FILE).stat()
        except FileNotFoundError:
            return
        if stat.st_size < self.log_offset:
            # Log was rotated (truncated or replaced); restart from start
            log.info("log file shrank — assuming rotation, resetting offset")
            self.log_offset = 0
        if stat.st_size == self.log_offset:
            return  # no new content
        with open(LOG_FILE, "r", encoding="utf-8", errors="replace") as f:
            f.seek(self.log_offset)
            for line in f:
                self.stat_log_lines += 1
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                except json.JSONDecodeError:
                    # Plain (non-JSON) log line — alerter cannot match; skip silently
                    continue
                self._dispatch_log(rec)
            self.log_offset = f.tell()

    def _dispatch_log(self, rec: dict) -> None:
        for rule in RULES:
            text = rule.match_log(rec)
            if text:
                self._maybe_fire(rule, text)

    def _poll_healthz(self) -> None:
        try:
            req = urllib.request.Request(HEALTHZ_URL)
            with urllib.request.urlopen(req, timeout=5) as resp:
                body = resp.read().decode("utf-8")
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            log.warning(f"healthz poll failed: {e}")
            return
        try:
            payload = json.loads(body)
        except json.JSONDecodeError:
            log.warning(f"healthz body not JSON: {body[:200]}")
            return
        for rule in RULES:
            text = rule.match_health(payload, self.healthz_history)
            if text:
                self._maybe_fire(rule, text)

    def _maybe_fire(self, rule: Rule, text: str) -> None:
        if not self.dedup.should_fire(rule.alert_key, rule.dedup_window_sec):
            self.stat_alerts_deduped += 1
            return
        # Rate limit: drop if 50 already sent in last 60s
        now = time.time()
        while self.send_timestamps and self.send_timestamps[0] < now - 60:
            self.send_timestamps.popleft()
        if len(self.send_timestamps) >= RATE_LIMIT_MAX_PER_MIN:
            self.stat_alerts_rate_limited += 1
            log.warning(
                f"rate limit hit ({RATE_LIMIT_MAX_PER_MIN}/min) — dropping {rule.alert_key}"
            )
            return
        # AI-based structured formatting wrapper (with zero-friction fallback)
        formatted_text = format_alert_with_ai(text, rule.severity, rule.alert_key)
        ok = send_message(TELEGRAM_TOKEN, TELEGRAM_CHAT_ID, formatted_text)
        if ok:
            self.send_timestamps.append(now)
            self.stat_alerts_fired += 1
            log.info(f"alert fired: {rule.alert_key}")

    def _write_heartbeat(self) -> None:
        try:
            Path(HEARTBEAT_FILE).parent.mkdir(parents=True, exist_ok=True)
            tmp = Path(HEARTBEAT_FILE + ".tmp")
            tmp.write_text(
                json.dumps({"alerter_heartbeat_ts": int(time.time())}),
                encoding="utf-8",
            )
            os.replace(tmp, HEARTBEAT_FILE)
        except OSError as e:
            log.warning(f"heartbeat write failed: {e}")

    def _log_hourly_stats(self) -> None:
        log.info(
            f"hourly stats — log_lines={self.stat_log_lines} "
            f"fired={self.stat_alerts_fired} deduped={self.stat_alerts_deduped} "
            f"rate_limited={self.stat_alerts_rate_limited}"
        )
        self.stat_log_lines = 0
        self.stat_alerts_fired = 0
        self.stat_alerts_deduped = 0
        self.stat_alerts_rate_limited = 0
        self.next_stats_log = time.time() + 3600


def main() -> None:
    Alerter().run()


if __name__ == "__main__":
    main()
