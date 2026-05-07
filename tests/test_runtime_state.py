"""RuntimeState in-memory behavior — locks, transitions, auto-clear."""
from __future__ import annotations

import time
from pathlib import Path

import pytest

from engine.safety.runtime_state import RuntimeState


@pytest.fixture
def state(tmp_path: Path) -> RuntimeState:
    return RuntimeState(state_dir=str(tmp_path))


def test_initial_fields_are_none_or_zero(state: RuntimeState):
    snap = state.snapshot()
    assert snap["last_loop_tick_ms"] is None
    assert snap["last_exchange_ping_ms"] is None
    assert snap["fatal_exception_state"] is False
    assert snap["fatal_exception_set_at_ms"] is None
    assert snap["crash_count"] == 0
    assert snap["last_crash_ms"] is None


def test_update_loop_tick_sets_timestamp(state: RuntimeState):
    before = int(time.time() * 1000)
    state.update_loop_tick()
    after = int(time.time() * 1000)
    snap = state.snapshot()
    assert snap["last_loop_tick_ms"] is not None
    assert before <= snap["last_loop_tick_ms"] <= after


def test_update_exchange_ping_sets_timestamp(state: RuntimeState):
    before = int(time.time() * 1000)
    state.update_exchange_ping()
    after = int(time.time() * 1000)
    snap = state.snapshot()
    assert snap["last_exchange_ping_ms"] is not None
    assert before <= snap["last_exchange_ping_ms"] <= after


def test_set_fatal_exception_records_flag_and_timestamp(state: RuntimeState):
    state.set_fatal_exception()
    snap = state.snapshot()
    assert snap["fatal_exception_state"] is True
    assert snap["fatal_exception_set_at_ms"] is not None


def test_fatal_auto_clears_after_5min_clean_ticks(state: RuntimeState):
    """If 5+ minutes have elapsed since fatal flag was set AND a fresh tick arrives, clear."""
    state.set_fatal_exception()
    # Manually rewind the set_at_ms by 6 minutes to simulate elapsed time
    six_min_ago = int(time.time() * 1000) - 6 * 60 * 1000
    state.fatal_exception_set_at_ms = six_min_ago
    state.update_loop_tick()  # this should clear the flag
    snap = state.snapshot()
    assert snap["fatal_exception_state"] is False
    assert snap["fatal_exception_set_at_ms"] is None


def test_fatal_does_not_clear_before_5min(state: RuntimeState):
    state.set_fatal_exception()
    # Only 2 minutes elapsed
    two_min_ago = int(time.time() * 1000) - 2 * 60 * 1000
    state.fatal_exception_set_at_ms = two_min_ago
    state.update_loop_tick()  # should NOT clear yet
    snap = state.snapshot()
    assert snap["fatal_exception_state"] is True


def test_increment_crash_increments_counter(state: RuntimeState):
    assert state.snapshot()["crash_count"] == 0
    state.increment_crash()
    assert state.snapshot()["crash_count"] == 1
    state.increment_crash()
    assert state.snapshot()["crash_count"] == 2
