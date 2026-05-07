"""End-to-end: full lifecycle of healthz signal flow.

Simulates: bot starts → ticks → exception → 5min clean ticks → recovers.
Verifies healthz status transitions match expectations at each step.
No real exchange / DB / network. Uses RuntimeState + evaluate_healthz directly.
"""
from __future__ import annotations

import time
from pathlib import Path

from backend.healthz import evaluate_healthz
from engine.safety.runtime_state import RuntimeState


def test_full_lifecycle_loop_tick_to_healthz(tmp_path: Path):
    """Walk through every healthz transition: never_ticked → ticking_clean
    → fatal_set → fatal_persists_short → fatal_clears_after_5min → clean_again.
    """
    rs = RuntimeState(state_dir=str(tmp_path))

    # T+0: bot just started — no ticks yet
    now = int(time.time() * 1000)
    code, payload = evaluate_healthz(rs, breaker_halted=False, now_ms=now)
    assert code == 503
    assert "loop_tick_never" in payload["failures"]

    # T+1s: first tick + ping land
    rs.update_loop_tick()
    rs.update_exchange_ping()
    now += 1_000
    code, payload = evaluate_healthz(rs, breaker_halted=False, now_ms=now)
    assert code == 200, f"expected 200 after first tick+ping, got {code}: {payload}"

    # T+30s: a cycle exception fires; fatal flag set
    rs.set_fatal_exception()
    now += 30_000
    code, payload = evaluate_healthz(rs, breaker_halted=False, now_ms=now)
    assert code == 503
    assert "fatal_exception" in payload["failures"]

    # T+1min: ticks continuing but flag still active (only 1 min since fatal)
    # Manually rewind set_at_ms so we control the elapsed time:
    rs.fatal_exception_set_at_ms = now - 60_000  # 1 min ago
    rs.update_loop_tick()    # this checks auto-clear (1 min < 5 min → no clear)
    rs.update_exchange_ping()
    code, payload = evaluate_healthz(rs, breaker_halted=False, now_ms=now)
    assert code == 503
    assert "fatal_exception" in payload["failures"]

    # T+6min from fatal-set: now auto-clear should fire on next tick
    rs.fatal_exception_set_at_ms = now - 6 * 60 * 1000  # 6 min ago
    rs.update_loop_tick()    # this should auto-clear
    rs.update_exchange_ping()
    snap = rs.snapshot()
    assert snap["fatal_exception_state"] is False, "fatal flag should auto-clear"
    code, payload = evaluate_healthz(rs, breaker_halted=False, now_ms=now)
    assert code == 200, f"expected recovery to 200, got {code}: {payload}"

    # T+10min: still ticking, breaker halts (operator manual halt or weekly DD)
    rs.update_loop_tick()
    rs.update_exchange_ping()
    code, payload = evaluate_healthz(rs, breaker_halted=True, now_ms=now)
    assert code == 503
    assert "breaker_halted" in payload["failures"]
