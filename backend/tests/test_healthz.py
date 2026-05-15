"""Tests for backend/healthz.py evaluate_healthz pure function.

Key contract:
  - All checks pass                  → (200, status="ok")
  - crash_loop suspended             → (200, status="suspended", failures=["crash_loop_suspended"])
  - breaker HALTED                   → (200, status="suspended", failures=["breaker_halted"])
  - transient fault (stale tick etc) → (503, status="unhealthy")

HALTED must NOT return 503 — autoheal cannot fix it and would crash-loop the container.
Operator must call /api/breaker/reset after acknowledging the DD breach.
"""
from __future__ import annotations

import pytest

from backend.healthz import (
    EXCHANGE_PING_THRESHOLD_MS,
    LOOP_TICK_THRESHOLD_MS,
    evaluate_healthz,
)
from engine.safety.runtime_state import (
    CRASH_LOOP_THRESHOLD,
    RuntimeState,
)


# ─────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────

NOW_MS = 1_700_000_000_000  # arbitrary fixed epoch


def _fresh_state(tmp_path) -> RuntimeState:
    return RuntimeState(state_dir=str(tmp_path))


def _healthy_state(tmp_path) -> RuntimeState:
    """RuntimeState that passes all transient checks."""
    rs = _fresh_state(tmp_path)
    rs.last_loop_tick_ms = NOW_MS - 1_000       # 1s ago — fresh
    rs.last_exchange_ping_ms = NOW_MS - 1_000   # 1s ago — fresh
    return rs


# ─────────────────────────────────────────────────────────────────
# Happy-path
# ─────────────────────────────────────────────────────────────────

def test_all_checks_pass_returns_200_ok(tmp_path):
    rs = _healthy_state(tmp_path)
    code, payload = evaluate_healthz(rs, breaker_halted=False, now_ms=NOW_MS)
    assert code == 200
    assert payload["status"] == "ok"
    assert payload["failures"] == []


# ─────────────────────────────────────────────────────────────────
# Breaker HALTED — must return 200, NOT 503
# ─────────────────────────────────────────────────────────────────

def test_breaker_halted_returns_200_suspended(tmp_path):
    """HALTED bot must not be autoheal-restarted — return 200 with suspended status."""
    rs = _healthy_state(tmp_path)
    code, payload = evaluate_healthz(rs, breaker_halted=True, now_ms=NOW_MS)
    assert code == 200, "HALTED must NOT return 503 — autoheal would restart-loop"
    assert payload["status"] == "suspended"
    assert "breaker_halted" in payload["failures"]


def test_breaker_halted_with_stale_tick_still_200(tmp_path):
    """Even if loop tick is also stale, HALTED takes precedence → 200 suspended."""
    rs = _fresh_state(tmp_path)
    # last_loop_tick_ms = None (never ticked) + breaker HALTED
    code, payload = evaluate_healthz(rs, breaker_halted=True, now_ms=NOW_MS)
    assert code == 200
    assert payload["status"] == "suspended"
    assert "breaker_halted" in payload["failures"]
    # stale tick should NOT appear in failures (suspension branch short-circuits)
    assert not any("loop_tick" in f for f in payload["failures"])


def test_breaker_not_halted_stale_tick_returns_503(tmp_path):
    """Without HALTED, stale loop tick is a transient fault → 503 for autoheal."""
    rs = _fresh_state(tmp_path)
    # last_loop_tick_ms = None → loop_tick_never failure
    code, payload = evaluate_healthz(rs, breaker_halted=False, now_ms=NOW_MS)
    assert code == 503
    assert payload["status"] == "unhealthy"
    assert any("loop_tick" in f for f in payload["failures"])


# ─────────────────────────────────────────────────────────────────
# Crash-loop suspension
# ─────────────────────────────────────────────────────────────────

def test_crash_loop_suspended_returns_200(tmp_path):
    rs = _healthy_state(tmp_path)
    # is_in_crash_loop() uses real time.time() internally, so last_crash_ms must be
    # a real recent timestamp — not the frozen NOW_MS constant.
    import time
    rs.crash_count = CRASH_LOOP_THRESHOLD
    rs.last_crash_ms = int(time.time() * 1000) - 60_000  # 1 min ago — within 30 min window
    code, payload = evaluate_healthz(rs, breaker_halted=False, now_ms=NOW_MS)
    assert code == 200
    assert payload["status"] == "suspended"
    assert "crash_loop_suspended" in payload["failures"]


def test_crash_loop_suspended_takes_precedence_over_halted(tmp_path):
    """crash_loop check runs first; if both active, suspended with crash_loop label."""
    import time
    rs = _healthy_state(tmp_path)
    rs.crash_count = CRASH_LOOP_THRESHOLD
    rs.last_crash_ms = int(time.time() * 1000) - 60_000
    code, payload = evaluate_healthz(rs, breaker_halted=True, now_ms=NOW_MS)
    assert code == 200
    assert payload["status"] == "suspended"
    # crash_loop_suspended is the failure label (first suspension branch wins)
    assert "crash_loop_suspended" in payload["failures"]


# ─────────────────────────────────────────────────────────────────
# Transient fault cases — these should return 503
# ─────────────────────────────────────────────────────────────────

def test_stale_loop_tick_returns_503(tmp_path):
    rs = _healthy_state(tmp_path)
    rs.last_loop_tick_ms = NOW_MS - LOOP_TICK_THRESHOLD_MS - 1
    code, payload = evaluate_healthz(rs, breaker_halted=False, now_ms=NOW_MS)
    assert code == 503
    assert any("loop_tick_stale" in f for f in payload["failures"])


def test_stale_exchange_ping_returns_503(tmp_path):
    rs = _healthy_state(tmp_path)
    rs.last_exchange_ping_ms = NOW_MS - EXCHANGE_PING_THRESHOLD_MS - 1
    code, payload = evaluate_healthz(rs, breaker_halted=False, now_ms=NOW_MS)
    assert code == 503
    assert any("exchange_ping_stale" in f for f in payload["failures"])


def test_fatal_exception_returns_503(tmp_path):
    rs = _healthy_state(tmp_path)
    rs.fatal_exception_state = True
    code, payload = evaluate_healthz(rs, breaker_halted=False, now_ms=NOW_MS)
    assert code == 503
    assert "fatal_exception" in payload["failures"]


def test_multiple_transient_failures_all_reported(tmp_path):
    rs = _fresh_state(tmp_path)
    rs.fatal_exception_state = True
    # Both tick and exchange ping = None → two failures
    code, payload = evaluate_healthz(rs, breaker_halted=False, now_ms=NOW_MS)
    assert code == 503
    failure_names = payload["failures"]
    assert "loop_tick_never" in failure_names
    assert "exchange_ping_never" in failure_names
    assert "fatal_exception" in failure_names


# ─────────────────────────────────────────────────────────────────
# Payload structure sanity
# ─────────────────────────────────────────────────────────────────

def test_payload_always_has_required_keys(tmp_path):
    rs = _healthy_state(tmp_path)
    for halted in (True, False):
        _, payload = evaluate_healthz(rs, breaker_halted=halted, now_ms=NOW_MS)
        assert "status" in payload
        assert "checks" in payload
        assert "now_ms" in payload
        assert "failures" in payload
        assert payload["now_ms"] == NOW_MS
