"""Dedup — SQLite-backed alert dedup with configurable per-key window."""
from __future__ import annotations

import sqlite3
import time
from pathlib import Path

import pytest

from ops.alerter.dedup import Dedup


@pytest.fixture
def dedup(tmp_path: Path) -> Dedup:
    return Dedup(db_path=str(tmp_path / "dedup.sqlite"))


def test_first_fire_is_allowed(dedup: Dedup):
    assert dedup.should_fire("breaker.tripped.daily", window_sec=1800) is True


def test_second_fire_within_window_is_blocked(dedup: Dedup):
    dedup.should_fire("breaker.tripped.daily", window_sec=1800)
    # Immediately again
    assert dedup.should_fire("breaker.tripped.daily", window_sec=1800) is False


def test_fire_after_window_is_allowed(dedup: Dedup):
    """Manually rewind last_fired_ts to simulate elapsed window."""
    dedup.should_fire("breaker.tripped.daily", window_sec=1800)
    # Rewind 31 minutes
    with sqlite3.connect(dedup.db_path) as conn:
        conn.execute(
            "UPDATE alerts SET last_fired_ts = ? WHERE alert_key = ?",
            (int(time.time()) - 31 * 60, "breaker.tripped.daily"),
        )
    assert dedup.should_fire("breaker.tripped.daily", window_sec=1800) is True


def test_fire_count_increments(dedup: Dedup):
    dedup.should_fire("breaker.tripped.daily", window_sec=1800)
    # Force fire again by rewinding window
    with sqlite3.connect(dedup.db_path) as conn:
        conn.execute(
            "UPDATE alerts SET last_fired_ts = ? WHERE alert_key = ?",
            (0, "breaker.tripped.daily"),
        )
    dedup.should_fire("breaker.tripped.daily", window_sec=1800)
    with sqlite3.connect(dedup.db_path) as conn:
        row = conn.execute(
            "SELECT fire_count FROM alerts WHERE alert_key = ?",
            ("breaker.tripped.daily",),
        ).fetchone()
    assert row[0] == 2


def test_corrupted_db_is_recreated(tmp_path: Path):
    """Spec §4.3: corrupt file → log WARNING + recreate. First hour after restart
    may produce 1-2 duplicate alerts; documented behavior."""
    db_path = tmp_path / "dedup.sqlite"
    db_path.write_bytes(b"this is not a valid sqlite database")
    # Construction should not raise
    d = Dedup(db_path=str(db_path))
    # Fresh DB — first fire is allowed
    assert d.should_fire("any.key", window_sec=1800) is True


# ── R-6 (2026-07-17): would_fire/mark_fired ayrımı ──────────────────────────

def test_would_fire_is_read_only(tmp_path):
    from ops.alerter.dedup import Dedup
    d = Dedup(str(tmp_path / "d.sqlite"))
    assert d.would_fire("k", 3600) is True
    # Kayıt düşülmedi → hâlâ ateşlenebilir
    assert d.would_fire("k", 3600) is True
    d.mark_fired("k")
    assert d.would_fire("k", 3600) is False


def test_mark_fired_increments_count(tmp_path):
    import sqlite3
    from ops.alerter.dedup import Dedup
    d = Dedup(str(tmp_path / "d.sqlite"))
    d.mark_fired("k")
    d.mark_fired("k")
    with sqlite3.connect(d.db_path) as conn:
        row = conn.execute("SELECT fire_count FROM alerts WHERE alert_key='k'").fetchone()
    assert row[0] == 2
