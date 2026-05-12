# PR-B Implementer Prompt — SL Logic v2

**Date:** 2026-05-12
**Status:** Gated. **Do not execute** until activation criteria below are met.
**Owners:** Utku (decision), Claude (architect), Hermes (implementer).
**Reads with:** [sl-logic-spec-v2.md](./2026-05-12-pr-b-sl-logic-spec-v2.md).

---

## 0. Activation criteria (ALL must hold before starting)

This prompt is **inactive** until all three:

1. [Phase 0 PR](./2026-05-12-pr-b-phase0-script-spec.md) (PR #48) is **merged to master**.
2. Production `trade_journal.jsonl` has been confirmed to populate
   (`journal_rows > 0` on a fresh Phase 0 run), OR Utku has explicitly waived
   journal requirement for an **interim H2 verdict** (in which case PR-B
   merges with `warn_only=true` only — Gate 3/4 blocked until journal lands).
3. Utku has written the **exact string** "H2 dominant, GO PR-B" (or
   "Interim H2, GO PR-B warn-only") in chat or PR thread.

If any of the three is missing → STOP. Do not branch, do not write code,
do not even open the spec for "preparation." Respond with:

```
PR-B implementer prompt is gated.

Missing activation criteria:
- <list of unmet criteria>

Standing by.
```

---

## 1. Mission

Implement the SL price logic rework described in
[sl-logic-spec-v2.md](./2026-05-12-pr-b-sl-logic-spec-v2.md).

The rule swaps the strategy's stop-loss anchor from "last swing low/high
before the break candle" to "break candle range + ATR fallback." Default-OFF.
Live behavior changes only when the triple AND-gate is set.

Production impact on merge: **NONE.** PR-B introduces dead code paths behind
`enabled=false`. Live behavior changes happen via config + env flip, governed
by Gates 1-4.

---

## 2. Branch + PR shape

- Branch: `feature/sl-logic-v2` from latest `master`.
- Atomic PR. No mixing with:
  - PR-C / Issue #46 (accounting).
  - Any config rebalance.
  - Any breaker reset work.
  - Any orphan-protection follow-up.
- Single PR description references the v2 spec and the Phase 0 verdict that
  unlocked this work.

---

## 3. Implementation order (TDD, hard discipline)

### Stage 1 — RED (no production code yet)

1. Write all **17 tests** per spec §3 in three files:
   - `tests/test_sl_logic.py` — 10 unit tests.
   - `tests/test_signals.py` — 4 integration tests + 1 backwards-compat regression.
   - `tests/test_backtest_determinism.py` — 1 determinism test (or extend the
     existing backtest test module).

2. Run: `pytest tests/test_sl_logic.py tests/test_signals.py tests/test_backtest_determinism.py -v`

3. Expected: 17 RED. **Do not start Stage 2 until all 17 are RED for the
   right reasons** (missing `engine.sl_logic` module, missing flag handling).
   A test failing because of a syntax error in the test itself is not a
   legitimate RED.

4. Commit message: `test(sl-logic): 17 RED tests covering v2 SL rule (TDD step 1)`

### Stage 2 — GREEN (pure unit tests)

5. Create `engine/sl_logic.py` with `SLLogicParams`, `SLResult`, `compute_sl`
   per spec §2.6.

6. Implement the SL price rule per spec §2.1. Make unit tests 1-10 pass.

7. Run: `pytest tests/test_sl_logic.py -v` → 10 PASS.

8. Commit: `feat(sl-logic): pure compute_sl engine with structural + ATR fallback`

### Stage 3 — GREEN (integration in `generate_signals`)

9. Modify `engine/signals.py` to call `compute_sl` when the triple gate is
   set. Implement spec §2.3 gate semantics:
   - All three gates true → use v2 SL.
   - `enabled=true` AND `warn_only=true` → compute v2 SL, log both, use legacy.
   - Otherwise → legacy code path (byte-identical to current behavior).

10. Implement spec §2.4 immediate-trigger rejection.

11. Run: `pytest tests/test_signals.py -v` → 14 PASS (4 new + 10+ existing).

12. Run full suite: `pytest tests/ backend/tests/ -q` → 0 regressions.

13. Commit: `feat(signals): integrate v2 SL with triple AND-gate (default-off)`

### Stage 4 — GREEN (backtest determinism)

14. Confirm `backtest/engine.py` already enforces alphabetical symbol order.
    If not, that is a separate PR — surface and stop.

15. Run determinism test: `pytest tests/test_backtest_determinism.py -v` → PASS.

16. Commit: `test(backtest): determinism guard for sl_logic_v2 enabled path`

### Stage 5 — Config schema

17. Update `configs/config.aggressive_v1.yaml` (and `config.testnet.yaml` if
    present) with a `risk.sl_logic` block. All values at defaults from spec §2.2:
    ```yaml
    risk:
      sl_logic:
        enabled: false
        bos_range_lookback: 3
        atr_period: 14
        atr_fallback_mult: 1.0
        min_ticks_above_entry: 3
        warn_only: true
    ```

18. Confirm test 16 (`test_aggressive_v1_config_loads_without_sl_logic_block`)
    still passes — existing configs **without** the block load with
    `enabled=false`. This is non-negotiable.

19. Commit: `config(sl-logic): add risk.sl_logic block with safe defaults`

### Stage 6 — Verification

20. `git grep -nE "from engine.sl_logic" engine/` → at least one match in
    `engine/signals.py`. No matches anywhere else in production code.

21. `git grep -n "enabled.*true" configs/` for any sl_logic block → empty.
    Default-OFF must hold across all committed configs.

22. Full suite: `pytest tests/ backend/tests/ -q` — clean, 17 new tests PASS.

23. Run a single backtest replay locally with `enabled=false` (Run A from
    spec Gate 2) to confirm byte-identical output vs master. If it differs,
    the legacy path was disturbed; **stop and investigate** before opening PR.

### Stage 7 — PR

24. Push branch, open PR with the description template in §6 of this prompt.

25. Trigger `efloud-risk-ops-reviewer` agent for review — spec touches
    `engine/safety/`-adjacent and risk config files.

26. Stand by for review. **Do not deploy.** Gates 2-4 are post-merge work.

---

## 4. Out-of-scope reminders (will tempt you)

Cross out the temptation, ship the PR.

| Temptation | Reality |
|---|---|
| "While I'm here, fix the FIL accounting bug." | PR-C / Issue #46. Separate. |
| "The aggressive config could use a tighter confluence floor." | Strategy iteration. Not PR-B. |
| "Position guard's `max_sl_atr` upper bound should also widen." | Out of scope. PR-B sits upstream of guard. |
| "Universe filtering would help OP/FIL." | Utku ruled this out. Not negotiable. |
| "Let me also clean up the old `# SL / TP` comment block." | Atomic PR. Defer cleanups. |
| "Breaker reset should ride along with this." | Independent Utku decision. |
| "Run on testnet to verify before merge." | Gate 3. Post-merge. |
| "The new SL should also feed TP recalculation." | TP is a separate decision; this PR does NOT change TP placement logic. |

---

## 5. Hard nos

- ❌ No production deploy. Merge is allowed (after review); deploy is Utku's call.
- ❌ No order/cancel/close/breaker touch.
- ❌ No `EFLOUD_ALLOW_SL_LOGIC_V2=1` in committed files or examples.
- ❌ No `enabled: true` in any committed config.
- ❌ No `warn_only: false` in any committed config.
- ❌ No edits to `engine/safety/breaker.py`, `engine/safety/position_guard.py`,
  `engine/safety/mainnet_guard.py`, or `exchange/__init__.py`.
- ❌ No new network calls — `compute_sl` is pure; `generate_signals` already
  has the precision data it needs.
- ❌ No silent fallback. If `compute_sl` raises, the signal is rejected with
  a structured WARNING, not patched over with the legacy path.

---

## 6. PR description template

```
feat(sl-logic): v2 SL price rule — CHoCH/BoS break-range + ATR fallback (default-OFF)

Implements PR-B v2 per docs/superpowers/specs/2026-05-12-pr-b-sl-logic-spec-v2.md.

What it does:
- New `engine/sl_logic.py` exposes pure `compute_sl(...)`.
- `engine/signals.py` calls `compute_sl` when the triple AND-gate is set:
    risk.sl_logic.enabled=true  AND  warn_only=false  AND  EFLOUD_ALLOW_SL_LOGIC_V2=1
- All three gates false on merge. Live behavior is unchanged.
- `warn_only=true` mode computes new SL and logs both, but uses legacy SL.

What it does not do:
- No deploy. No config flip. No env var set.
- No change to position_guard, breaker, mainnet guard, or exchange layer.
- No TP recalculation. No order/cancel/close.

Tests:
- 17 new tests (10 unit, 4 integration, 2 regression, 1 backtest determinism).
- 0 regressions on existing suite.

Gating:
- Phase 0 evidence PR #48 merged: YES.
- Utku verdict "H2 dominant, GO PR-B" recorded: YES — <link to message>.
- journal_rows > 0 in latest Phase 0 run: YES / WAIVED (interim H2).

Next steps (post-merge, Utku approval required for each gate):
- Gate 2: backtest replay (A/B/C). Artifact: docs/validation/2026-05-pr-b/backtest-replay.md.
- Gate 3: paper run 48-72h with EFLOUD_ALLOW_SL_LOGIC_V2=1, warn_only=false, dry_run=true.
- Gate 4: live activation with halved exposure for 10 trades.
```

---

## 7. Self-review checklist before requesting human review

Before tagging Utku or running the risk-ops-reviewer, confirm:

- [ ] All 17 tests written before any production code (`git log` shows the
      RED commit before the GREEN ones).
- [ ] Triple AND-gate enforced in `engine/signals.py`. Confirmed by reading
      the diff, not by assuming.
- [ ] Default-OFF holds: `enabled=false` in every committed config.
- [ ] `warn_only=true` default in committed configs (free in-production
      observation channel preserved).
- [ ] No imports of `engine.sl_logic` outside `engine/signals.py` (or the
      test files).
- [ ] No new network calls. `BinanceClient` not imported in `engine.sl_logic`.
- [ ] `compute_sl` raises on bad input (negative entry, NaN ATR), and the
      caller rejects the signal rather than silently falling back.
- [ ] Existing 60+ signal tests pass byte-identical with `enabled=false`.
- [ ] Backtest replay with `enabled=false` produces byte-identical
      `result.json` vs master HEAD.
- [ ] No file under `engine/safety/` was touched.

If any box is unchecked → fix before review.

---

## 8. Status reporting

Use this template for each stage transition:

```
PR-B Stage <N> complete.
- Files changed: <list>
- Tests added/passing: <count>
- Regressions: 0
- Commit SHA: <short>
- Next stage: <N+1>
```

When PR is opened:

```
PR-B PR opened: <URL>
- Branch: feature/sl-logic-v2
- All 17 tests PASS, 0 regressions on full suite.
- Default-OFF verified across committed configs.
- Triple AND-gate verified in engine/signals.py.
- efloud-risk-ops-reviewer requested.

Standing by. No deploy. Gates 2-4 pending Utku.
```

If blocked at any stage:

```
BLOCKED on PR-B Stage <N>.
- What I tried: <description>
- What blocked me: <description>
- What I need: <decision from Utku / clarification from architect / etc.>
```

---

## 9. After merge — Hermes hands off, not implements

Gates 2-4 are operational work, not implementation. After PR-B merges:

- **Gate 2 (backtest replay):** Hermes runs the three-way backtest, writes
  the artifact, surfaces the verdict to Utku. No code change required.
- **Gate 3 (paper run):** Utku deploys (Hermes assists). Bot runs with v2 SL
  computed but legacy used (warn_only=false in dry_run). Hermes monitors
  structured logs, writes the artifact, surfaces to Utku.
- **Gate 4 (live activation):** Utku decides. Hermes assists with the config
  flip + halved exposure cap. No code change required.

If any gate fails its acceptance criteria, **stop and surface**. Do not
re-tune parameters silently. Parameter changes are a config-only PR with
its own review, citing which gate told us to retune.

---

## 10. Closing

You are not the analyst. You are the implementer. The spec is the spec.
The triple AND-gate is the triple AND-gate. The defaults are the defaults.

If something in the spec turns out to be impossible or contradictory in
implementation, **stop and surface to Claude (architect) before patching the
spec on the fly**. Spec drift in flight is how subtle behavioral bugs ship.

Ship the code. Not opinions.
