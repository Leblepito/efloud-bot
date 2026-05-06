# Aşama 2 — Step 2: Health-aware /healthz + crash-loop persistence Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the always-200 `/healthz` with a health-aware probe that returns 503 when the bot is sick (loop tick stale, exchange unreachable, fatal exception, or breaker halted), and persist `fatal_exception_state` + `crash_count` across Docker restarts via `state/runtime.json` so the watchdog (Step 3) can break crash-loops.

**Architecture:** New `RuntimeState` class manages thread-safe in-memory fields with atomic-write disk persistence (`state/runtime.json`). The bot's main loop (`backend/bot_runner._run_loop`) updates `last_loop_tick_ms` per cycle and `last_exchange_ping_ms` after `reconcile()` succeeds; uncaught cycle exceptions flip `fatal_exception_state` (auto-clears after 5 min of clean ticks). A pure-function `evaluate_healthz(state, breaker_halted, now_ms)` returns `(status_code, payload)` — easily unit-testable. The /healthz route reads from in-memory only (no disk I/O on the hot path; <50ms latency).

**Tech Stack:** Python 3.12, asyncio, FastAPI, threading.Lock (sync engine thread ↔ async healthz reader), pytest + pytest-asyncio. No new dependencies.

**Spec parent:** `docs/superpowers/specs/2026-05-07-asama-2-self-maintenance-observability-design.md` (§4.1, §11 Step 2)

**Estimated effort:** 3-5 days for one engineer.

---

## Codebase reality check (read first)

The spec §4.1 named files that don't exactly match the current tree. Real paths used in this plan (each verified against current master, post Aşama 2 Step 1 merge):

| Spec said | Reality on master |
|-----------|-------------------|
| `backend/api/routes/health.py` (new) | Current `/healthz` is at `backend/main.py:100-107` (registered directly on `app`, not via APIRouter). Plan creates new `backend/healthz.py` module and removes the old route from `backend/main.py`. |
| `engine/safe_orchestrator.py` (modify — track loop tick) | Wrong layer: `safe_orchestrator.run_cycle` is per-symbol (called multiple times per main loop). The actual main loop is `backend/bot_runner._run_loop` (line 178). Plan tracks loop_tick there. |
| `state/runtime.json` (new) | Aligns with existing pattern: `state/breaker.json`, `state/positions.json`, `state/scenarios.json` are already there. New file added alongside. |
| `SafeOrchestrator.run_once()` (spec wording) | Method does not exist; the analog is `safe_orchestrator.run_cycle` per symbol. Cycle-level exception catching happens in `bot_runner._run_loop:211` (the `try/except` around the cycle body). Plan flips fatal flag there. |

**Pre-existing infrastructure to reuse:**
- `engine/safety/state.py:StateStore` — atomic JSON write (tmp + rename + fsync). New `RuntimeState` uses the same atomic-write pattern but with custom flat schema (no `{saved_at, data}` wrapper) for direct field access.
- `engine/safety/breaker.py:CircuitBreaker.status.state` returns `BreakerState` enum (`OPEN` / `TRIPPED` / `HALTED`). The `breaker_halted` healthz input maps to `state == HALTED` (TRIPPED is a soft pause that auto-resumes; HALTED needs manual reset and IS a healthz fail).
- `backend/main.py:100-107` — existing `/healthz` GET handler (returns 200 always). Will be removed in Task 5 and replaced with a router from `backend/healthz.py`.

**Threading model:**
- `backend/bot_runner._run_loop` is **async** (runs on the FastAPI event loop). The cycle body uses `loop.run_in_executor(None, self._scan_universe)` to push sync engine work to a thread.
- `RuntimeState` updates happen from the async loop thread (after `run_in_executor` returns) AND potentially from the sync engine thread via `_scan_universe` if we surfaced finer-grained ticks. To keep the surface narrow, this plan only updates from the async loop thread (after each cycle completes), so a `threading.Lock` is sufficient (and arguably overkill, but adds clarity + future-proofing for finer-grained sync-thread ticks).
- Healthz endpoint is async. It reads via `state.snapshot()` which acquires the lock. Lock contention is negligible (writes are ~1Hz, reads are ~30s/1Hz from Docker healthcheck).

---

## File structure (what gets created vs modified)

**Create:**
- `engine/safety/runtime_state.py` — `RuntimeState` class with thread-safe in-memory fields + disk persistence
- `backend/healthz.py` — `evaluate_healthz` pure function + `health_router` APIRouter exposing `GET /healthz`
- `tests/test_runtime_state.py` — `RuntimeState` unit tests
- `tests/test_healthz_logic.py` — `evaluate_healthz` pure-function tests
- `tests/test_healthz_endpoint.py` — `/healthz` endpoint integration tests (FastAPI TestClient)
- `tests/test_runtime_state_persistence.py` — disk persistence tests (atomic write, load on init, corruption recovery)

**Modify:**
- `backend/bot_runner.py` — instantiate `RuntimeState`, call `update_loop_tick`/`update_exchange_ping`/`set_fatal_exception` from `_run_loop`. Increment crash counter on startup if fatal flag was set.
- `backend/main.py` — remove inline `/healthz` handler (lines 100-107), include `health_router` from `backend/healthz.py`.

