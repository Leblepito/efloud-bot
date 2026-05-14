"""Overseer state — SQLite heartbeat + per-day LLM-usage counters.

Heartbeat lives in a single row so we always have an O(1) lookup; LLM usage
is keyed on UTC date so the counter naturally resets at midnight UTC without
a background job."""
from __future__ import annotations

import json
import sqlite3
import time
from datetime import datetime, timezone
from pathlib import Path


def _make_state(tmp_path: Path):
    from ops.overseer.state import OverseerState
    return OverseerState(str(tmp_path / "overseer.sqlite"))


def test_write_heartbeat_persists_to_sqlite(tmp_path):
    """Heartbeat row should land in SQLite within ~1s of write."""
    state = _make_state(tmp_path)
    before = int(time.time())
    state.write_heartbeat()
    after = int(time.time())

    db_path = tmp_path / "overseer.sqlite"
    conn = sqlite3.connect(str(db_path))
    try:
        row = conn.execute("SELECT ts FROM heartbeat").fetchone()
    finally:
        conn.close()

    assert row is not None
    assert before <= row[0] <= after


def test_heartbeat_age_seconds_returns_none_when_never_written(tmp_path):
    """Fresh DB with no heartbeat row → caller treats as unknown / never seen."""
    state = _make_state(tmp_path)
    assert state.get_heartbeat_age_seconds() is None


def test_heartbeat_age_seconds_after_write_is_small(tmp_path):
    """Age right after write must be ≥0 and small — sanity check on clock math."""
    state = _make_state(tmp_path)
    state.write_heartbeat()
    age = state.get_heartbeat_age_seconds()
    assert age is not None
    assert 0.0 <= age < 5.0


def test_record_llm_call_increments_daily_counter(tmp_path):
    """3 calls in same UTC day → counter reads 3 (proves cumulative within day)."""
    state = _make_state(tmp_path)
    state.record_llm_call(token_in=10, token_out=5)
    state.record_llm_call(token_in=20, token_out=10)
    state.record_llm_call(token_in=30, token_out=15)
    assert state.get_llm_calls_today() == 3


def test_record_llm_call_returns_running_count(tmp_path):
    """Each call returns its own post-increment count — caller can log it cheaply."""
    state = _make_state(tmp_path)
    assert state.record_llm_call(1, 1) == 1
    assert state.record_llm_call(1, 1) == 2
    assert state.record_llm_call(1, 1) == 3


def test_record_llm_call_accumulates_tokens(tmp_path):
    """token_in/out aggregated per UTC day — daily report can read totals directly."""
    state = _make_state(tmp_path)
    state.record_llm_call(token_in=100, token_out=50)
    state.record_llm_call(token_in=200, token_out=100)

    db_path = tmp_path / "overseer.sqlite"
    conn = sqlite3.connect(str(db_path))
    try:
        row = conn.execute(
            "SELECT calls, token_in, token_out FROM llm_usage"
        ).fetchone()
    finally:
        conn.close()

    assert row[0] == 2
    assert row[1] == 300
    assert row[2] == 150


def test_llm_counter_resets_at_utc_midnight(tmp_path):
    """A new UTC date gets its own row; today's count must not include yesterday's."""
    state = _make_state(tmp_path)
    db_path = tmp_path / "overseer.sqlite"

    # Pre-populate yesterday's row directly so today's first call must NOT see it.
    yesterday = "2025-01-01"
    conn = sqlite3.connect(str(db_path))
    try:
        conn.execute(
            "INSERT INTO llm_usage (date, calls, token_in, token_out) "
            "VALUES (?, ?, ?, ?)",
            (yesterday, 99, 9999, 9999),
        )
        conn.commit()
    finally:
        conn.close()

    state.reset_llm_counter_if_new_day()
    state.record_llm_call(token_in=1, token_out=1)
    assert state.get_llm_calls_today() == 1


def test_get_llm_calls_today_returns_zero_when_no_row(tmp_path):
    """Brand-new day with no calls yet → 0 (not None) so dashboards can format it."""
    state = _make_state(tmp_path)
    assert state.get_llm_calls_today() == 0


def test_heartbeat_file_atomic_write(tmp_path, monkeypatch):
    """When EFLOUD_OVERSEER_HEARTBEAT_FILE is set, write JSON {ts: …} atomically."""
    hb_file = tmp_path / "overseer_heartbeat.json"
    monkeypatch.setenv("EFLOUD_OVERSEER_HEARTBEAT_FILE", str(hb_file))

    state = _make_state(tmp_path)
    state.write_heartbeat_file()

    assert hb_file.exists()
    payload = json.loads(hb_file.read_text(encoding="utf-8"))
    assert "ts" in payload or "overseer_heartbeat_ts" in payload
    ts = payload.get("ts", payload.get("overseer_heartbeat_ts"))
    assert isinstance(ts, int)
    assert ts > 0


def test_heartbeat_file_skip_when_env_missing(tmp_path, monkeypatch):
    """No env set → no file created and no exception raised."""
    monkeypatch.delenv("EFLOUD_OVERSEER_HEARTBEAT_FILE", raising=False)
    state = _make_state(tmp_path)
    state.write_heartbeat_file()  # must not raise

    # Nothing extra dropped on disk under tmp_path beyond the SQLite file
    leftover = [p.name for p in tmp_path.iterdir() if p.suffix == ".json"]
    assert leftover == []


def test_schema_is_idempotent(tmp_path):
    """Re-opening the DB twice must NOT raise — schema bootstrap is idempotent."""
    _make_state(tmp_path)
    _make_state(tmp_path)  # second init on same file must succeed
