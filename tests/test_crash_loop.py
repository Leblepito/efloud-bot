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


# ─────────────────────────────────────────────────────────────────────
# Task 2: evaluate_healthz suspended branch
# ─────────────────────────────────────────────────────────────────────

from backend.healthz import evaluate_healthz


def test_evaluate_healthz_returns_200_suspended_when_crash_loop_active(state: RuntimeState):
    """Crash-loop suspension intentionally returns 200 (not 503) so the autoheal
    sidecar doesn't restart-loop the container. The failures list contains
    'crash_loop_suspended' for the alerter (Step 4) and daily-report (Step 5) to
    key off.
    """
    # Force crash-loop state
    for _ in range(CRASH_LOOP_THRESHOLD):
        state.increment_crash()
    assert state.is_in_crash_loop() is True

    # Make tick + ping fresh so the regular checks would otherwise pass
    now_ms = int(time.time() * 1000)
    state.last_loop_tick_ms = now_ms - 5_000
    state.last_exchange_ping_ms = now_ms - 5_000

    code, payload = evaluate_healthz(state, breaker_halted=False, now_ms=now_ms)
    assert code == 200, f"expected 200 in suspended mode (autoheal-friendly), got {code}: {payload}"
    assert payload["status"] == "suspended"
    assert "crash_loop_suspended" in payload["failures"]


def test_evaluate_healthz_normal_503_path_unchanged_when_not_in_crash_loop(state: RuntimeState):
    """When NOT in crash-loop, the existing 503 logic must still fire for normal
    failures (loop_tick_never, etc.). Regression check on the Step 2 contract.
    """
    # No crashes → not in crash loop
    assert state.is_in_crash_loop() is False

    # Bot just started — no tick yet
    now_ms = int(time.time() * 1000)
    code, payload = evaluate_healthz(state, breaker_halted=False, now_ms=now_ms)
    assert code == 503
    assert payload["status"] == "unhealthy"
    assert "loop_tick_never" in payload["failures"]