**Delete:** none (the old `/healthz` is replaced, not deleted as a file — only the route is removed from `backend/main.py`).

---

## Pre-flight

### Task 0: Worktree + branch setup, baseline verification

**Files:** none modified, only environment setup.

- [ ] **Step 0.1: Create dedicated worktree from master**

```powershell
cd C:\Users\utkuc\Downloads\efloud-bot
git worktree add ../efloud-bot-asama2-step2 -b feature/asama-2-step-2-healthz master
cd ../efloud-bot-asama2-step2
```

Expected: new worktree on branch `feature/asama-2-step-2-healthz`, based on master HEAD (post Aşama 2 Step 1 merge).

- [ ] **Step 0.2: Verify base tests pass**

```powershell
python -m pytest tests/ -q --no-header 2>&1 | Select-Object -Last 5
```

Expected: 47+ pass, ≤6 skip (DB-dependent SKIPs without DATABASE_URL_TEST). If anything FAILS at baseline, STOP and surface to owner.

- [ ] **Step 0.3: Capture baseline test count**

Record exact counts (e.g., `BASELINE_PASSED=47`, `BASELINE_SKIPPED=6`). Pin this number; Step 1 of Aşama 2 already shifted master's baseline post-merge — re-verify with `pytest --collect-only -q tests/ | Select-Object -Last 3` before starting. Final test count after Step 2 must be **exactly** `BASELINE_PASSED + 24` collected (the running master baseline + 24 new tests added by this plan; SKIP count unchanged).

New tests added by this plan (= 24):
- Task 1 (`tests/test_runtime_state.py`): 7 tests (`test_initial_fields_are_none_or_zero`, `test_update_loop_tick_sets_timestamp`, `test_update_exchange_ping_sets_timestamp`, `test_set_fatal_exception_records_flag_and_timestamp`, `test_fatal_auto_clears_after_5min_clean_ticks`, `test_fatal_does_not_clear_before_5min`, `test_increment_crash_increments_counter`)
- Task 1 (`tests/test_runtime_state_persistence.py`): 4 tests (`test_save_and_load_round_trip`, `test_load_returns_clean_when_file_missing`, `test_load_recovers_from_corrupted_file`, `test_loop_tick_not_persisted_across_restart`)
- Task 2 (`tests/test_healthz_logic.py`): 7 tests (`test_returns_200_when_all_clean`, `test_returns_503_when_loop_tick_stale`, `test_returns_503_when_loop_tick_never_set`, `test_returns_503_when_exchange_ping_stale`, `test_returns_503_when_exchange_ping_never_set`, `test_returns_503_when_fatal_exception_set`, `test_returns_503_when_breaker_halted`)
- Task 4 (`tests/test_healthz_endpoint.py`): 3 tests (`test_healthz_endpoint_returns_200_when_clean`, `test_healthz_endpoint_returns_503_when_unhealthy`, `test_healthz_payload_shape`)
- Task 5 (`tests/test_runtime_state_persistence.py`, persistence add-on): 2 tests (`test_clean_shutdown_then_startup_resets_crash_count`, `test_dirty_shutdown_then_startup_increments_crash_count`)
- Task 6 (E2E integration): 1 test (`test_full_lifecycle_loop_tick_to_healthz`)

Total: 7+4+7+3+2+1 = **24**.

Running totals at each task boundary (pin these for Tasks 3-6 verification):
- After Task 1: baseline + 11 (7 in-memory + 4 persistence)
- After Task 2: baseline + 18 (+7 logic)
- After Task 3: baseline + 18 (no new tests; engine wiring only)
- After Task 4: baseline + 21 (+3 endpoint)
- After Task 5: baseline + 23 (+2 persistence add-on)
- After Task 6: baseline + 24 (+1 E2E) ← FINAL

- [ ] **Step 0.4: Confirm `state/` is in `.gitignore` (state files should not be committed)**

```powershell
Select-String -Path .gitignore -Pattern "^state/?\b" 2>&1
```

Expected: a match like `state/` or `/state/`. If MISSING (state files would get committed), STOP and add `state/` to `.gitignore` first as a precondition. The `state/runtime.json` we create must not be committed.

---

## Foundation: RuntimeState

### Task 1: RuntimeState class with persistence

**Files:**
- Create: `engine/safety/runtime_state.py` (~120 lines)
- Test: `tests/test_runtime_state.py` (in-memory behavior, 7 tests)
- Test: `tests/test_runtime_state_persistence.py` (disk persistence, 4 tests)

- [ ] **Step 1.1: Write in-memory unit tests first**

Create `tests/test_runtime_state.py`:

```python
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
```

- [ ] **Step 1.2: Run tests, expect FAIL**

```powershell
python -m pytest tests/test_runtime_state.py -v 2>&1
```

Expected: ImportError ("No module named 'engine.safety.runtime_state'") — all 7 tests fail at collection.

- [ ] **Step 1.3: Write persistence tests**

Create `tests/test_runtime_state_persistence.py`:

