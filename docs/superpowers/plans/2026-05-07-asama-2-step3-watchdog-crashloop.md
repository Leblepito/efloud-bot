# Aşama 2 — Step 3: Docker watchdog + crash-loop suppression Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Wire the `/healthz` endpoint (Step 2) to actual auto-restart behavior via a `willfarrell/autoheal` sidecar, and prevent crash-loops by short-circuiting the trading loop once `crash_count` crosses the threshold within a 30-minute window.

**Architecture:** Stock Docker compose's `restart: unless-stopped` only reacts to container EXIT, not to `(unhealthy)` health status. We add an `autoheal` sidecar (~10 MB image) that polls Docker's API every 60s, finds containers with the `autoheal=true` label in `(unhealthy)` state, and restarts them. Crash-loop suppression lives in the bot itself: when `RuntimeState.is_in_crash_loop()` is true (≥3 crashes in last 30 min), `bot_runner` skips the trading loop and `evaluate_healthz` returns 200 with `status: "suspended"` and `failures: ["crash_loop_suspended"]` — autoheal sees healthy, doesn't restart the loop, and Step 4's alerter fires CRITICAL on the failures field. A 60-minute clean-uptime window auto-clears `crash_count` (mirrors the existing 5-minute auto-clear for `fatal_exception_state`).

**Tech Stack:** Docker compose v2, `willfarrell/autoheal:latest`, Python 3.12, pytest. No new Python deps.

**Spec parent:** `docs/superpowers/specs/2026-05-07-asama-2-self-maintenance-observability-design.md` (§4.1 watchdog, §11 Step 3, §6 health.crash_loop event)

**Estimated effort:** 2-3 days for one engineer.

---

## Codebase reality check

### Step 2 deliverables (already shipped to master, commit `6f47529`)
- `engine/safety/runtime_state.py:RuntimeState` — has `crash_count`, `last_crash_ms`, `fatal_exception_state`, `update_loop_tick()`, `set_fatal_exception()`, `increment_crash()`, `reset_crash_count()`, `snapshot()`. **Step 3 adds `is_in_crash_loop()` + 60-min clean-uptime auto-clear inside `update_loop_tick`.**
- `backend/healthz.py:evaluate_healthz` — pure function, returns `(200, payload)` or `(503, payload)`. **Step 3 adds the `crash_loop_suspended` 200-with-failures branch.**
- `backend/bot_runner.py:_run_loop` — async main loop, calls `update_loop_tick`/`update_exchange_ping`/`set_fatal_exception`. **Step 3 adds a startup guard: skip `_run_loop` entirely when crash-loop is active.**

### Spec deviations to call out

The spec §3 architecture diagram says *"on unhealthy: docker auto-restart"* but stock Docker compose does NOT support restart-on-unhealthy (only Docker swarm or external watchdogs do). This plan fills that gap with `willfarrell/autoheal` — a 10 MB sidecar that polls the Docker socket for unhealthy labeled containers and restarts them. Documented as a spec correction in the runbook (§ Runbook below).

The spec §4.1 "Returns 503 if any [healthz check] fails" wording is strict, but **crash-loop suspension intentionally returns 200** with `status: "suspended"` and a `crash_loop_suspended` failure tag. Reason: if `/healthz` returned 503 in suspension mode, autoheal would loop-restart the container and never let suspension stick. The 200 response keeps autoheal quiet; the `failures` field is what Step 4's alerter and Step 5's daily-report key off for the CRITICAL escalation.

**Caddy interaction (intentional side effect of returning 200 in suspension):** `docker-compose.prod.yml` has `caddy: depends_on: efloud-bot: condition: service_healthy`. Docker compose's healthcheck stanza on `efloud-bot` polls the same `/healthz` endpoint, so during suspension the bot's container reports `(healthy)` (since /healthz returns 200). Caddy's `depends_on` constraint stays satisfied → the dashboard at `https://bot.ualgotrade.com` stays reachable. This is by design — the operator needs to be able to see the suspension status (status:"suspended") via the dashboard before deciding how to recover. If we returned 503 here, Caddy would mark the service unavailable AND the operator would lose access to the diagnostic UI exactly when they need it most.

**UX gap during suspension — `/api/bot/start` audit:** when the operator clicks "Start" in the dashboard while the bot is in suspension, `runner.start()` returns early at the new guard (Task 3.4) without setting `last_error`. The current `/api/bot/start` endpoint (in `backend/api.py`) likely returns `{"status": "started"}` or similar success response — meaning the user gets a misleading green confirmation while nothing actually started. **Step 3 acceptance does NOT auto-fix this UX gap** (would require modifying the API contract); it is documented in the runbook (Task 5) under "what success looks like vs. silent suspension". A follow-up plan (or Step 4 alerter visibility) is the proper place to add explicit "bot is suspended, cannot start" feedback to the user — out of scope here.

### Existing docker-compose.prod.yml shape (verified in production)

```yaml
services:
  efloud-bot:
    image: efloud-bot:latest
    restart: unless-stopped
    healthcheck:
      test: ["CMD", "python", "-c", "..."]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 40s
  caddy:
    depends_on:
      efloud-bot:
        condition: service_healthy
```

