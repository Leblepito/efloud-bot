"""SQLite-backed overseer state — heartbeat + LLM-usage counters.

Two-table schema (heartbeat single-row, llm_usage keyed on UTC date) keeps
all lookups O(1) without a background reset job: a new UTC day simply
produces a new row, so yesterday's counts never leak into today's.

The optional EFLOUD_OVERSEER_HEARTBEAT_FILE env mirrors the SQLite heartbeat
to a small JSON file the alerter (or an external watchdog) can poll without
opening the DB — same atomic-rename pattern used by ops.alerter.alerter.
"""
from __future__ import annotations

import json
import logging
import os
import sqlite3
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

log = logging.getLogger("efloud.overseer.state")


def _today_utc() -> str:
    """Today's UTC date as ISO YYYY-MM-DD — key for the per-day usage row."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


class OverseerState:
    """Persistent heartbeat + LLM-usage store used by the overseer agent."""

    def __init__(self, db_path: str):
        """Open (or create) the SQLite DB at db_path and ensure schema exists.

        Schema bootstrap is idempotent: CREATE TABLE IF NOT EXISTS, so re-opening
        the same file on every overseer tick is safe and cheap.
        """
        self.db_path = db_path
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    def _connect(self) -> sqlite3.Connection:
        """Short-lived connection per call — overseer is low-frequency, so we
        avoid keeping a connection open across long sleeps."""
        return sqlite3.connect(self.db_path, timeout=5.0)

    def _init_schema(self) -> None:
        """Create tables if missing. Called from __init__; safe to repeat."""
        conn = self._connect()
        try:
            conn.execute(
                "CREATE TABLE IF NOT EXISTS heartbeat ("
                "  id INTEGER PRIMARY KEY CHECK (id = 1),"
                "  ts INTEGER NOT NULL"
                ")"
            )
            conn.execute(
                "CREATE TABLE IF NOT EXISTS llm_usage ("
                "  date TEXT PRIMARY KEY,"
                "  calls INTEGER NOT NULL DEFAULT 0,"
                "  token_in INTEGER NOT NULL DEFAULT 0,"
                "  token_out INTEGER NOT NULL DEFAULT 0"
                ")"
            )
            conn.commit()
        finally:
            conn.close()

    # ---- heartbeat ----------------------------------------------------------

    def write_heartbeat(self) -> None:
        """UPSERT the single-row heartbeat to UTC now (epoch seconds)."""
        now = int(time.time())
        conn = self._connect()
        try:
            conn.execute(
                "INSERT INTO heartbeat (id, ts) VALUES (1, ?) "
                "ON CONFLICT(id) DO UPDATE SET ts = excluded.ts",
                (now,),
            )
            conn.commit()
        finally:
            conn.close()

    def get_heartbeat_age_seconds(self) -> Optional[float]:
        """Seconds since the last write_heartbeat, or None if never written.

        Returning None (not 0) lets the caller distinguish "fresh process,
        nothing yet" from "process alive and just pinged" without ambiguity.
        """
        conn = self._connect()
        try:
            row = conn.execute("SELECT ts FROM heartbeat WHERE id = 1").fetchone()
        finally:
            conn.close()
        if row is None:
            return None
        return float(time.time() - row[0])

    def write_heartbeat_file(self) -> None:
        """Mirror heartbeat to EFLOUD_OVERSEER_HEARTBEAT_FILE if set; else no-op.

        Atomic write (tmp + os.replace) so a concurrent reader never observes a
        half-written JSON file — same pattern as ops.alerter.alerter._write_heartbeat.
        """
        path_str = os.environ.get("EFLOUD_OVERSEER_HEARTBEAT_FILE", "")
        if not path_str:
            return
        try:
            path = Path(path_str)
            path.parent.mkdir(parents=True, exist_ok=True)
            tmp = Path(path_str + ".tmp")
            tmp.write_text(
                json.dumps({"ts": int(time.time())}),
                encoding="utf-8",
            )
            os.replace(tmp, path)
        except OSError as e:
            log.warning(f"overseer heartbeat file write failed: {e}")

    # ---- LLM usage ----------------------------------------------------------

    def record_llm_call(self, token_in: int, token_out: int) -> int:
        """Increment today's UTC counter and add token deltas. Returns new calls count.

        UPSERT keyed on UTC date so the first call of a new UTC day creates a
        fresh row — no explicit midnight reset job required.
        """
        date = _today_utc()
        conn = self._connect()
        try:
            conn.execute(
                "INSERT INTO llm_usage (date, calls, token_in, token_out) "
                "VALUES (?, 1, ?, ?) "
                "ON CONFLICT(date) DO UPDATE SET "
                "  calls = calls + 1,"
                "  token_in = token_in + excluded.token_in,"
                "  token_out = token_out + excluded.token_out",
                (date, token_in, token_out),
            )
            conn.commit()
            row = conn.execute(
                "SELECT calls FROM llm_usage WHERE date = ?", (date,)
            ).fetchone()
        finally:
            conn.close()
        return int(row[0]) if row else 0

    def get_llm_calls_today(self) -> int:
        """Calls recorded for today's UTC date (0 if none yet)."""
        date = _today_utc()
        conn = self._connect()
        try:
            row = conn.execute(
                "SELECT calls FROM llm_usage WHERE date = ?", (date,)
            ).fetchone()
        finally:
            conn.close()
        return int(row[0]) if row else 0

    def reset_llm_counter_if_new_day(self) -> None:
        """No-op when today's row already exists; otherwise ensure a zero-row for today.

        Because today's row is auto-created on the next record_llm_call() via
        UPSERT, this function is mostly defensive — it guarantees that callers
        reading get_llm_calls_today() on a brand-new UTC day see 0 instead of
        accidentally inheriting yesterday's counter through any stray UPDATE.
        """
        date = _today_utc()
        conn = self._connect()
        try:
            conn.execute(
                "INSERT OR IGNORE INTO llm_usage (date, calls, token_in, token_out) "
                "VALUES (?, 0, 0, 0)",
                (date,),
            )
            conn.commit()
        finally:
            conn.close()