```python
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
    snap1 = s1.snapshot()
    assert snap1["last_loop_tick_ms"] is not None  # set in-memory

    # Verify file does NOT contain last_loop_tick_ms (or contains None)
    runtime_path = tmp_path / "runtime.json"
    assert runtime_path.exists()
    on_disk = json.loads(runtime_path.read_text(encoding="utf-8"))
    assert "last_loop_tick_ms" not in on_disk or on_disk["last_loop_tick_ms"] is None

    # Fresh instance must have None
    s2 = RuntimeState(state_dir=str(tmp_path))
    snap2 = s2.snapshot()
    assert snap2["last_loop_tick_ms"] is None
```

- [ ] **Step 1.4: Run persistence tests, expect FAIL**

```powershell
python -m pytest tests/test_runtime_state_persistence.py -v 2>&1
```

Expected: ImportError; 4 tests fail.

- [ ] **Step 1.5: Implement RuntimeState class**

Create `engine/safety/runtime_state.py`:

```python
"""Persistent runtime state for healthz / crash-loop detection.

Tracks four signals:
  - last_loop_tick_ms — main bot loop liveness (volatile, NOT persisted)
  - last_exchange_ping_ms — exchange connectivity (volatile, NOT persisted)
  - fatal_exception_state — sticky flag (PERSISTED across restarts)
  - crash_count + last_crash_ms — crash-loop detection (PERSISTED)

Volatile fields are intentionally not persisted: a bot that just restarted has
no fresh loop-tick or exchange-ping evidence yet, so loading stale values would
falsely report healthy. The healthz endpoint correctly reports 503 (unhealthy)
during the startup window until the first cycle ticks succeed.

Persistence: state/runtime.json (atomic write via tmp + os.replace + fsync).
Concurrency: threading.Lock guards in-memory writes; reads via snapshot() also
take the lock for atomic snapshot of all fields.
"""
from __future__ import annotations

import json
import logging
import os
import threading
import time
from pathlib import Path
from typing import Optional

log = logging.getLogger("efloud.runtime_state")

# 5 minutes — fatal flag auto-clears after this many ms of clean ticks since it was set
FATAL_CLEAR_AFTER_MS = 5 * 60 * 1000


class RuntimeState:
    """Thread-safe in-memory + persistent runtime state."""

    def __init__(self, state_dir: str = "./state"):
        self.dir = Path(state_dir)
        self.dir.mkdir(parents=True, exist_ok=True)
        self.path = self.dir / "runtime.json"
        self._lock = threading.Lock()
        # Volatile (in-memory only)
        self.last_loop_tick_ms: Optional[int] = None
        self.last_exchange_ping_ms: Optional[int] = None
        # Persistent
        self.fatal_exception_state: bool = False
        self.fatal_exception_set_at_ms: Optional[int] = None
        self.crash_count: int = 0
        self.last_crash_ms: Optional[int] = None
        self._load()

    def _load(self) -> None:
        """Load persistent fields from disk. Missing/corrupted file → clean state."""
        if not self.path.exists():
            return
        try:
            with open(self.path, "r", encoding="utf-8") as f:
                data = json.load(f)
            self.fatal_exception_state = bool(data.get("fatal_exception_state", False))
            self.fatal_exception_set_at_ms = data.get("fatal_exception_set_at_ms")
            self.crash_count = int(data.get("crash_count", 0))
            self.last_crash_ms = data.get("last_crash_ms")
        except Exception as e:
            log.error(f"runtime_state load failed: {e}; starting clean")
            # Move corrupted file aside so subsequent saves succeed
            try:
                backup = self.path.with_suffix(f".corrupted.{int(time.time())}")
                self.path.rename(backup)
                log.warning(f"corrupted runtime.json moved to {backup}")
            except Exception:
                pass

    def _save(self) -> None:
        """Atomic write of persistent fields. Caller MUST hold self._lock."""
        tmp = self.path.with_suffix(".json.tmp")
        try:
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump({
                    "fatal_exception_state": self.fatal_exception_state,
                    "fatal_exception_set_at_ms": self.fatal_exception_set_at_ms,
                    "crash_count": self.crash_count,
                    "last_crash_ms": self.last_crash_ms,
                }, f, indent=2)
                f.flush()
                os.fsync(f.fileno())
            os.replace(str(tmp), str(self.path))
        except Exception as e:
            log.error(f"runtime_state save failed: {e}")
            try:
                tmp.unlink()
            except Exception:
                pass

    def update_loop_tick(self) -> None:
        """Called from main loop after each successful cycle.

        Side effect: auto-clears fatal_exception_state if 5+ min have elapsed
        since the flag was set (i.e. the bot has been running cleanly for long
        enough to be considered recovered).
        """
        now_ms = int(time.time() * 1000)
        with self._lock:
            self.last_loop_tick_ms = now_ms
            if self.fatal_exception_state and self.fatal_exception_set_at_ms is not None:
                if now_ms - self.fatal_exception_set_at_ms >= FATAL_CLEAR_AFTER_MS:
                    self.fatal_exception_state = False
                    self.fatal_exception_set_at_ms = None
                    self._save()

    def update_exchange_ping(self) -> None:
        """Called when an exchange API call succeeds (e.g. reconcile)."""
        with self._lock:
            self.last_exchange_ping_ms = int(time.time() * 1000)

    def set_fatal_exception(self) -> None:
        """Called when bot main loop catches an uncaught cycle exception.

        Idempotent: if already set, only updates the timestamp to the latest
        exception (sliding 5-min auto-clear window).
        """
        now_ms = int(time.time() * 1000)
        with self._lock:
            self.fatal_exception_state = True
            self.fatal_exception_set_at_ms = now_ms
            self._save()

    def increment_crash(self) -> None:
        """Called once at startup if fatal_exception_state is set on disk
        (i.e. the previous run died with the flag set).
        """
        now_ms = int(time.time() * 1000)
        with self._lock:
            self.crash_count += 1
            self.last_crash_ms = now_ms
            self._save()

    def reset_crash_count(self) -> None:
        """Called once at startup if fatal_exception_state is CLEAN on disk
        (previous run shut down healthy). Resets crash counter to 0.
        """
        with self._lock:
            if self.crash_count != 0 or self.last_crash_ms is not None:
                self.crash_count = 0
                self.last_crash_ms = None
                self._save()

    def snapshot(self) -> dict:
        """Atomic read of all fields for healthz endpoint."""
        with self._lock:
            return {
                "last_loop_tick_ms": self.last_loop_tick_ms,
                "last_exchange_ping_ms": self.last_exchange_ping_ms,
                "fatal_exception_state": self.fatal_exception_state,
                "fatal_exception_set_at_ms": self.fatal_exception_set_at_ms,
                "crash_count": self.crash_count,
                "last_crash_ms": self.last_crash_ms,
            }
```

