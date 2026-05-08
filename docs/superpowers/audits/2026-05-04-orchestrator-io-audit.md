# SafeOrchestrator I/O Surface Audit

**Date:** 2026-05-04
**Branch:** feature/backtest-subsystem
**Spec:** `docs/superpowers/specs/2026-05-04-backtest-design.md` §6.1
**Purpose:** Inventory every I/O / clock / network call reachable from `SafeOrchestrator.run_cycle` and decide how each is gated for backtest purity.

---

## Audit method

```powershell
$paths = @(
  "engine/safe_orchestrator.py",
  "engine/safety/__init__.py",
  "engine/safety/guard.py",
  "engine/notifications/__init__.py"
)
foreach ($p in $paths) {
  Select-String -Path $p `
    -Pattern "open\(|requests\.|time\.time|datetime\.now|datetime\.utcnow|logging\.getLogger|json\.dump|\.write_text|\.write_bytes|validate_kline_freshness"
}
```

Audited dependency tree of `SafeOrchestrator.run_cycle`:
- `engine/safe_orchestrator.py`
- `engine/safety/__init__.py` → `guard.py`, `breaker.py`, `position_guard.py`, `state.py`
- `engine/notifications/__init__.py` (`NotificationManager`)
- `engine/intent.py`, `engine/scenarios.py` (analysis only — pure functions, no I/O)
- `engine/risk/` (sizing — pure)

---

## Findings

| # | Location | Type | Backtest treatment |
|---|----------|------|--------------------|
| 1 | `safe_orchestrator.py:33` `logging.getLogger("efloud.safe_orch")` | log handler | **Leave** — handlers are optional, no-op when not configured. Backtest can attach a captured handler if needed. |
| 2 | `safe_orchestrator.py:128` `StateStore(state_dir)` constructor | disk path | **Inert** — constructor only stores path; no I/O until save/load. Safe with `persist=False`. |
| 3 | `safe_orchestrator.py:143` `_restore_state()` (called from `__init__`) | disk read | **Acceptable** — reads only if files exist. Backtest uses fresh `tmp_path` ⇒ misses ⇒ no-op. With pyfakefs, fake dir is empty and reads return None safely. Verify no exceptions. |
| 4 | `safe_orchestrator.py:164-181` `_persist_state()` | disk write | **Gate via `persist` flag** (Task 1.4). Top of method: `if not self.persist: return`. |
| 5 | `safe_orchestrator.py:202` `validate_kline_freshness(df, tfname, ...)` | clock | **Gate via `freshness_check` flag** (Task 1.3). Wrap call: `if self.freshness_check: validate_kline_freshness(...)`. |
| 6 | `safe_orchestrator.py:336-337` `import time as _time; now_ts = _time.time()` (signal dedup) | clock | **NOT YET GATED — flagged for Phase 3 engine work.** Wall-clock dedup over 1h is incorrect in backtest (would batch all bars). Engine must inject `current_ts` per bar OR clear dedup cache between bars. |
| 7 | `safe_orchestrator.py:359-366` `self.notification_mgr.signal_readonly(...)` (and similar at lines for position open/close, alerts) | network/log | **Inject `NullNotificationManager`** (Task 1.5). All `notify_*` calls become no-ops via `__getattr__`. |
| 8 | `safety/guard.py:83` `now = time.time()` inside `validate_kline_freshness` | clock | **Gated transitively** by Task 1.3 — never called when `freshness_check=False`. |
| 9 | `safety/guard.py:133-136` `datetime.utcnow()` / `datetime.now(timezone.utc)` | clock | **Inside helpers used by freshness validation** — gated transitively. Verify no other call sites in audit grep. |
| 10 | `safety/breaker.py` `time.time()` if any | clock | None found in grep. Breaker uses balance-based state, no wall clock. ✅ |
| 11 | `safety/position_guard.py` | logic-only | Pure (boundary checks). ✅ |
| 12 | `notifications/__init__.py:18` `from datetime import datetime` (unused at module scope; only imported) | clock | Not invoked in NullManager path. Leave. |

---

## Module-globals monkey-patch in legacy runner (to be removed)

`backtest/runner.py:298-313` currently does:

```python
import engine.safe_orchestrator
engine.safe_orchestrator.validate_kline_freshness = lambda *a, **kw: None
```

This is brittle (silent failure if module path changes) and is the exact thing the new `freshness_check=False` flag replaces. **Action:** removed when legacy `backtest/runner.py` is deleted in Chunk 4.

---

## Network / HTTP audit

`grep "requests\." engine/` → no matches reachable from `run_cycle`. CCXT-based exchange calls live in `exchange/` and are passed in via `order_manager` (already injectable, can be `None` in backtest).

`grep "socket" engine/` → no matches.

**Conclusion:** `SafeOrchestrator.run_cycle` does not perform network I/O directly. The network surface is entirely in `exchange/` (out of scope for engine purity).

---

## Outstanding concern (deferred to Phase 3)

**Signal dedup wall clock (Finding #6):** In live mode, the same signal repeats every cycle (~30s) and dedup uses wall-clock `time.time()` to skip re-opens within 1h. In backtest:

- Each bar triggers `run_cycle` → wall-clock advances trivially (microseconds) → all signals within a 1h backtest window get deduped to the first occurrence on the first iteration → subsequent bars never trigger.
- **Fix in Phase 3:** Engine driver passes the bar timestamp (`current_ts: float`) to `run_cycle`. Inside `run_cycle`, replace `_time.time()` with `current_ts` (parameter-injected). Plan Task 3.x will surface this; cited here so Phase 1 reviewer understands why we are not gating it now.

---

## Verification

After Phase 1 tasks 1.3-1.6 land:
- `pytest backend/tests/test_safe_orchestrator_flags.py` — flags work
- `pytest backend/tests/test_engine_purity.py` — pyfakefs + blocked sockets show no leak
- `grep -n "validate_kline_freshness" engine/` confirms a single call site, gated

**Sign-off:** I/O surface is fully accounted for. Findings #1-5 + #7 are addressed by Phase 1 plan tasks. Finding #6 is documented and assigned to Phase 3.
