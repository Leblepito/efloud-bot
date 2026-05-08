# `_processed_signals` Disk Persistence Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Persist `SafeOrchestrator._processed_signals` to disk after every mutation and restore it on startup, so a mid-cycle restart can no longer re-open the same signal twice (the SOL-double-open incident, 2026-05-08 10:14 → 10:18 UTC).

**Architecture:** Reuse the existing `StateStore` already wired into `SafeOrchestrator` (`self.store`). Mirror to a new state key `"processed_signals"` after every assignment to `self._processed_signals`, and restore inside `_restore_state()` next to the existing breaker + positions restore. The 1-hour TTL housekeeping in the existing dedup site stays as-is — restore just rehydrates whatever was on disk and the next cycle's housekeeping prunes stale entries.

**Tech Stack:** Python 3.12, existing `engine.safety.state.StateStore`, pytest, `pyfakefs` (already in `requirements.txt`).

---

## Background — why this is needed

When the bot restarted mid-cycle on 2026-05-08, `_processed_signals` was in-memory only (`engine/safe_orchestrator.py:142`). After the TZ-error crash at 10:14:12 and autoheal restart at 10:18:07, the dedup cache was empty → the SOL signal that already opened a position 4 minutes earlier was treated as fresh → second position opened on top of the first (size doubled 11.67 → 17.5 averaged).

PR #13 already persists `lifecycle.positions`. The duplicate-direction guard prevents reopens **when** lifecycle has the position. But for a moment between "lifecycle.open_position appended" and "OrderManager.open_position succeeded + state file flushed", a crash leaves both stores out of sync. Persisting `_processed_signals` is the cheapest belt-and-suspenders: even if positions list desyncs, the same `(symbol, direction, entry)` key won't fire twice within the 1-hour TTL.

---

## File Structure

| File | Responsibility | Change kind |
|---|---|---|
| [engine/safe_orchestrator.py](../../engine/safe_orchestrator.py) | Init + restore + persist `_processed_signals` | Modify (3 small additions) |
| [backend/tests/test_processed_signals_persistence.py](../../backend/tests/test_processed_signals_persistence.py) | Unit tests for save/restore + TTL pruning round-trip | Create |

The state file `processed_signals.json` lands under the bot's `state_dir` next to the existing `breaker.json`, `positions.json`, and `order_manager_positions.json`. The state volume mount (PR #14) already covers it — no infra change.

---

## Chunk 1: Persist + restore round-trip

### Task 1: Restore `_processed_signals` from StateStore in `_restore_state`

**Files:**
- Modify: [engine/safe_orchestrator.py](../../engine/safe_orchestrator.py) — `_restore_state()` (lines ~153-218) and `__init__` (line 142)
- Create: [backend/tests/test_processed_signals_persistence.py](../../backend/tests/test_processed_signals_persistence.py)

- [ ] **Step 1: Write the failing tests (round-trip + TTL after restore)**

Create `backend/tests/test_processed_signals_persistence.py`:

