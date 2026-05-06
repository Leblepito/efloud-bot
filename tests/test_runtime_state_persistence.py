"""RuntimeState disk persistence — atomic write, load, corruption recovery."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from engine.safety.runtime_state import RuntimeState


def test_save_and_load_round_trip(tmp_path: Path):
    s1 = RuntimeState(state_dir=str(tmp_path))
    s1.set_fatal_exception()
    s1.increment_crash()
    s1.increment_crash()
    # Reload from disk by constructing a fresh instance over same dir
    s2 = RuntimeState(state_dir=str(tmp_path))
    snap = s2.snapshot()
    assert snap["fatal_exception_state"] is True
    assert snap["fatal_exception_set_at_ms"] is not None
    assert snap["crash_count"] == 2
    assert snap["last_crash_ms"] is not None


def test_load_returns_clean_when_file_missing(tmp_path: Path):
    s = RuntimeState(state_dir=str(tmp_path))
    snap = s.snapshot()
    assert snap["fatal_exception_state"] is False
    assert snap["crash_count"] == 0


def test_load_recovers_from_corrupted_file(tmp_path: Path):
    # Write garbage to runtime.json
    runtime_path = tmp_path / "runtime.json"
    runtime_path.write_text("this is not valid json {{{", encoding="utf-8")
    # Should not raise
    s = RuntimeState(state_dir=str(tmp_path))
    snap = s.snapshot()
    assert snap["fatal_exception_state"] is False
    assert snap["crash_count"] == 0


def test_loop_tick_not_persisted_across_restart(tmp_path: Path):
    """last_loop_tick_ms is volatile — must be None on fresh load even if it was set
    before. Reason: a stale loop_tick value loaded from disk would falsely report
    'recent activity' for a bot that hasn't actually started ticking yet.
    """
    s1 = RuntimeState(state_dir=str(tmp_path))
    s1.update_loop_tick()
    s1.set_fatal_exception()  # forces _save() so runtime.json exists
    snap1 = s1.snapshot()
    assert snap1["last_loop_tick_ms"] is not None  # set in-memory

    # Verify file does NOT contain last_loop_tick_ms
    runtime_path = tmp_path / "runtime.json"
    assert runtime_path.exists()
    on_disk = json.loads(runtime_path.read_text(encoding="utf-8"))
    assert "last_loop_tick_ms" not in on_disk or on_disk["last_loop_tick_ms"] is None

    # Fresh instance must have None for loop_tick (volatile)
    s2 = RuntimeState(state_dir=str(tmp_path))
    snap2 = s2.snapshot()
    assert snap2["last_loop_tick_ms"] is None