`start_period: 40s` is too short for the bot — Step 2 deployed and saw `(starting)` for ~30s before flipping to `(healthy)` post-loop-tick. With autoheal added in this plan, false `(unhealthy)` during slow startups would loop-restart. Step 3 raises `start_period` to `120s` to comfortably accommodate first-cycle initialization (config load + DB pool + first orchestrator scan).

---

## File structure (what gets created vs modified)

**Create:**
- `tests/test_crash_loop.py` — `is_in_crash_loop()` + `evaluate_healthz` suspended branch + `_run_loop` startup guard tests
- `docs/runbooks/crash-loop-recovery.md` — manual recovery playbook (when auto-clear isn't enough)

**Modify:**
- `engine/safety/runtime_state.py` — add `is_in_crash_loop()` method + 60-min clean-uptime auto-clear inside `update_loop_tick()`
- `backend/healthz.py` — add `crash_loop_suspended` branch in `evaluate_healthz()`
- `backend/bot_runner.py:start()` — skip `_run_loop` task creation when `is_in_crash_loop()` is True; log CRITICAL once
- `docker-compose.prod.yml` — add `autoheal` sidecar service + `autoheal=true` label on `efloud-bot` + raise `start_period` to 120s

**Delete:** none.

---

## Pre-flight

### Task 0: Worktree + branch setup, baseline verification

**Files:** none modified, only environment setup.

- [ ] **Step 0.1: Create dedicated worktree from master**

```powershell
cd C:\Users\utkuc\Downloads\efloud-bot
git worktree add ../efloud-bot-asama2-step3 -b feature/asama-2-step-3-watchdog master
cd ../efloud-bot-asama2-step3
```

Expected: new worktree on branch `feature/asama-2-step-3-watchdog`, based on master HEAD `6f47529` (post Aşama 2 Step 2 merge).

- [ ] **Step 0.2: Verify base tests pass**

```powershell
python -m pytest tests/ -q --no-header 2>&1 | Select-Object -Last 5
```

Expected: 76 pass + 6 skip = **82 collected** (matches Step 2 final count). If anything fails, STOP.

- [ ] **Step 0.3: Capture baseline test count**

Record `BASELINE_PASSED=76`, `BASELINE_SKIPPED=6`. Final test count after Step 3 must be **exactly** `76 + 7 = 83 passed` (skip count unchanged at 6, total collected = 89).

New tests added by this plan (= 7):
- Task 1 (`tests/test_crash_loop.py`, RuntimeState section): 3 tests (`test_is_in_crash_loop_returns_true_when_threshold_met_in_window`, `test_is_in_crash_loop_returns_false_when_outside_window`, `test_update_loop_tick_clears_crash_count_after_60min_clean_uptime`)
- Task 2 (`tests/test_crash_loop.py`, healthz section): 2 tests (`test_evaluate_healthz_returns_200_suspended_when_crash_loop_active`, `test_evaluate_healthz_normal_503_path_unchanged_when_not_in_crash_loop`)
- Task 3 (`tests/test_crash_loop.py`, bot_runner guard section): 1 test (`test_bot_runner_start_skips_trading_loop_when_crash_loop_active`)
- Task 6 (E2E): 1 test (`test_e2e_crash_loop_lifecycle`)

Total: 3+2+1+1 = **7**.

Running totals at each task boundary:
- After Task 1: 76+3 = 79 pass
- After Task 2: 76+5 = 81 pass
- After Task 3: 76+6 = 82 pass
- After Task 4: 76+6 = 82 pass (no tests; Docker config only)
- After Task 5: 76+6 = 82 pass (no tests; markdown only)
- After Task 6: 76+7 = **83 pass** ← FINAL

---

## Foundation: crash-loop detection

### Task 1: RuntimeState.is_in_crash_loop() + 60-min auto-clear

**Files:**
- Modify: `engine/safety/runtime_state.py` (add 1 constant + 1 method, extend 1 method)
- Test: `tests/test_crash_loop.py` (3 tests, file is created here; later tasks append to it)

- [ ] **Step 1.1: Write the 3 tests first**

Create `tests/test_crash_loop.py`:

```python
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
```

Note: 3 tests, but the file imports symbols (`CRASH_LOOP_THRESHOLD`, `CRASH_LOOP_WINDOW_MS`, `CRASH_AUTO_CLEAR_AFTER_MS`) that don't exist yet — collection will fail at import, marking all 3 as ERROR.

- [ ] **Step 1.2: Run tests, expect FAIL**

```powershell
python -m pytest tests/test_crash_loop.py -v 2>&1
```

Expected: ImportError for `CRASH_LOOP_THRESHOLD` / `CRASH_LOOP_WINDOW_MS` / `CRASH_AUTO_CLEAR_AFTER_MS` / `is_in_crash_loop`. All 3 fail at collection.

- [ ] **Step 1.3: Implement constants + is_in_crash_loop + auto-clear branch**

Open `engine/safety/runtime_state.py`. Below the existing `FATAL_CLEAR_AFTER_MS = 5 * 60 * 1000` line, add:

```python
# Crash-loop detection thresholds
CRASH_LOOP_THRESHOLD = 3              # 3+ crashes in window → suspension
CRASH_LOOP_WINDOW_MS = 30 * 60 * 1000  # 30-minute sliding window
CRASH_AUTO_CLEAR_AFTER_MS = 60 * 60 * 1000  # 60 min clean uptime → reset crash_count
```

Add the `is_in_crash_loop` method to the `RuntimeState` class (place it AFTER `snapshot()` so it's the last method on the class):

```python
    def is_in_crash_loop(self) -> bool:
        """Return True if the bot is in a crash-loop (≥3 crashes in last 30 min).

        Reads from in-memory snapshot — no disk I/O. Used by:
        - bot_runner.start() to skip trading loop creation (suspension mode)
        - evaluate_healthz() to flip into the 200 + 'suspended' status branch
        """
        snap = self.snapshot()
        if snap["crash_count"] < CRASH_LOOP_THRESHOLD:
            return False
        if snap["last_crash_ms"] is None:
            return False
        now_ms = int(time.time() * 1000)
        return (now_ms - snap["last_crash_ms"]) < CRASH_LOOP_WINDOW_MS
```

Modify the existing `update_loop_tick()` method to add the 60-min clean-uptime auto-clear ALONGSIDE the existing 5-min fatal auto-clear. Replace the body of `update_loop_tick`:

```python
    def update_loop_tick(self) -> None:
        """Called from main loop after each successful cycle.

        Side effects (both checked atomically under the lock):
        - Auto-clears fatal_exception_state if 5+ min since the flag was set.
        - Auto-clears crash_count if 60+ min since the last crash.
        """
        now_ms = int(time.time() * 1000)
        with self._lock:
            self.last_loop_tick_ms = now_ms
            persist_dirty = False

            if self.fatal_exception_state and self.fatal_exception_set_at_ms is not None:
                if now_ms - self.fatal_exception_set_at_ms >= FATAL_CLEAR_AFTER_MS:
                    self.fatal_exception_state = False
                    self.fatal_exception_set_at_ms = None
                    persist_dirty = True

            if self.crash_count > 0 and self.last_crash_ms is not None:
                if now_ms - self.last_crash_ms >= CRASH_AUTO_CLEAR_AFTER_MS:
                    self.crash_count = 0
                    self.last_crash_ms = None
                    persist_dirty = True

            if persist_dirty:
                self._save()
```

Single `persist_dirty` flag avoids two separate `_save()` calls if both branches fire simultaneously (rare but possible).

- [ ] **Step 1.4: Run tests, expect PASS**

```powershell
python -m pytest tests/test_crash_loop.py -v 2>&1 | Select-Object -Last 15
```

Expected: 3 tests pass.

- [ ] **Step 1.5: Run full suite for regression**

```powershell
python -m pytest tests/ -q 2>&1 | Select-Object -Last 5
```

Expected: 79 pass + 6 skip = 85 collected (76 baseline + 3 new = 79; the existing `test_runtime_state.py` Step 2 tests still pass because the new auto-clear logic doesn't fire when `last_crash_ms` is None, which is the baseline case).

- [ ] **Step 1.6: Commit**

```powershell
git add engine/safety/runtime_state.py tests/test_crash_loop.py
git commit -m "feat(state): is_in_crash_loop() + 60-min crash_count auto-clear"
```

---

### Task 2: evaluate_healthz suspended branch

**Files:**
- Modify: `backend/healthz.py` (add suspended branch in `evaluate_healthz`)
- Test: `tests/test_crash_loop.py` (append 2 tests)

- [ ] **Step 2.1: Append 2 tests to tests/test_crash_loop.py**

At the END of `tests/test_crash_loop.py` (which Task 1 created), append:

```python
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
```

- [ ] **Step 2.2: Run tests, expect FAIL**

```powershell
python -m pytest tests/test_crash_loop.py -v 2>&1 | Select-Object -Last 15
```

Expected: the 2 new tests fail (`test_evaluate_healthz_returns_200_suspended_when_crash_loop_active` will fail because the existing `evaluate_healthz` doesn't know about the suspension branch — it would return 200 only when all checks pass, but the suspension check doesn't exist yet, so the path returns 200 with `status: "ok"` and `failures: []` — the assertion on `status == "suspended"` fails).

The other 3 Task-1 tests still pass.

- [ ] **Step 2.3: Add the suspended branch to evaluate_healthz**

Open `backend/healthz.py`. The current `evaluate_healthz` body (lines ~57-95) has 4 condition checks. Wrap them with a new "suspension takes precedence" branch at the top:

```python
def evaluate_healthz(
    state: RuntimeState,
    breaker_halted: bool,
    now_ms: int,
) -> Tuple[int, dict]:
    """Pure function: evaluate healthz conditions, return (status_code, payload).

    Outcomes:
      - (200, {status:"ok"})        — all checks pass
      - (200, {status:"suspended", failures:["crash_loop_suspended"]})
                                    — crash-loop suspension active (NOT 503;
                                      see plan §"Spec deviations" for why)
      - (503, {status:"unhealthy"}) — at least one normal check failed

    Args:
        state: RuntimeState instance.
        breaker_halted: True if CircuitBreaker is in HALTED state.
        now_ms: current epoch ms (passed in for testability).
    """
    snap = state.snapshot()

    # Suspension branch — takes precedence over normal checks.
    # See plan §"Spec deviations" — returning 200 here keeps the autoheal sidecar
    # from restart-looping us; alerter (Step 4) keys off the 'failures' field.
    if state.is_in_crash_loop():
        return (200, {
            "status": "suspended",
            "checks": snap,
            "now_ms": now_ms,
            "failures": ["crash_loop_suspended"],
        })

    # Normal 4-condition health check (Step 2 contract).
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

    if breaker_halted:
        failures.append("breaker_halted")

    payload = {
        "status": "ok" if not failures else "unhealthy",
        "checks": snap,
        "now_ms": now_ms,
        "failures": failures,
    }
    return (200 if not failures else 503, payload)
```

The change is purely additive: a new precedence-taking branch at the top, normal logic preserved below. All Step 2's test_healthz_logic tests still pass because none of them set up a crash-loop state.

- [ ] **Step 2.4: Run tests, expect PASS**

```powershell
python -m pytest tests/test_crash_loop.py tests/test_healthz_logic.py -v 2>&1 | Select-Object -Last 25
```

Expected: 5 crash_loop tests + 7 healthz_logic tests = 12 PASS. The Step 2 endpoint tests in `tests/test_healthz_endpoint.py` also still pass (same regression check).

- [ ] **Step 2.5: Run full suite**

```powershell
python -m pytest tests/ -q 2>&1 | Select-Object -Last 5
```

Expected: 81 pass + 6 skip (76 baseline + 5 from Tasks 1-2 = 81).

- [ ] **Step 2.6: Commit**

```powershell
git add backend/healthz.py tests/test_crash_loop.py
git commit -m "feat(healthz): crash-loop suspension branch returns 200+suspended (autoheal-safe)"
```

---

### Task 3: bot_runner skip trading loop when crash-loop active

**Files:**
- Modify: `backend/bot_runner.py:start()` method
- Test: `tests/test_crash_loop.py` (append 1 test)

The intent: when `is_in_crash_loop()` is True at startup, do NOT create the `_run_loop` task. The bot stays alive (FastAPI app + WebSocket + /healthz endpoint all keep serving), but no trades happen. Healthz returns 200+suspended (Task 2), keeping autoheal quiet. Operator sees the suspension via Step 4's alerter / Step 5's daily-report and intervenes manually.

- [ ] **Step 3.0: Attribute name reality check**

Before writing the test, verify the attribute names the test depends on actually exist on `BotRunner`:

```powershell
Select-String -Path backend\bot_runner.py -Pattern "self\.(runtime_state|task|cfg|last_error)\s*=|def __init__|class BotRunner" | Select-Object -First 12
```

Expected output (verified at master HEAD `6f47529`):
- `class BotRunner:` (line 33)
- `def __init__(self) -> None:` (line 34, no args)
- `self.task: Optional[asyncio.Task] = None` (line 35)
- `self.cfg: dict = {}` (line 37) — empty dict, set BEFORE runtime_state init at line 54
- `self.last_error: Optional[str] = None` (line 47)
- `self.runtime_state = RuntimeState(state_dir=state_dir)` (line 54)

If the actual lines differ, surface the divergence before continuing — the Task 3 test depends on these names.

- [ ] **Step 3.1: Locate the `start()` method**

```powershell
Select-String -Path backend\bot_runner.py -Pattern "async def start\(|self.task =|create_task" | Select-Object -First 5
```

The current `start()` method (line 60+) starts with an idempotency check (`if self.running and not self.stopped:`), then loads config (line 70-79), then constructs the orchestrator + creates the `_run_loop` asyncio task at line 157. We add the crash-loop guard at the very top — BEFORE the existing idempotency check, BEFORE config load.

- [ ] **Step 3.2: Append the guard test to tests/test_crash_loop.py**

```python
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

    with caplog.at_level(logging.CRITICAL, logger="efloud.bot_runner"):
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
```

- [ ] **Step 3.3: Run test, expect FAIL**

```powershell
python -m pytest tests/test_crash_loop.py::test_bot_runner_start_skips_trading_loop_when_crash_loop_active -v 2>&1 | Select-Object -Last 15
```

Expected: assertion fails (current `start()` doesn't have the guard, so `task` is not None).

- [ ] **Step 3.4: Add the guard to bot_runner.start()**

Open `backend/bot_runner.py`. Find the `async def start(self)` method body. AT THE TOP of the method body (before any other logic — orchestrator construction, task creation, etc.), insert:

```python
    async def start(self) -> None:
        # Aşama 2 Step 3: crash-loop suspension guard.
        # If recent crashes have crossed the threshold, do NOT spin up the
        # trading task. The FastAPI app stays alive so /healthz can return
        # status:"suspended", which Step 4's alerter and Step 5's daily-report
        # turn into a CRITICAL escalation. Operator intervenes manually
        # (see docs/runbooks/crash-loop-recovery.md).
        if self.runtime_state.is_in_crash_loop():
            log.critical(
                "⛔ CRASH LOOP DETECTED: %s crashes in last %s min — trading loop SUSPENDED. "
                "See docs/runbooks/crash-loop-recovery.md to recover.",
                self.runtime_state.snapshot()["crash_count"],
                30,
            )
            return  # Bot stays alive (FastAPI + healthz); no trading task created.

        # ... existing start() body follows unchanged ...
```

If the existing `start()` has guard checks (e.g. "already running"), place this NEW guard BEFORE them (the crash-loop check should be the very first thing).

- [ ] **Step 3.5: Run test, expect PASS**

```powershell
python -m pytest tests/test_crash_loop.py::test_bot_runner_start_skips_trading_loop_when_crash_loop_active -v 2>&1 | Select-Object -Last 5
```

Expected: 1 test passes.

- [ ] **Step 3.6: Run full suite**

```powershell
python -m pytest tests/ -q 2>&1 | Select-Object -Last 5
```

Expected: 82 pass + 6 skip (76 baseline + 6 from Tasks 1-3 = 82).

- [ ] **Step 3.7: Commit**

```powershell
git add backend/bot_runner.py tests/test_crash_loop.py
git commit -m "feat(bot_runner): skip trading loop creation during crash-loop suspension"
```

---

## Watchdog wiring

### Task 4: docker-compose autoheal sidecar + healthcheck tuning

**Files:**
- Modify: `docker-compose.prod.yml`

This task adds the `willfarrell/autoheal` sidecar so Docker actually restarts unhealthy containers. No tests (Docker config). Verification is the smoke test in Step 7.2.

- [ ] **Step 4.1: Read current docker-compose.prod.yml**

```powershell
Get-Content docker-compose.prod.yml
```

Confirm the file matches the shape expected (Caddy + efloud-bot, with `restart: unless-stopped` and `healthcheck:` stanza). If the file has diverged, STOP and surface to owner.

- [ ] **Step 4.2: Add `autoheal=true` label + raise start_period on efloud-bot service**

Locate the `efloud-bot:` service block. Add a `labels:` key (alongside `image:`, `container_name:`, etc.) and update the existing `start_period` from `40s` to `120s`:

```yaml
  efloud-bot:
    build:
      context: .
      dockerfile: Dockerfile
    image: efloud-bot:latest
    container_name: efloud-bot
    restart: unless-stopped
    labels:
      - autoheal=true
    env_file:
      - .env.production
    expose:
      - "8080"
    volumes:
      - efloud_state:/app/state
      - efloud_state_1k:/app/state_1k
      - efloud_logs:/app/logs
      - efloud_reports:/app/reports
    healthcheck:
      test: ["CMD", "python", "-c", "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://localhost:8080/healthz', timeout=5).getcode()==200 else 1)"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 120s
    logging:
      driver: json-file
      options:
        max-size: "10m"
        max-file: "5"
```

The `start_period: 120s` change matters: with autoheal added, an `(unhealthy)` status during slow startup (config load + DB pool + first cycle) would trigger a restart loop. 120s comfortably covers the bot's first-cycle initialization observed in production.

- [ ] **Step 4.3: Add the autoheal sidecar service**

After the `caddy:` service block (or in any consistent position), add:

```yaml
  autoheal:
    image: willfarrell/autoheal:1.2.0      # PINNED (do NOT use :latest in production)
    container_name: efloud-autoheal
    restart: always
    environment:
      - AUTOHEAL_INTERVAL=60        # check unhealthy containers every 60s
      - AUTOHEAL_START_PERIOD=120   # match efloud-bot start_period; ignore unhealthy during this window
      - AUTOHEAL_CONTAINER_LABEL=autoheal  # only restart containers tagged autoheal=true
    volumes:
      - /var/run/docker.sock:/var/run/docker.sock
    logging:
      driver: json-file
      options:
        max-size: "5m"
        max-file: "2"
```

**Why pin `1.2.0` instead of `:latest`:** the autoheal container has root-equivalent host access via `/var/run/docker.sock`. A routine `docker compose pull` with `:latest` could swap the image at any time — pinning to `1.2.0` (the current stable tag at time of writing) means image changes are deliberate, reviewed events. To upgrade later, bump the tag and redeploy.

**Security note:** mounting `/var/run/docker.sock` gives the autoheal container full Docker daemon access (root-equivalent on the host). `willfarrell/autoheal` is a well-known image (~1.5k GitHub stars) that only does `docker restart` on labeled containers. Trade-off accepted for single-operator deployments. Document this in the runbook (Task 5).

- [ ] **Step 4.4: Validate compose file**

```powershell
docker compose -f docker-compose.prod.yml config 2>&1 | Select-Object -First 30
```

Expected: the parsed config prints without errors. If `docker` isn't installed locally, skip this step and rely on the Hetzner-side validation in Step 7.2.

- [ ] **Step 4.5: Commit**

```powershell
git add docker-compose.prod.yml
git commit -m "feat(deploy): autoheal sidecar restarts unhealthy efloud-bot; start_period 40s→120s"
```

---

### Task 5: Manual recovery runbook

**Files:**
- Create: `docs/runbooks/crash-loop-recovery.md`

When auto-clear (60-min clean uptime) doesn't fire (bot keeps re-crashing), an operator needs a documented procedure to recover.

- [ ] **Step 5.1: Create the runbook**

Create `docs/runbooks/crash-loop-recovery.md`:

```markdown
# Crash-Loop Recovery Runbook

## What happened?

The bot's `RuntimeState.is_in_crash_loop()` returned True (≥3 crashes in last 30 min).
As a result:
- `BotRunner.start()` skipped creating the trading task. **The bot is alive but not trading.**
- `/healthz` returns `200` with `status: "suspended"` and `failures: ["crash_loop_suspended"]`.
- The autoheal sidecar sees `(healthy)` and does NOT restart the container.
- (Step 4 alerter, when shipped) fires a CRITICAL Telegram alert.

## ⚠️ Auto-recovery does NOT work during suspension

**Read this carefully:** `RuntimeState.update_loop_tick()` is the only auto-clear path for
`crash_count`, and it is called ONLY from the trading loop. When suspension trips, the
trading loop is the FIRST thing that gets shut off (Task 3 guard). So `update_loop_tick()`
never fires during suspension, which means `crash_count` never auto-clears, which means
suspension is permanent until you manually recover.

The 60-min auto-clear only helps if the bot was crashing-then-recovering on its own and
never crossed the threshold into full suspension (e.g., 2 crashes in 30 min — under the
3-crash threshold — followed by 60 min of clean uptime would trigger auto-clear). If you
are reading this runbook, the bot is in suspension and you must use manual recovery below.

## What success vs. silent suspension looks like

The dashboard's "Start" button (POST `/api/bot/start`) returns success even during suspension —
because the guard short-circuits cleanly without setting `last_error`. **A successful click
that doesn't actually resume trading means suspension is active.** Verify by:
- `curl -s https://bot.ualgotrade.com/healthz | python -m json.tool` → look for `"status": "suspended"`
- `docker compose -f docker-compose.prod.yml logs efloud-bot --tail 50 | grep "CRASH LOOP DETECTED"`

If you see suspension, the button doesn't work — proceed with manual recovery below.

## Manual recovery (operator)

### 1. Diagnose

SSH into Hetzner and inspect the recent logs:

\`\`\`bash
ssh efloud@<VPS_IP>
cd /opt/efloud-bot
docker compose -f docker-compose.prod.yml logs efloud-bot --tail 200 2>&1 | \
    grep -E "fatal_exception|Cycle error|CRASH LOOP|🛑|💥"
\`\`\`

Identify the recurring exception. Common causes:
- **Config error** (typo in `EFLOUD_CONFIG_PATH`, malformed YAML)
- **Exchange API key invalid / revoked**
- **DB pool failure** (Supabase outage, pgbouncer state corruption)
- **Code regression** (deployed a bad commit; check `git log -5`)

### 2. Fix the underlying issue

Address whatever the logs show. Examples:
- Bad config → fix `.env.production` or the YAML, no redeploy needed if just env
- Bad code → `git revert <bad-commit>` + rebuild + recreate
- Exchange auth → rotate keys via Binance dashboard, update `.env.production`

### 3. Reset crash_count to release suspension

Once the underlying issue is fixed, manually clear the crash-loop state:

\`\`\`bash
docker compose -f docker-compose.prod.yml exec efloud-bot python -c "
import asyncio
from engine.safety.runtime_state import RuntimeState
rs = RuntimeState(state_dir='./state')
rs.reset_crash_count()
print('crash_count reset:', rs.snapshot())
"
\`\`\`

This rewrites `state/runtime.json` inside the container's volume. The change persists across
restarts.

### 4. Restart the bot to clear the suspension

\`\`\`bash
docker compose -f docker-compose.prod.yml restart efloud-bot
\`\`\`

After ~30s:
- `/healthz` should return `200` with `status: "ok"` (or 503 with `loop_tick_never` until first cycle)
- Trading loop creates normally (no suspension log)
- If `EFLOUD_AUTOSTART=0`, manually start via dashboard or `POST /api/bot/start`

### 5. Confirm

\`\`\`bash
curl -s https://bot.ualgotrade.com/healthz | python -m json.tool
\`\`\`

Expected: `status: "ok"`, `failures: []`, `crash_count: 0`.

## Disabling autoheal in an emergency

If autoheal itself is misbehaving (loop-restarting a healthy container, etc.), disable it:

\`\`\`bash
docker compose -f docker-compose.prod.yml stop autoheal
\`\`\`

The bot's `restart: unless-stopped` policy still handles process EXIT crashes. You lose
auto-restart on sustained unhealth, which is the only thing autoheal adds.

## Spec deviation note

The original spec §3 architecture diagram said _"on unhealthy: docker auto-restart"_, but
stock Docker compose doesn't support restart-on-unhealthy. The `willfarrell/autoheal` sidecar
fills that gap — it polls Docker's API for unhealthy labeled containers and restarts them.

The spec §4.1 "Returns 503 if any check fails" wording is intentionally bent during crash-loop
suspension: returning 503 would cause autoheal to loop-restart the container instead of
letting suspension stick. Suspension mode returns 200 with `status: "suspended"` and a
`crash_loop_suspended` entry in `failures`. The alerter (Step 4) and daily-report (Step 5)
key off the `failures` field, not just the HTTP status.
```

- [ ] **Step 5.2: Commit**

```powershell
git add docs/runbooks/crash-loop-recovery.md
git commit -m "docs(runbooks): crash-loop recovery procedure (operator-facing)"
```

---

## Verification

### Task 6: End-to-end integration test

**Files:**
- Test: `tests/test_crash_loop.py` (append 1 test)

Walk through the full crash-loop lifecycle: bot ticks cleanly → crashes 3× → suspension activates → /healthz returns 200+suspended → manual reset clears it → bot recovers.

- [ ] **Step 6.1: Append the E2E test to tests/test_crash_loop.py**

```python
# ─────────────────────────────────────────────────────────────────────
# Task 6: End-to-end lifecycle
# ─────────────────────────────────────────────────────────────────────


def test_e2e_crash_loop_lifecycle(tmp_path: Path):
    """Full lifecycle: clean → 3 crashes → suspension → reset → recovers.

    Uses RuntimeState + evaluate_healthz directly. Does NOT spin up FastAPI/uvicorn
    (that's the smoke test in Step 7.2). Asserts every state transition.
    """
    rs = RuntimeState(state_dir=str(tmp_path))
    now_ms = int(time.time() * 1000)

    # T+0: bot just started, ticking cleanly
    rs.update_loop_tick()
    rs.update_exchange_ping()
    code, payload = evaluate_healthz(rs, breaker_halted=False, now_ms=now_ms)
    assert code == 200 and payload["status"] == "ok"

    # T+1min: first crash (e.g. cycle exception → bot exits → autoheal restarts → on next start
    # lifespan increment_crash() fires because fatal flag was set on disk)
    rs.increment_crash()
    assert rs.is_in_crash_loop() is False  # only 1 crash, not yet suspended

    # T+2min: second crash
    rs.increment_crash()
    assert rs.is_in_crash_loop() is False  # 2 < threshold

    # T+3min: third crash — suspension trips
    rs.increment_crash()
    assert rs.is_in_crash_loop() is True

    # /healthz now returns 200+suspended (autoheal stays quiet)
    rs.update_loop_tick()  # bot is alive, /healthz endpoint still responding
    rs.update_exchange_ping()
    code, payload = evaluate_healthz(rs, breaker_halted=False, now_ms=now_ms)
    assert code == 200, f"expected 200 in suspension, got {code}: {payload}"
    assert payload["status"] == "suspended"
    assert "crash_loop_suspended" in payload["failures"]

    # Operator manually clears via reset_crash_count() (per runbook step 3)
    rs.reset_crash_count()
    assert rs.is_in_crash_loop() is False

    # /healthz now returns 200+ok again
    rs.update_loop_tick()
    rs.update_exchange_ping()
    code, payload = evaluate_healthz(rs, breaker_halted=False, now_ms=now_ms)
    assert code == 200 and payload["status"] == "ok"
    assert payload["failures"] == []
```

- [ ] **Step 6.2: Run E2E test**

```powershell
python -m pytest tests/test_crash_loop.py::test_e2e_crash_loop_lifecycle -v 2>&1 | Select-Object -Last 10
```

Expected: 1 test passes.

- [ ] **Step 6.3: Run full suite**

```powershell
python -m pytest tests/ -q 2>&1 | Select-Object -Last 5
```

Expected: **83 pass + 6 skip = 89 collected** — the final target.

- [ ] **Step 6.4: Commit**

```powershell
git add tests/test_crash_loop.py
git commit -m "test(crash_loop): e2e lifecycle — clean → 3 crashes → suspended → manual reset → ok"
```

---

### Task 7: Final verification + push

**Files:** none modified (verification only).

- [ ] **Step 7.1: Full test suite final check**

```powershell
python -m pytest tests/ -q 2>&1 | Select-Object -Last 5
```

Expected: 83 pass + 6 skip = 89 collected. Specifically:
- Task 1: 3 in-memory crash-loop tests
- Task 2: 2 healthz suspended-branch tests
- Task 3: 1 bot_runner guard test
- Task 6: 1 E2E

Sum: 3 + 2 + 1 + 1 = 7 new. Pass count rises by 7. Skip count unchanged.

- [ ] **Step 7.2: Smoke test — boot real app, hit /healthz, verify idle 503**

Single-phase: just confirm the FastAPI app boots with the Step 3 changes and `/healthz` returns 503 when the bot is idle (no tick yet). Suspension-on-restart is fully covered by Task 6's E2E test on the in-process state machine, so the smoke doesn't need to re-test it.

```powershell
$env:EFLOUD_AUTOSTART = "0"
$env:EFLOUD_LOGGING_FORMAT = "json"

$py = @"
import threading, time, urllib.request, urllib.error, json
import uvicorn
config = uvicorn.Config('backend.main:app', host='127.0.0.1', port=8768, log_level='warning')
server = uvicorn.Server(config)
t = threading.Thread(target=lambda: server.run(), daemon=True)
t.start()
time.sleep(4)

try:
    resp = urllib.request.urlopen('http://127.0.0.1:8768/healthz', timeout=5)
    code, body = resp.getcode(), resp.read().decode()
except urllib.error.HTTPError as e:
    code, body = e.code, e.read().decode()
print('STATUS:', code)
parsed = json.loads(body)
assert code == 503, f'expected 503 idle, got {code}'
assert 'loop_tick_never' in parsed['failures']
print('SMOKE OK')
"@
$py | python
Remove-Item Env:\EFLOUD_AUTOSTART
Remove-Item Env:\EFLOUD_LOGGING_FORMAT
```

Expected: `STATUS: 503` + `SMOKE OK`.

If uvicorn-in-thread is fragile on Windows, skip and rely on Task 6's E2E coverage. Report DONE_WITH_CONCERNS rather than BLOCKED.

- [ ] **Step 7.3: Code review checklist (manual)**

Read each modified file and verify:
- `RuntimeState.is_in_crash_loop()`: reads via `snapshot()` (atomic, locked), no side effects
- `update_loop_tick()`: uses single `persist_dirty` flag to avoid duplicate `_save()` calls
- `evaluate_healthz()`: suspension branch is FIRST (precedence over normal checks), returns 200 not 503
- `bot_runner.start()`: crash-loop guard is FIRST in the method body (before any task creation)
- `docker-compose.prod.yml`: `start_period: 120s`, `labels: [autoheal=true]`, autoheal service has correct env vars and docker.sock mount
- Runbook references match actual command syntax (test the `docker compose exec ... python -c ...` snippet manually if uncertain)

- [ ] **Step 7.4: Push branch (defer tag until after merge to master)**

```powershell
git push origin feature/asama-2-step-3-watchdog
```

The tag `asama-2-step-3-complete` is created and pushed AFTER owner approval and merge to master. Same convention as Step 2.

- [ ] **Step 7.5: Final report**

Output to owner:
- Branch: `feature/asama-2-step-3-watchdog`
- Commits: ~6 (Task 1 + Task 2 + Task 3 + Task 4 + Task 5 + Task 6)
- Tests added: 7 (itemized in Step 0.3)
- New env vars: none
- New config: docker-compose.prod.yml gains autoheal sidecar + autoheal label
- New persistent state: none (reuses Step 2's `state/runtime.json`)
- Rollback: revert branch → no autoheal, no crash-loop suspension; Step 2's healthz still works
- **Production deploy notes (more involved than Step 2 because docker-compose.prod.yml changed):**
  1. Merge to master + push
  2. SSH to Hetzner: `cd /opt/efloud-bot && git pull origin master`
  3. Pull autoheal image: `docker compose -f docker-compose.prod.yml pull autoheal`
  4. Rebuild + recreate efloud-bot: `docker compose -f docker-compose.prod.yml up -d --build --force-recreate efloud-bot`
  5. Start autoheal: `docker compose -f docker-compose.prod.yml up -d autoheal`
  6. Verify all 3 containers up: `docker compose -f docker-compose.prod.yml ps` (efloud-bot, caddy, autoheal)
  7. Verify autoheal sees the bot's label: `docker logs efloud-autoheal | grep efloud-bot` (should show monitoring activity within 60s)
  8. Live restart-on-unhealthy verification (the actual integration test): `docker kill efloud-bot` once → autoheal should restart it within 60-90s; `/healthz` should transition `unhealthy → starting → healthy` cleanly
  9. (Optional, only if deploying outside trading hours) Crash-loop suspension verification: `docker kill efloud-bot` 3× within 30 min, observe that:
     - autoheal restarts each time (steps 1-2)
     - on the 3rd restart, bot enters suspension (`/healthz` returns 200 with `status:"suspended"`)
     - autoheal then sees `(healthy)` and stops restarting (suspension sticks)
     - manually recover via runbook: reset crash_count + container restart

---

## What this plan does NOT cover

Per spec §11, these are subsequent steps with their own plans:
- Step 4: Telegram alerter (will fire CRITICAL on `crash_loop_suspended` failure tag, plus other conditions)
- Step 5: Daily email report
- Step 6: Log rotation

---

## Rollback (if anything in this plan goes bad)

Per spec §14:

1. **Revert the branch:** `git revert <merge-commit>` on master, redeploy. Docker-compose loses the autoheal service (next `docker compose up -d` removes the container) and the bot loses crash-loop suspension. Step 2's basic healthz still works. No data risk.

2. **Disable autoheal only (keep code fixes):** `docker compose -f docker-compose.prod.yml stop autoheal`. The bot's crash-loop suspension keeps working in the bot's own process; you just lose auto-restart-on-unhealthy.

3. **Per-task rollback:** each task is its own commit; `git revert <hash>` for any single task that proves problematic.

4. **Manual escape hatch (suspension misfires):** edit `state/runtime.json` directly inside the container (per runbook), reset `crash_count` to 0, restart the container. Bot resumes normal operation.

---

## Acceptance for Step 3

Step 3 is **DONE** when:
- All Task 0-7 checkboxes are checked
- All tests pass (count = baseline + exactly 7 new = 83 pass + 6 skip = 89 collected)
- Smoke run with idle bot returns `/healthz` 503 with `loop_tick_never`
- E2E lifecycle test (Task 6) walks all transitions cleanly
- `docker-compose.prod.yml` validates with `docker compose config`
- Branch is pushed
- Owner reviews + approves before promoting to master and Hetzner

After acceptance → write the Step 4 plan (Telegram alerter).