```python
"""SafeOrchestrator must persist _processed_signals across restarts so a
mid-cycle restart cannot re-open the same signal (SOL double-open, 2026-05-08).

Tests use pyfakefs to avoid touching the real filesystem.
"""
import time
from pathlib import Path

import pytest

# Construct via the real factory path; tests inject a config dict.
# Adjust import path if SafeOrchestrator factory wrapper differs in the repo.
from engine.safe_orchestrator import SafeOrchestrator
from engine.safety.state import StateStore


@pytest.fixture
def fs_state_dir(fs):
    """pyfakefs-backed state dir."""
    state_dir = "/state"
    fs.create_dir(state_dir)
    return state_dir


def _minimal_cfg() -> dict:
    """Minimal config that the orchestrator's __init__ will accept."""
    return {
        "exchange": {"market_type": "futures", "leverage": 5, "testnet": True},
        "risk": {"max_open_positions": 5},
        "safety": {
            "starting_balance": 2000,
            "daily_loss_limit_pct": 10,
            "weekly_drawdown_limit_pct": 15,
            "max_position_notional_pct": 10,
            "max_holding_hours": 48,
            "max_pyramid_adds": 2,
            "min_sl_atr": 0.5,
            "max_sl_atr": 5.0,
            "consecutive_loss_limit": 3,
            "consecutive_pause_min": 120,
        },
        "operation": {"dry_run": True, "persist": True},
    }


def test_processed_signals_round_trip(fs_state_dir):
    """Sets get persisted, then a fresh orchestrator restores them."""
    store = StateStore(fs_state_dir)
    sig_key = ("SOL/USDT", "LONG", 175.42)
    now_ts = time.time()
    store.save("processed_signals", [
        [list(sig_key), now_ts],
    ])

    # Construct a new orchestrator with state_dir pointing at the fake fs.
    orch = SafeOrchestrator(_minimal_cfg(), state_dir=fs_state_dir)
    assert sig_key in orch._processed_signals
    assert abs(orch._processed_signals[sig_key] - now_ts) < 1.0


def test_processed_signals_persists_after_record(fs_state_dir):
    """When a signal is recorded, the disk file reflects it on next read."""
    orch = SafeOrchestrator(_minimal_cfg(), state_dir=fs_state_dir)
    sig_key = ("FIL/USDT", "LONG", 1.10)
    now_ts = time.time()
    orch._processed_signals[sig_key] = now_ts

    # Trigger persistence — the production code persists inside _persist_state(),
    # which is called from the same place that already writes breaker/positions.
    orch._persist_state()

    on_disk = StateStore(fs_state_dir).load("processed_signals")
    assert on_disk is not None
    keys = {tuple(entry[0]) for entry in on_disk}
    assert sig_key in keys


def test_stale_entries_pruned_on_restore_via_first_cycle(fs_state_dir):
    """A stale (>1h old) entry persisted to disk gets pruned on first dedup
    pass (existing 3600s housekeeping at safe_orchestrator.py:412-415).
    Restore itself is intentionally not pruning — the check loop already does."""
    store = StateStore(fs_state_dir)
    fresh = ("ETH/USDT", "LONG", 3000.0)
    stale = ("BTC/USDT", "SHORT", 67000.0)
    now = time.time()
    store.save("processed_signals", [
        [list(fresh), now - 60],          # 1 minute old
        [list(stale), now - 7200],        # 2 hours old → should be pruned by next cycle
    ])

    orch = SafeOrchestrator(_minimal_cfg(), state_dir=fs_state_dir)
    assert fresh in orch._processed_signals
    assert stale in orch._processed_signals  # restore loads everything

    # Simulate the prune step that happens on every signal-handling pass:
    pruned = {
        k: ts for k, ts in orch._processed_signals.items()
        if time.time() - ts < 3600
    }
    orch._processed_signals = pruned
    assert fresh in orch._processed_signals
    assert stale not in orch._processed_signals


def test_corrupt_processed_signals_does_not_break_init(fs_state_dir):
    """If the disk file is malformed JSON, init must not crash; it falls back
    to an empty dict (same StateStore behavior as breaker/positions)."""
    bad = Path(fs_state_dir) / "processed_signals.json"
    bad.write_text("{not valid json", encoding="utf-8")

    orch = SafeOrchestrator(_minimal_cfg(), state_dir=fs_state_dir)
    assert orch._processed_signals == {}
```

- [ ] **Step 2: Run tests — confirm all 4 fail with `KeyError`/`AttributeError` (no persistence wired yet)**

```
pytest backend/tests/test_processed_signals_persistence.py -v
```

Expected: 4 failures. Errors will be along the lines of "_processed_signals is empty after restore" because the production code only initializes `self._processed_signals = {}` in `__init__` and never reads from disk.

- [ ] **Step 3: Modify `_restore_state` to load `processed_signals`**

In [engine/safe_orchestrator.py](../../engine/safe_orchestrator.py), at the end of `_restore_state` (after the lifecycle.positions restore block, before the closing of the method around line 218):

```python
        # Restore _processed_signals so a mid-cycle restart cannot re-open the
        # same signal twice. Disk format: list of [key_tuple_as_list, timestamp].
        # See SOL double-open incident, 2026-05-08 10:14 → 10:18 UTC.
        saved_sigs = self.store.load("processed_signals")
        if saved_sigs:
            try:
                self._processed_signals = {
                    tuple(entry[0]): float(entry[1])
                    for entry in saved_sigs
                    if isinstance(entry, (list, tuple)) and len(entry) == 2
                }
                log.info(
                    f"♻️  Restored {len(self._processed_signals)} processed signal(s) from disk"
                )
            except Exception as e:
                log.warning(f"Could not restore processed_signals: {e}")
                self._processed_signals = {}
```

