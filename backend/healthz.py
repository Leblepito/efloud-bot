"""Health-aware /healthz endpoint.

Returns 200 when ALL conditions hold, OR when the bot is intentionally
suspended (breaker HALTED or crash-loop suspended):
  - last_loop_tick_ms within last 90s (bot's main loop is alive)
  - last_exchange_ping_ms within last 60s (exchange is reachable)
  - fatal_exception_state is False (no recent uncaught cycle exception)

Returns 200 with status "suspended" and a failures list when:
  - crash-loop suspension is active (too many rapid restarts)
  - breaker is in HALTED state (operator must manually reset)

Returns 503 (truly unhealthy) only for transient failures — things autoheal
can actually fix by restarting (stale loop tick, stale exchange ping, fatal exception).

HALTED is intentional state, not a transient fault — returning 503 would cause
autoheal to restart-loop the container even though restarts can't clear the HALTED
condition (weekly DD threshold still exceeded). The alerter keys off the failures
field to notify the operator.

Reads in-memory only — no disk I/O on the hot path.
Latency target: <50ms even on a slow disk.

Spec parent: docs/superpowers/specs/2026-05-07-asama-2-self-maintenance-observability-design.md §4.1
"""
from __future__ import annotations

import time
from typing import Tuple

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from engine.safety.runtime_state import RuntimeState

# 90s — bot's main loop must tick at least once per 90s. Configured generously to
# accommodate slow exchange responses and operation.check_interval_sec settings up to ~30s.
LOOP_TICK_THRESHOLD_MS = 90_000

# 60s — exchange connectivity must be confirmed at least once per 60s. Reconcile cadence
# is tied to operation.check_interval_sec; if cycles go beyond 60s without reconcile,
# the bot is in trouble.
EXCHANGE_PING_THRESHOLD_MS = 60_000


def evaluate_healthz(
    state: RuntimeState,
    breaker_halted: bool,
    now_ms: int,
) -> Tuple[int, dict]:
    """Pure function: evaluate healthz conditions, return (status_code, payload).

    Outcomes:
      - (200, {status:"ok"})        — all checks pass
      - (200, {status:"suspended", failures:["crash_loop_suspended"]})
                                    — crash-loop suspension active; autoheal must NOT restart
      - (200, {status:"suspended", failures:["breaker_halted"]})
                                    — breaker HALTED; requires operator manual_reset; autoheal must NOT restart
      - (503, {status:"unhealthy"}) — transient fault autoheal can fix by restarting

    Args:
        state: RuntimeState instance (read-only — caller takes a snapshot inside).
        breaker_halted: True if CircuitBreaker is in HALTED state.
        now_ms: current epoch ms (passed in for testability — never call time.time() here).
    """
    snap = state.snapshot()

    # Suspension branches — return 200 so autoheal does NOT restart.
    # Autoheal can't fix these; only operator action (manual_reset / wait) can.
    if state.is_in_crash_loop():
        return (200, {
            "status": "suspended",
            "checks": snap,
            "now_ms": now_ms,
            "failures": ["crash_loop_suspended"],
        })

    if breaker_halted:
        return (200, {
            "status": "suspended",
            "checks": snap,
            "now_ms": now_ms,
            "failures": ["breaker_halted"],
        })

    # Transient-fault checks — these autoheal CAN fix by restarting.
    failures: list[str] = []

    if snap["last_loop_tick_ms"] is None:
        failures.append("loop_tick_never")
    else:
        age_ms = now_ms - snap["last_loop_tick_ms"]
        if age_ms > LOOP_TICK_THRESHOLD_MS:
            failures.append(f"loop_tick_stale({age_ms}ms)")

    if snap["last_exchange_ping_ms"] is None:
        failures.append("exchange_ping_never")
    else:
        age_ms = now_ms - snap["last_exchange_ping_ms"]
        if age_ms > EXCHANGE_PING_THRESHOLD_MS:
            failures.append(f"exchange_ping_stale({age_ms}ms)")

    if snap["fatal_exception_state"]:
        failures.append("fatal_exception")

    payload = {
        "status": "ok" if not failures else "unhealthy",
        "checks": snap,
        "now_ms": now_ms,
        "failures": failures,
    }
    return (200 if not failures else 503, payload)


# ─────────────────────────────────────────────────────────────────────
# FastAPI router (Task 4 wires real RuntimeState + breaker reference)
# ─────────────────────────────────────────────────────────────────────

health_router = APIRouter()

# These globals are populated in Task 4 by backend/main.py during startup.
# Stub set here so import-order issues don't blow up before wire-up.
_runtime_state: RuntimeState | None = None
_breaker_state_getter = None  # callable returning bool: True if HALTED


def configure(runtime_state: RuntimeState, breaker_state_getter) -> None:
    """Wire dependencies. Called once during FastAPI app startup."""
    global _runtime_state, _breaker_state_getter
    _runtime_state = runtime_state
    _breaker_state_getter = breaker_state_getter


@health_router.get("/healthz")
async def healthz_endpoint() -> JSONResponse:
    """Health-aware probe. Returns 200 (ok) or 503 (unhealthy)."""
    if _runtime_state is None:
        # Endpoint hit before configure() — return 503 with explanation
        return JSONResponse(
            status_code=503,
            content={"status": "unhealthy", "failures": ["healthz_not_configured"]},
        )
    breaker_halted = bool(_breaker_state_getter()) if _breaker_state_getter else False
    now_ms = int(time.time() * 1000)
    code, payload = evaluate_healthz(_runtime_state, breaker_halted, now_ms)
    return JSONResponse(status_code=code, content=payload)