- [ ] **Step 1.6: Run all RuntimeState tests, expect PASS**

```powershell
python -m pytest tests/test_runtime_state.py tests/test_runtime_state_persistence.py -v 2>&1
```

Expected: 11 tests pass (7 in-memory + 4 persistence).

- [ ] **Step 1.7: Commit**

```powershell
git add engine/safety/runtime_state.py tests/test_runtime_state.py tests/test_runtime_state_persistence.py
git commit -m "feat(state): RuntimeState class with thread-safe in-memory + atomic disk persistence"
```

---

### Task 2: Healthz pure-function logic

**Files:**
- Create: `backend/healthz.py` (initial scaffolding — APIRouter + evaluate_healthz pure function)
- Test: `tests/test_healthz_logic.py` (7 pure-function tests)

This task creates the testable LOGIC. Task 4 wires it into the FastAPI app.

- [ ] **Step 2.1: Write logic tests first**

Create `tests/test_healthz_logic.py`:

```python
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


def test_returns_503_when_breaker_halted(state: RuntimeState):
    now_ms = 10_000_000
    _make_clean(state, now_ms)
    code, payload = evaluate_healthz(state, breaker_halted=True, now_ms=now_ms)
    assert code == 503
    assert "breaker_halted" in payload["failures"]
```

- [ ] **Step 2.2: Run tests, expect FAIL**

```powershell
python -m pytest tests/test_healthz_logic.py -v 2>&1
```

Expected: ImportError on `backend.healthz`. All 7 tests fail.

- [ ] **Step 2.3: Implement evaluate_healthz**

Create `backend/healthz.py`:

```python
"""Health-aware /healthz endpoint.

Returns 200 only when ALL conditions hold:
  - last_loop_tick_ms within last 90s (bot's main loop is alive)
  - last_exchange_ping_ms within last 60s (exchange is reachable)
  - fatal_exception_state is False (no recent uncaught cycle exception)
  - breaker not in HALTED state (a halted bot is not "healthy")

Returns 503 otherwise. Reads in-memory only — no disk I/O on the hot path.
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

    Args:
        state: RuntimeState instance (read-only — caller takes a snapshot inside).
        breaker_halted: True if CircuitBreaker is in HALTED state.
        now_ms: current epoch ms (passed in for testability — never call time.time() here).

    Returns:
        (200, payload) when all conditions hold.
        (503, payload) when any condition fails. payload["failures"] lists offending checks.
    """
    snap = state.snapshot()
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
```

- [ ] **Step 2.4: Run tests, expect PASS**

```powershell
python -m pytest tests/test_healthz_logic.py -v 2>&1
```

Expected: 7 tests pass.

- [ ] **Step 2.5: Commit**

```powershell
git add backend/healthz.py tests/test_healthz_logic.py
git commit -m "feat(healthz): pure-function evaluate_healthz + APIRouter scaffolding"
```

---

## Engine integration

### Task 3: Wire RuntimeState into bot_runner main loop

**Files:**
- Modify: `backend/bot_runner.py:_run_loop` (lines ~178-220) and constructor

This task connects the engine's main loop to the new state tracker. No new tests — coverage comes from Task 6's E2E and existing regression suite.

- [ ] **Step 3.1: Add RuntimeState instantiation to bot_runner constructor**

Read `backend/bot_runner.py` to find the `BotRunner.__init__` (or equivalent constructor). Locate the `__init__` block and add a `RuntimeState` instance.

```powershell
Select-String -Path backend\bot_runner.py -Pattern "def __init__|class BotRunner|self.cfg|self.cycle_count" | Select-Object -First 10
```

Inside the constructor (where other instance attributes like `self.cycle_count = 0` live), add:

```python
        # Healthz / crash-loop runtime state (Aşama 2 Step 2)
        from engine.safety.runtime_state import RuntimeState
        state_dir = (
            self.cfg.get("operation", {}).get("state_dir") if self.cfg else None
        ) or os.environ.get("EFLOUD_STATE_DIR", "./state")
        self.runtime_state = RuntimeState(state_dir=state_dir)
```

The import is local to keep startup-time imports lean. `state_dir` honors the same config knob the rest of the bot uses (see configs/*.yaml `operation.state_dir`).

If `os` is not already imported in `backend/bot_runner.py`, add `import os` to the top-of-file imports.

- [ ] **Step 3.2: Update `_run_loop` to call update_loop_tick after each cycle**

Locate the cycle body in `_run_loop` (around line 199-207 — the block that publishes `cycle_end`). Add the tick update RIGHT BEFORE `bus.publish("cycle_end", ...)`:

```python
                duration_ms = int((loop.time() - t0) * 1000)
                self.last_cycle_duration_ms = duration_ms
                self.last_cycle_at = self._now_iso()
                self.runtime_state.update_loop_tick()        # NEW — Aşama 2 Step 2
                bus.publish(
                    "cycle_end",
                    cycle_n=self.cycle_count,
                    duration_ms=duration_ms,
                    open_positions=len(self.order_mgr.positions) if self.order_mgr else 0,
                )
```

This guarantees: a tick is recorded only when the cycle completes WITHOUT raising an exception (the `try` block above. The `except Exception as e:` branch at line 211 does NOT call `update_loop_tick`, so a sick cycle is correctly NOT counted as fresh activity.

- [ ] **Step 3.3: Update `_run_loop` to call update_exchange_ping after reconcile succeeds**

Locate the reconcile call inside the cycle (around line 191-194). Add ping update RIGHT AFTER reconcile returns successfully:

```python
                # Reconcile first (sync ccxt — run in thread)
                if self.order_mgr and not self.cfg["operation"]["dry_run"]:
                    closed = await loop.run_in_executor(None, self.order_mgr.reconcile)
                    self.runtime_state.update_exchange_ping()    # NEW — exchange is reachable
                    for pos in closed:
                        await self._persist_close(pos)
```

If `dry_run=True` (test/paper-trading mode), no reconcile = no exchange call = no ping. That's correct — paper-trading shouldn't claim exchange connectivity it isn't using. Healthz will return 503 (`exchange_ping_never`) in pure dry-run mode, which is acceptable: dry-run is a development mode, not a production deployment.

- [ ] **Step 3.4: Update `_run_loop` exception handler to set fatal_exception**

Locate the `except Exception as e:` block at line 211-213. Add the fatal flag flip:

```python
            except asyncio.CancelledError:
                raise
            except Exception as e:
                log.error(f"Cycle error: {e}", exc_info=True)
                bus.publish("error", message=str(e))
                self.runtime_state.set_fatal_exception()    # NEW — sticky flag for healthz
```

Order matters: log + publish first (so the error is observable even if the disk write fails), then set the flag.

- [ ] **Step 3.5: Run regression tests**

```powershell
python -m pytest tests/ -q 2>&1 | Select-Object -Last 5
```

Expected: existing tests still pass (47 + 11 from Task 1 + 6 from Task 2 = 64 collected, all pass except 6 pre-existing DB-dependent skips).

- [ ] **Step 3.6: Commit**

```powershell
git add backend/bot_runner.py
git commit -m "feat(bot_runner): wire RuntimeState updates from main loop (tick + ping + fatal)"
```

---

### Task 4: Wire /healthz endpoint into FastAPI app

**Files:**
- Modify: `backend/main.py` — remove inline `/healthz` (lines 100-107), include `health_router`, call `configure()` during startup
- Test: `tests/test_healthz_endpoint.py` (3 endpoint integration tests)

- [ ] **Step 4.1: Write endpoint integration tests**

Create `tests/test_healthz_endpoint.py`:

```python
"""Healthz endpoint integration tests — verify wiring + status code semantics."""
from __future__ import annotations

import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from engine.safety.runtime_state import RuntimeState


@pytest.fixture
def configured_app(tmp_path: Path):
    """Build a FastAPI app with healthz wired to a fresh RuntimeState we control."""
    from fastapi import FastAPI
    from backend.healthz import health_router, configure

    rs = RuntimeState(state_dir=str(tmp_path))

    breaker_halted = {"v": False}  # mutable wrapper; tests flip it

    def get_halted() -> bool:
        return breaker_halted["v"]

    configure(rs, get_halted)

    app = FastAPI()
    app.include_router(health_router)
    return app, rs, breaker_halted


def test_healthz_endpoint_returns_200_when_clean(configured_app):
    app, rs, _ = configured_app
    # Simulate clean state: recent tick + ping
    rs.update_loop_tick()
    rs.update_exchange_ping()

    client = TestClient(app)
    r = client.get("/healthz")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert body["failures"] == []


def test_healthz_endpoint_returns_503_when_unhealthy(configured_app):
    app, rs, breaker = configured_app
    # Don't call update_loop_tick — last_loop_tick_ms remains None
    client = TestClient(app)
    r = client.get("/healthz")
    assert r.status_code == 503
    body = r.json()
    assert body["status"] == "unhealthy"
    assert "loop_tick_never" in body["failures"]


def test_healthz_payload_shape(configured_app):
    app, rs, _ = configured_app
    rs.update_loop_tick()
    rs.update_exchange_ping()
    client = TestClient(app)
    r = client.get("/healthz")
    body = r.json()
    # Required keys
    for key in ("status", "checks", "now_ms", "failures"):
        assert key in body, f"missing key: {key}"
    # Checks sub-shape
    for key in ("last_loop_tick_ms", "last_exchange_ping_ms",
                "fatal_exception_state", "crash_count"):
        assert key in body["checks"], f"missing checks key: {key}"
```

- [ ] **Step 4.2: Run tests, expect PASS**

```powershell
python -m pytest tests/test_healthz_endpoint.py -v 2>&1
```

Task 2 already implemented `evaluate_healthz` AND wired `health_router` to accept `configure()`-injected dependencies. The fixture in Step 4.1 calls `configure(rs, get_halted)` before `TestClient(app).get("/healthz")`, so all 3 endpoint tests should PASS without further code changes. If any fail, debug before continuing — likely cause would be an import path error or missing dependency wiring from Task 2.

Expected: **3 tests PASS**. Document actual outcome (pass/fail counts and any error messages) before moving to Step 4.3.

- [ ] **Step 4.3: Wire health_router into backend/main.py**

Read `backend/main.py` to locate:
1. The current `/healthz` handler (lines 100-107)
2. Where routers are included (the `api_router` include line)
3. The `lifespan` async context manager (line 40+)

**Required modifications to `backend/main.py`, in order:**

**(a) Add import** alongside the other router imports (near line 24):

```python
from backend.healthz import health_router, configure as configure_healthz
```

**(b) Remove the inline `/healthz` handler** (delete lines 100-107). The pre-existing comment block at lines 110-117 referencing `/healthz` is still accurate — the route just moves to the router.

**(c) Add `app.include_router(health_router)`** alongside the existing `app.include_router(api_router, ...)` line.

**(d) Inside `lifespan`, add the explicit ordering of these 4 steps** (after `await db.connect()` and any bot_runner construction; BEFORE `yield`):

```python
    # === Aşama 2 Step 2 healthz wiring (ORDER MATTERS) ===
    # Step 1: ensure `runner` is constructed and has runtime_state
    #         (BotRunner.__init__ from Task 3.1 creates runner.runtime_state eagerly).
    assert runner.runtime_state is not None, "BotRunner did not initialize runtime_state"

    # Step 2: configure the healthz router with concrete dependencies.
    def _breaker_halted() -> bool:
        try:
            from engine.safety.breaker import BreakerState
            if runner.orch is None:
                return False  # bot idle (not yet started); loop_tick_never will mark unhealthy anyway
            return runner.orch.breaker.status.state == BreakerState.HALTED
        except Exception:
            return False
    configure_healthz(runner.runtime_state, _breaker_halted)

    # Step 3: crash counter logic (added in Task 5).
    # (Placeholder comment here; Task 5 fills it in.)

    # Step 4: yield to FastAPI for request serving (existing `yield` line follows).
```

The `assert` is intentional defensive coding — if a future refactor breaks the ordering, the failure mode is loud (assertion at startup) instead of silent (healthz never reports because `_runtime_state` is None).

The lambda-style breaker getter delays the breaker-state read until each healthz call — no stale snapshots. When `runner.orch is None` (bot started in API-only mode with `EFLOUD_AUTOSTART=0`), we report `False` for halted — the `loop_tick_never` check will already mark this case unhealthy, so the breaker check doesn't double-flag.

- [ ] **Step 4.4: Run endpoint tests + full suite**

```powershell
python -m pytest tests/test_healthz_endpoint.py tests/test_runtime_state.py tests/test_runtime_state_persistence.py tests/test_healthz_logic.py -v 2>&1 | Select-Object -Last 25
python -m pytest tests/ -q 2>&1 | Select-Object -Last 5
```

Expected: all of the above pass. Total test count at this point = baseline + 21 (Tasks 1+2+4 done). Task 5 adds 2 more, Task 6 adds 1 more, final = baseline + 24.

(Step 4.5 uvicorn-in-thread smoke test was removed during plan review — the FastAPI TestClient coverage in Step 4.2 already exercises the same ASGI app through the same route, and uvicorn-in-thread is fragile on Windows. The boot-the-real-app smoke is preserved at Step 7.2 as a final check.)

- [ ] **Step 4.5: Commit**

```powershell
git add backend/main.py tests/test_healthz_endpoint.py
git commit -m "feat(healthz): wire health-aware /healthz into FastAPI app, replace always-200 stub"
```

(Numbering note: the original plan had a Step 4.5 smoke test + Step 4.6 commit; the smoke step was dropped during plan review, so this commit became Step 4.5.)

---

### Task 5: Crash counter on startup

**Files:**
- Modify: `backend/main.py:lifespan` — increment crash_count if fatal flag was set on disk; otherwise reset

**Critical behavior:** The previous run's exit state determines what happens at this run's startup:
- If `state/runtime.json` had `fatal_exception_state == True`: the previous run died sick. `increment_crash()`. The flag stays set on disk (loaded by RuntimeState constructor) and will only auto-clear after 5 min of clean ticks in this run.
- If `state/runtime.json` had `fatal_exception_state == False` (or file absent): previous run exited cleanly. `reset_crash_count()` (clear any stale crash counter from older runs).

This logic runs ONCE at app startup, in `lifespan` after `runner` is constructed.

- [ ] **Step 5.1: Add crash-counter logic to lifespan**

In `backend/main.py:lifespan`, AFTER `runner` is constructed and AFTER `configure_healthz(...)` is called, add:

```python
    # Aşama 2 Step 2: crash-loop counter
    rs = runner.runtime_state
    snap = rs.snapshot()
    if snap["fatal_exception_state"]:
        rs.increment_crash()
        log.warning(
            "💥 Previous run exited with fatal_exception_state=True; "
            f"crash_count now {rs.snapshot()['crash_count']}"
        )
    else:
        rs.reset_crash_count()
```

The reset path is important: a bot that's been running cleanly for 30 days, then has 1 crash, should report `crash_count=1`. Without reset, the counter would keep climbing across unrelated restarts (manual restarts, deploys, etc.) and the crash-loop alarm (Step 4 in roadmap) would false-fire.

- [ ] **Step 5.2: Add a unit test for the crash-counter logic**

We test the branching behavior directly via RuntimeState (the lifespan-level wiring is exercised by Task 6's E2E). Add a test to `tests/test_runtime_state_persistence.py`:

```python
def test_clean_shutdown_then_startup_resets_crash_count(tmp_path: Path):
    """Clean fatal_exception_state on disk → next startup reset_crash_count() → 0."""
    # Pre-condition: write a runtime.json with stale crash_count but clean fatal flag
    s1 = RuntimeState(state_dir=str(tmp_path))
    s1.increment_crash()
    s1.increment_crash()
    s1.increment_crash()  # 3 crashes accumulated
    assert s1.snapshot()["crash_count"] == 3
    # Now: simulate "previous run exited cleanly" — fatal flag is already False
    assert s1.snapshot()["fatal_exception_state"] is False

    # Fresh startup: load + reset
    s2 = RuntimeState(state_dir=str(tmp_path))
    s2.reset_crash_count()
    snap = s2.snapshot()
    assert snap["crash_count"] == 0
    assert snap["last_crash_ms"] is None


def test_dirty_shutdown_then_startup_increments_crash_count(tmp_path: Path):
    """Set fatal_exception_state on disk → next startup increment_crash() → counter rises."""
    s1 = RuntimeState(state_dir=str(tmp_path))
    s1.set_fatal_exception()
    assert s1.snapshot()["fatal_exception_state"] is True
    assert s1.snapshot()["crash_count"] == 0

    # Fresh startup: load + increment
    s2 = RuntimeState(state_dir=str(tmp_path))
    assert s2.snapshot()["fatal_exception_state"] is True  # loaded from disk
    s2.increment_crash()
    snap = s2.snapshot()
    assert snap["crash_count"] == 1
    assert snap["fatal_exception_state"] is True  # still set; auto-clears later
```

These 2 tests bring the persistence test count from 4 → 6. Step 0.3 already accounts for them in the running totals (final count = baseline + 24).

- [ ] **Step 5.3: Run new persistence tests, expect PASS**

```powershell
python -m pytest tests/test_runtime_state_persistence.py -v 2>&1
```

Expected: 6 tests pass (4 from Task 1 + 2 new).

- [ ] **Step 5.4: Run full suite**

```powershell
python -m pytest tests/ -q 2>&1 | Select-Object -Last 5
```

Expected: all pass; collected count = baseline + 23 (Tasks 1-5 done: 11 + 7 + 3 + 2 = 23. E2E in Task 6 adds the last +1 for final = baseline + 24).

- [ ] **Step 5.5: Commit**

```powershell
git add backend/main.py tests/test_runtime_state_persistence.py
git commit -m "feat(healthz): crash counter increment on dirty startup, reset on clean"
```

---

## Verification

### Task 6: End-to-end integration test

**Files:**
- Test: `tests/test_healthz_e2e.py` (1 test that exercises the full lifecycle)

The E2E test simulates: a bot that ticks → fatal exception → 5 min later resumes ticking → flag clears. Uses RuntimeState directly + evaluate_healthz; does NOT spin up uvicorn (that's the smoke test in Step 7.2).

- [ ] **Step 6.1: Write E2E test**

Create `tests/test_healthz_e2e.py`:

```python
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
```

- [ ] **Step 6.2: Run E2E test**

```powershell
python -m pytest tests/test_healthz_e2e.py -v 2>&1
```

Expected: 1 test passes.

- [ ] **Step 6.3: Commit**

```powershell
git add tests/test_healthz_e2e.py
git commit -m "test(healthz): e2e lifecycle — never_ticked → clean → fatal → recovers → halted"
```

---

### Task 7: Final verification + acceptance check

**Files:** none modified (verification only).

- [ ] **Step 7.1: Full test suite**

```powershell
python -m pytest tests/ -q 2>&1 | Select-Object -Last 5
```

Expected: total = baseline + **24** new tests. Specifically:
- Task 1: 7 in-memory + 4 persistence = 11
- Task 2: 7 logic (6 conditions + 1 symmetry test for `exchange_ping_never`)
- Task 4: 3 endpoint
- Task 5: 2 persistence add-on
- Task 6: 1 E2E

Sum: 11 + 7 + 3 + 2 + 1 = 24. Pass count rises by 24. Skip count unchanged.

- [ ] **Step 7.2: Smoke run with bot off, verify /healthz returns 503**

```powershell
$env:EFLOUD_AUTOSTART = "0"
$env:EFLOUD_LOGGING_FORMAT = "json"
# Background-start the FastAPI app and curl /healthz once
python -c @"
import threading, time, urllib.request, urllib.error
import uvicorn

config = uvicorn.Config('backend.main:app', host='127.0.0.1', port=8766, log_level='warning')
server = uvicorn.Server(config)
t = threading.Thread(target=lambda: server.run(), daemon=True)
t.start()
time.sleep(3)

try:
    resp = urllib.request.urlopen('http://127.0.0.1:8766/healthz', timeout=5)
    print(f'STATUS: {resp.getcode()}')
except urllib.error.HTTPError as e:
    print(f'STATUS: {e.code}')
    print(f'BODY: {e.read().decode()[:300]}')
"@
Remove-Item Env:\EFLOUD_AUTOSTART
Remove-Item Env:\EFLOUD_LOGGING_FORMAT
```

Expected: `STATUS: 503` with body containing `loop_tick_never` (correctly: bot is idle, no cycles ticked).

- [ ] **Step 7.3: Code review checklist (manual)**

Read each modified/new file and verify:
- `RuntimeState`: thread-safety (every write inside `with self._lock`), atomic disk write (tmp + os.replace + fsync), volatile fields not persisted
- `evaluate_healthz`: pure function (no side effects, no time.time() inside), clear failure messages
- `bot_runner._run_loop`: `update_loop_tick` is OUTSIDE the `except` branch (only ticks on success), `update_exchange_ping` is AFTER `reconcile()` not before
- `backend/main.py:lifespan`: crash-counter logic runs ONCE at startup, after RuntimeState is constructed
- No print() statements added anywhere
- No bare `except:` introduced
- No DATABASE_URL or API key leaked into logs (privacy §9)

- [ ] **Step 7.4: Push branch (defer tag until after merge to master)**

```powershell
git push origin feature/asama-2-step-2-healthz
```

The tag `asama-2-step-2-complete` is created and pushed AFTER owner approval and merge to master (Step 7.5 owner action). Tagging the feature branch before merge would conflict with the convention used for Aşama 2 Step 1 where the tag marks the fully-shipped commit.

- [ ] **Step 7.5: Final report (push to share with owner)**

Output to owner:
- Branch: `feature/asama-2-step-2-healthz`
- Commits: ~7 (one per task with test/impl pairs)
- Tests added: 24 (itemized in Step 0.3)
- New env vars: none
- New config keys: none (`operation.state_dir` already existed)
- Persistent state file: `state/runtime.json` (new — must be in .gitignore alongside other state files)
- Rollback: revert branch (no schema/migration changes)
- Production deploy notes:
  - No migrations to apply (Step 2 is pure code)
  - No bot downtime required for state file (created on first save)
  - Recommended deploy sequence: rebuild image, force-recreate, watch /healthz transitions in first 2-3 min (should go 503 → 200 once first cycle ticks)
  - **Step 3 (Docker compose healthcheck tuning) depends on this Step 2 — the existing healthcheck stanza in docker-compose.prod.yml works as-is, just smarter now**

---

## What this plan does NOT cover

Per spec §11, these are subsequent steps with their own plans:
- Step 3: Docker compose healthcheck `interval`/`timeout`/`retries` tuning + `restart: on-failure:5` policy
- Step 4: Telegram alerter + SQLite dedup + heartbeat (will fire on `health.crash_loop` event when crash_count crosses 3 in 30 min)
- Step 5: Daily email report
- Step 6: Log rotation

---

## Rollback (if anything in this plan goes bad)

Per spec §14:

1. **Revert the branch:** branch is `feature/asama-2-step-2-healthz`; merge target is master. `git revert <merge-commit>` on master, redeploy. Docker compose `healthcheck:` stanza falls back to "always 200 from old endpoint" but the file is gone — actually, after revert, the old `/healthz` in `backend/main.py` returns. No data risk.

2. **Disable healthz check via Docker compose:** comment out the `healthcheck:` stanza and redeploy. Bot reverts to "always-restart-on-crash" without health awareness. State file `state/runtime.json` keeps accumulating but is ignored.

3. **Per-task rollback:** each task is its own commit; `git revert <hash>` for any single task that proves problematic.

---

## Acceptance for Step 2

Step 2 is **DONE** when:
- All Task 1-7 checkboxes are checked
- All tests pass (count = baseline + exactly 24 new, per Step 0.3 breakdown)
- Smoke run produces `/healthz` 503 when bot is idle (no ticks), 200 once first cycle completes
- `state/runtime.json` is created on disk after first cycle and contains the expected schema
- `state/` is in `.gitignore` (verified Step 0.4)
- Branch is pushed and tagged `asama-2-step-2-complete`
- Owner reviews + approves before promoting to master and Hetzner

After acceptance → write the Step 3 plan (Docker compose healthcheck tuning + restart policies).