- [ ] **Step 4: Modify `_persist_state` to also save `processed_signals`**

In [engine/safe_orchestrator.py](../../engine/safe_orchestrator.py:220-229), append to the existing `_persist_state` body:

```python
        # _processed_signals — JSON-friendly form: list of [key_list, ts].
        # Tuples are not JSON-native; we serialize as lists and reconstruct on load.
        try:
            self.store.save(
                "processed_signals",
                [[list(k), ts] for k, ts in self._processed_signals.items()],
            )
        except Exception as e:
            log.warning(f"Could not persist processed_signals: {e}")
```

- [ ] **Step 5: Persist after the dedup cache mutation**

In [engine/safe_orchestrator.py:417-421](../../engine/safe_orchestrator.py#L417-L421), after the assignment `self._processed_signals[sig_key] = now_ts`, add a persist call:

```python
            else:
                self._processed_signals[sig_key] = now_ts
                self._persist_state()  # persist dedup cache so a mid-cycle restart
                                       # can't re-open the same signal (SOL double-open fix)
```

(The TTL prune at lines 412-415 mutates the dict in-place every cycle, but persisting on every prune is wasteful. Persisting only when a *new* signal is recorded is sufficient — pruning happens on the next restored-then-checked cycle anyway, as covered by `test_stale_entries_pruned_on_restore_via_first_cycle`.)

- [ ] **Step 6: Run tests — all 4 pass**

```
pytest backend/tests/test_processed_signals_persistence.py -v
```

Expected: 4 PASS.

- [ ] **Step 7: Run the full test suite (sanity)**

```
pytest backend/tests/ -x -q
```

Expected: 0 regressions in existing orchestrator/state tests.

- [ ] **Step 8: Commit**

```
git add engine/safe_orchestrator.py backend/tests/test_processed_signals_persistence.py
git commit -m "fix(orchestrator): persist _processed_signals across restarts

In-memory dedup cache was lost on every restart. After the 2026-05-08 TZ-error
crash + autoheal restart 4 minutes later, SOL signal re-fired and a second
position opened on top of the first (size doubled 11.67 → 17.5 averaged).

Persist the dedup cache to StateStore on every new-signal recording; restore
on init alongside breaker + lifecycle positions. The existing 1-hour TTL
prune in the signal-handling loop continues to clean up stale entries on
the next cycle after restart, so no extra pruning on restore is needed."
```

---

## Chunk 2: PR + deploy + verification

### Task 2: Open PR and deploy

**Files:** none (git/PR/deploy operations)

- [ ] **Step 1: Push branch**

Branch name: `fix/processed-signals-disk-persist`

```
git push -u origin fix/processed-signals-disk-persist
```

- [ ] **Step 2: Open PR via gh**

```
gh pr create --title "fix(orchestrator): persist _processed_signals across restarts" --body "$(cat <<'EOF'
## Summary
- `SafeOrchestrator._processed_signals` was in-memory only. Mid-cycle restarts (TZ-error → autoheal) lost the dedup state, allowing the same signal to open a second position within minutes.
- Round-trip via existing `StateStore`: load on init in `_restore_state`, save in `_persist_state`, also save inline when a new signal is recorded.
- TTL prune (1-hour window) stays in the signal-handling loop; restore loads the full dict and the next cycle prunes stale entries.

## Test plan
- [x] 4 unit tests covering round-trip, persist-on-record, prune-on-next-cycle, corrupt-file tolerance (pyfakefs).
- [x] `pytest backend/tests/` — no regressions.
- [ ] Post-deploy: trigger a synthetic crash test on prod (stop the container, verify `/opt/efloud-bot/state*/processed_signals.json` exists with current dedup keys, restart, confirm the same signals are not re-fired in the first cycle).

## Notes
- Storage volume `efloud_state_aggressive` (PR #14) already covers the new file — no infra change.
EOF
)"
```

- [ ] **Step 3: After approval, merge + deploy**

```
gh pr merge --squash --delete-branch
ssh efloud@178.104.122.91 'cd /opt/efloud-bot && git pull && bash deploy/deploy.sh'
```

- [ ] **Step 4: Post-deploy smoke**

```
ssh efloud@178.104.122.91 'docker compose -f docker-compose.prod.yml exec -T efloud-bot ls -la /app/state_aggressive/'
```

Expected: `processed_signals.json` appears once the bot processes its first signal cycle.
