"""Crash-loop suppression — RuntimeState detection + auto-clear, healthz branch,
bot_runner startup guard, end-to-end lifecycle.
"""
from __future__ import annotations

import time
from pathlib import Path

import pytest

from engine.safety.runtime_state import (
    CRASH_LOOP_THRESHOLD,
    CRASH_LOOP_WINDOW_MS,
    CRASH_AUTO_CLEAR_AFTER_MS,
    RuntimeState,
)


@pytest.fixture
def state(tmp_path: Path) -> RuntimeState:
    return RuntimeState(state_dir=str(tmp_path))


# ─────────────────────────────────────────────────────────────────────
# Task 1: RuntimeState.is_in_crash_loop() + auto-clear
# ─────────────────────────────────────────────────────────────────────


def test_is_in_crash_loop_returns_true_when_threshold_met_in_window(state: RuntimeState):
    """3+ crashes within last 30 min → in crash loop."""
    # No crashes yet → False
    assert state.is_in_crash_loop() is False

    # Simulate 3 crashes, all within window
    for _ in range(CRASH_LOOP_THRESHOLD):
        state.increment_crash()
    # last_crash_ms is now (essentially) now
    assert state.is_in_crash_loop() is True


def test_is_in_crash_loop_returns_false_when_outside_window(state: RuntimeState):
    """3+ crashes but last one was >30 min ago → not in crash loop (recovered)."""
    for _ in range(CRASH_LOOP_THRESHOLD):
        state.increment_crash()
    assert state.is_in_crash_loop() is True

    # Rewind last_crash_ms to 31 min ago
    thirty_one_min_ago = int(time.time() * 1000) - (31 * 60 * 1000)
    state.last_crash_ms = thirty_one_min_ago
    assert state.is_in_crash_loop() is False


def test_update_loop_tick_clears_crash_count_after_60min_clean_uptime(state: RuntimeState):
    """If crash_count > 0 AND last_crash_ms is 60+ min ago AND a clean tick arrives,
    auto-clear crash_count to 0. Mirrors the 5-min fatal_exception auto-clear pattern.
    """
    state.increment_crash()
    state.increment_crash()
    assert state.snapshot()["crash_count"] == 2

    # Rewind last_crash_ms to 61 min ago
    sixty_one_min_ago = int(time.time() * 1000) - (61 * 60 * 1000)
    state.last_crash_ms = sixty_one_min_ago

    state.update_loop_tick()  # this should auto-clear
    snap = state.snapshot()
    assert snap["crash_count"] == 0
    assert snap["last_crash_ms"] is None
