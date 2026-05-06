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


# ─────────────────────────────────────────────────────────────────────
# Task 3: bot_runner.start() guard
# ─────────────────────────────────────────────────────────────────────


def test_bot_runner_start_skips_trading_loop_when_crash_loop_active(monkeypatch, tmp_path: Path, caplog):
    """If crash-loop is active at start-time, BotRunner.start() must short-circuit
    BEFORE any other init logic (config load, exchange client, etc.).

    Verified by 3 signals together (any one alone is ambiguous):
      1. log.critical("⛔ CRASH LOOP DETECTED ...") fired
      2. runner.task remained None (no trading task created)
      3. runner.last_error remained None (guard returned cleanly, NOT via the
         "config not found" error branch — which would also leave task=None
         but would set last_error)
    """
    import asyncio
    import logging

    # Set state dir BEFORE BotRunner() — RuntimeState reads EFLOUD_STATE_DIR
    # eagerly in __init__ (verified Step 3.0).
    monkeypatch.setenv("EFLOUD_STATE_DIR", str(tmp_path))

    # Defensively point at a clearly-invalid config path so IF the crash-loop
    # guard fails to short-circuit, the next branch ("config not found" at
    # bot_runner.py:73-77) sets last_error — making the test failure
    # diagnosable instead of silent.
    monkeypatch.setenv("EFLOUD_CONFIG_PATH", "/nonexistent/should-never-load.yaml")

    from backend.bot_runner import BotRunner
    runner = BotRunner()

    # Force crash-loop state on this runner's RuntimeState instance
    for _ in range(CRASH_LOOP_THRESHOLD):
        runner.runtime_state.increment_crash()
    assert runner.runtime_state.is_in_crash_loop() is True

    # Logger name in backend/bot_runner.py is "efloud.runner" (verified Step 3.0).
    with caplog.at_level(logging.CRITICAL, logger="efloud.runner"):
        # Wrap with timeout: if the guard regresses and start() actually runs the
        # full init path, the test would otherwise hang / leak resources.
        asyncio.run(asyncio.wait_for(runner.start(), timeout=2.0))

    assert runner.task is None, (
        "expected runner.task to remain None during crash-loop suspension"
    )
    assert runner.last_error is None, (
        f"crash-loop guard should return cleanly without touching last_error; "
        f"got last_error={runner.last_error!r} — likely the config-not-found "
        f"branch fired, meaning the guard didn't short-circuit"
    )
    assert any("CRASH LOOP DETECTED" in r.message for r in caplog.records), (
        "expected log.critical('⛔ CRASH LOOP DETECTED ...') message"
    )
