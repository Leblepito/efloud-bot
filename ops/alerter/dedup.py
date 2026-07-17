"""SQLite-backed alert dedup. Persistent across alerter restarts.

Schema: (alert_key TEXT PRIMARY KEY, last_fired_ts INTEGER, fire_count INTEGER).
On corrupt-file detection, the file is moved aside and a fresh DB is created
(spec §4.3 "auto-recreate on corruption" — first hour after restart may produce
1-2 duplicates).
"""
from __future__ import annotations

import logging
import os
import sqlite3
import time
from pathlib import Path

log = logging.getLogger("efloud.alerter.dedup")

_SCHEMA = """
CREATE TABLE IF NOT EXISTS alerts (
    alert_key       TEXT PRIMARY KEY,
    last_fired_ts   INTEGER NOT NULL,
    fire_count      INTEGER NOT NULL DEFAULT 0
)
"""


class Dedup:
    """SQLite dedup keyed by alert_key with per-key time windows."""

    def __init__(self, db_path: str):
        self.db_path = db_path
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self._open_or_recreate()

    def _open_or_recreate(self) -> None:
        """Open the DB; if file exists but is corrupt, move it aside and create fresh."""
        if Path(self.db_path).exists():
            conn = None
            try:
                conn = sqlite3.connect(self.db_path)
                # Cheap integrity probe
                conn.execute("PRAGMA integrity_check").fetchone()
                conn.execute(_SCHEMA)
                conn.commit()
                conn.close()
                return
            except (sqlite3.DatabaseError, sqlite3.OperationalError) as e:
                # Ensure handle is released before attempting rename (Windows lock).
                if conn is not None:
                    try:
                        conn.close()
                    except sqlite3.Error:
                        pass
                log.warning(
                    f"alerter dedup DB at {self.db_path} corrupt ({e}); "
                    f"moving aside and recreating"
                )
                backup = f"{self.db_path}.corrupt.{int(time.time())}"
                try:
                    os.replace(self.db_path, backup)
                except OSError:
                    Path(self.db_path).unlink(missing_ok=True)
        # Fresh DB
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(_SCHEMA)

    def would_fire(self, alert_key: str, window_sec: int) -> bool:
        """Read-only kontrol: bu alert şu an ateşlenebilir mi? Kayıt YAPMAZ.

        R-6 fix (2026-07-17): dedup kaydı teslimattan ÖNCE düşülünce, başarısız
        bir Telegram gönderimi tek-atımlık transition alert'ini (breaker trip)
        window boyunca kalıcı yutuyordu. Çağıran sıra: would_fire → send →
        başarılıysa mark_fired.
        """
        now = int(time.time())
        with sqlite3.connect(self.db_path) as conn:
            row = conn.execute(
                "SELECT last_fired_ts FROM alerts WHERE alert_key = ?",
                (alert_key,),
            ).fetchone()
        if row is None:
            return True
        return now - row[0] >= window_sec

    def mark_fired(self, alert_key: str) -> None:
        """Başarılı teslimat SONRASI dedup kaydını düş (bkz. would_fire)."""
        now = int(time.time())
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "INSERT INTO alerts (alert_key, last_fired_ts, fire_count) "
                "VALUES (?, ?, 1) "
                "ON CONFLICT(alert_key) DO UPDATE SET "
                "last_fired_ts = excluded.last_fired_ts, "
                "fire_count = alerts.fire_count + 1",
                (alert_key, now),
            )

    def should_fire(self, alert_key: str, window_sec: int) -> bool:
        """Return True if this alert is allowed to fire (and record the fire);
        False if it's a duplicate within window_sec.

        Side effect on True: inserts/updates the alert row, increments fire_count.
        """
        now = int(time.time())
        with sqlite3.connect(self.db_path) as conn:
            row = conn.execute(
                "SELECT last_fired_ts, fire_count FROM alerts WHERE alert_key = ?",
                (alert_key,),
            ).fetchone()
            if row is not None:
                last_ts, fire_count = row
                if now - last_ts < window_sec:
                    return False
                # Window elapsed — allow and bump count
                conn.execute(
                    "UPDATE alerts SET last_fired_ts = ?, fire_count = ? "
                    "WHERE alert_key = ?",
                    (now, fire_count + 1, alert_key),
                )
                return True
            # First fire
            conn.execute(
                "INSERT INTO alerts (alert_key, last_fired_ts, fire_count) "
                "VALUES (?, ?, 1)",
                (alert_key, now),
            )
            return True
