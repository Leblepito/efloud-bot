"""evaluate_healthz pure-function tests — deterministic given inputs.

Decision matrix: returns 200 only when all conditions hold; 503 otherwise
with `failures` array explaining why.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from backend.healthz import (
    LOOP_TICK_THRESHOLD_MS,
    EXCHANGE_PING_THRESHOLD_MS,
    evaluate_healthz,
)
from engine.safety.runtime_state import RuntimeState


@pytest.fixture
def state(tmp_path: Path) -> RuntimeState:
    return RuntimeState(state_dir=str(tmp_path))


def _make_clean(state: RuntimeState, now_ms: int) -> None:
    """Helper: simulate a healthy bot — recent tick + ping, no fatal, breaker not halted."""
    state.last_loop_tick_ms = now_ms - 5_000   # 5 s ago — well within 90s
    state.last_exchange_ping_ms = now_ms - 5_000  # 5 s ago — well within 60s


def test_returns_200_when_all_clean(state: RuntimeState):
    now_ms = 10_000_000
    _make_clean(state, now_ms)
    code, payload = evaluate_healthz(state, breaker_halted=False, now_ms=now_ms)
    assert code == 200
    assert payload["status"] == "ok"
    assert payload["failures"] == []


def test_returns_503_when_loop_tick_stale(state: RuntimeState):
    now_ms = 10_000_000
    _make_clean(state, now_ms)
    state.last_loop_tick_ms = now_ms - (LOOP_TICK_THRESHOLD_MS + 1_000)  # 91s ago
    code, payload = evaluate_healthz(state, breaker_halted=False, now_ms=now_ms)
    assert code == 503
    assert any("loop_tick_stale" in f for f in payload["failures"])


def test_returns_503_when_loop_tick_never_set(state: RuntimeState):
    """A bot that just started has no tick yet — must report unhealthy until first tick."""
    now_ms = 10_000_000
    state.last_exchange_ping_ms = now_ms - 5_000  # exchange OK, but no tick
    code, payload = evaluate_healthz(state, breaker_halted=False, now_ms=now_ms)
    assert code == 503
    assert "loop_tick_never" in payload["failures"]


def test_returns_503_when_exchange_ping_stale(state: RuntimeState):
    now_ms = 10_000_000
    _make_clean(state, now_ms)
    state.last_exchange_ping_ms = now_ms - (EXCHANGE_PING_THRESHOLD_MS + 1_000)  # 61s ago
    code, payload = evaluate_healthz(state, breaker_halted=False, now_ms=now_ms)
    assert code == 503
    assert any("exchange_ping_stale" in f for f in payload["failures"])


def test_returns_503_when_exchange_ping_never_set(state: RuntimeState):
    """Symmetry with test_returns_503_when_loop_tick_never_set: bot has ticked
    but never confirmed exchange connectivity (e.g. exchange API unreachable
    since startup) — must report unhealthy."""
    now_ms = 10_000_000
    state.last_loop_tick_ms = now_ms - 5_000  # tick OK
    # last_exchange_ping_ms remains None
    code, payload = evaluate_healthz(state, breaker_halted=False, now_ms=now_ms)
    assert code == 503
    assert "exchange_ping_never" in payload["failures"]


def test_returns_503_when_fatal_exception_set(state: RuntimeState):
    now_ms = 10_000_000
    _make_clean(state, now_ms)
    state.fatal_exception_state = True
    state.fatal_exception_set_at_ms = now_ms - 1_000
    code, payload = evaluate_healthz(state, breaker_halted=False, now_ms=now_ms)
    assert code == 503
    assert "fatal_exception" in payload["failures"]


def test_returns_200_suspended_when_breaker_halted(state: RuntimeState):
    """HALTED must return 200 suspended — autoheal cannot fix it, restarting would
    crash-loop (weekly DD still exceeded after restart). Operator must manual_reset."""
    now_ms = 10_000_000
    _make_clean(state, now_ms)
    code, payload = evaluate_healthz(state, breaker_halted=True, now_ms=now_ms)
    assert code == 200
    assert payload["status"] == "suspended"
    assert "breaker_halted" in payload["failures"]
