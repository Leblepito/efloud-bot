# PR-B v2 (Issue #45) — SL Price Logic: CHoCH/BoS Break-Range + ATR Fallback

**Date:** 2026-05-12
**Status:** Canonical — supersedes [v1](./2026-05-12-pr-b-sl-logic-spec.md)
**Owners:** Utku (decision), Claude (spec/architect), Hermes (implementation)
**Production impact:** Default-OFF on merge. Validation-gated activation.
**Hard prerequisite:** [Phase 0 evidence PR](./2026-05-12-pr-b-phase0-script-spec.md) merged
and Utku verdict "H2 dominant, GO PR-B".

Applied project skills:
- `efloud-trading-risk-checklist` — risk-sensitive: changes SL price on every new entry.
- `efloud-bugfix-workflow` — behavior change, test-first.
- `efloud-deploy-safety` — default-off + multi-gate activation.
- `superpowers:brainstorming` — see [brainstorming notes](./2026-05-12-pr-b-brainstorming-notes.md).
- `superpowers:test-driven-development` — 17 tests RED first, then GREEN.
- `superpowers:verification-before-completion` — every gate produces a written artifact.

---

## 0. What changed from v1

v2 is a tightening, not a rewrite. The intent and the SL rule are unchanged.

| Aspect | v1 | v2 |
|---|---|---|
| Phase 0 evidence | Recommended in §6 | **Hard precondition.** Separate PR, separate spec. |
| Implementer instructions | Embedded in §6 | Extracted into [implementer-prompt.md](./2026-05-12-pr-b-implementer-prompt.md). |
| Activation gates | Listed in §2.5 | Codified as triple AND-gate; matches `EFLOUD_ALLOW_MAINNET` precedent. |
| Journal availability | Assumed populated | **Assumed possibly empty.** §1.5 adds a journal investigation track before verdict. |
| Backwards compatibility | Implied | Test 16 enforces; cannot drift. |
| Deploy ordering | Open question | Settled: PR-A (PR #47/#42) deploys independently; PR-B sequenced after Phase 0. |

If v1 and v2 disagree, v2 wins. v1 is retained only for the audit trail.

---

## 1. Prerequisite — Phase 0 evidence

### 1.1 What Phase 0 produces

`scripts/extract_sl_evidence.py` (PR #48) emits:
- CSV: one row per closed trade in the window. 26 columns (see
  [phase0-script-spec §3.1](./2026-05-12-pr-b-phase0-script-spec.md)).
- Summary markdown: per-symbol aggregates + H1/H2/H3/H4 indicator sections + empty
  decision matrix for Utku to fill.

### 1.2 What Utku decides

Utku reads CSV + summary and writes one of four verdicts in chat:

| Verdict | Effect |
|---|---|
| "H2 dominant, GO PR-B" | PR-B implementation activates per this spec. |
| "H1 dominant" | PR-B parks. PR #47/#42 deploy/observation work continues. |
| "H3 dominant" | PR-B parks. Strategy iteration workstream activates separately. |
| "H4 dominant" | PR-B parks. PR-C / Issue #46 (accounting) activates. |
| "Need more data" | Extend Phase 0 window or add metrics; re-run. |

Utku owns the verdict. The script does not vote. Claude (architect) may help
interpret on request but does not vote.

### 1.3 Gating on Phase 0 evidence

PR-B implementation **does not start** until:
1. PR #48 is merged to master.
2. Phase 0 has been run with `journal_rows > 0` (see §1.5).
3. Utku has written "H2 dominant, GO PR-B" verbatim.

The implementer prompt is the trigger; until those three conditions hold it is
inactive.

### 1.4 What "H2 dominant" means quantitatively

Utku owns the threshold but the spec recommends:
- For OP+FIL losers, **median `sl_atr_ratio` < 0.8** (SL closer than 0.8× ATR
  to entry — the audit scorer's "too tight" band).
- **AND** median `mae_pct` for those losers within 1.2× of `sl_distance_pct`
  (market did not run far past the SL — it kissed the SL distance and turned).

These two together say: "the strategy chose an SL that was on the wrong side
of normal noise." That is the H2 picture. If only one of the two holds, Utku
may still call H2 dominant but the verdict should note "partial H2."

### 1.5 Journal investigation amendment (new in v2)

**Problem confirmed 2026-05-12:** PR #48 smoke test on production showed
`journal_rows=0`. MAE/MFE per closed trade is therefore not extractable today.
This was missed by v1.

**Mandatory before H2 verdict:**
1. Investigate root cause (mount mismatch, path config, lifecycle integration
   gap — see [hermes-handoff-consolidated.md](../../../) Task C).
2. Land a `fix/production-trade-journal` PR. Read-only investigation phase;
   no production writes during investigation.
3. Deploy fix; allow 2–3 days of operation so new closed trades populate
   `trade_journal.jsonl`.
4. Re-run Phase 0; require `journal_rows > 0` before any H1↔H2 separation.

Until journal data is populated, Utku may issue an **interim verdict** based
on `sl_score`, `sl_atr_ratio`, and audit-only signals. An interim verdict
may set `warn_only=true` only — never `warn_only=false`. The implementer
prompt enforces this.

---

## 2. PR-B acceptance criteria

### 2.1 SL price rule

For a signal triggered by a CHoCH or BoS break at bar index `brk.idx`:

**LONG (BULL break):**
- `SL_structural = min(low[brk.idx - bos_range_lookback : brk.idx + 1])`
  — the lowest low over the `bos_range_lookback` bars ending at and including
  the break candle.

**SHORT (BEAR break):**
- `SL_structural = max(high[brk.idx - bos_range_lookback : brk.idx + 1])`
  — the highest high over the same window.

**ATR fallback** (applies in both directions):
- Let `atr14 = ATR(period=atr_period)` computed on the entry-TF series up to
  and including `brk.idx`.
- Let `min_sl_distance = max(atr_fallback_mult × atr14, tick_size × min_ticks_above_entry)`.
- If `|entry_price − SL_structural| < min_sl_distance`, use the ATR fallback:
  - LONG: `SL = entry_price − min_sl_distance`
  - SHORT: `SL = entry_price + min_sl_distance`
- Otherwise: `SL = SL_structural`.

**Final tick / precision normalization:**
- Round SL **away from entry**: LONG floor-to-tick; SHORT ceil-to-tick.
- After rounding, re-check the immediate-trigger guard:
  `|entry_price − SL| ≥ tick_size × min_ticks_above_entry`.
- If violated, widen by one tick.

### 2.2 Parameters — all under `risk.sl_logic.*`

| Param | Default | Range | Comment |
|---|---|---|---|
| `enabled` | **false** | bool | Default-OFF. Config flip required to activate. |
| `bos_range_lookback` | 3 | 1–10 | Inclusive of break candle. 3 ≈ "break candle + 2 prior". |
| `atr_period` | 14 | 7–30 | Standard ATR length for the fallback. |
| `atr_fallback_mult` | 1.0 | 0.5–3.0 | Min SL distance in ATRs. Inside `position_guard.min_sl_atr` band. |
| `min_ticks_above_entry` | 3 | 1–20 | Hard floor against immediate-trigger after rounding. |
| `warn_only` | **true** | bool | When `enabled=true` AND `warn_only=true`, log both SLs but use legacy. |

### 2.3 Triple AND-gate for live behavior

The new SL rule **changes runtime behavior only when all three** hold:

1. `risk.sl_logic.enabled = true` in active config.
2. `risk.sl_logic.warn_only = false` in active config.
3. `EFLOUD_ALLOW_SL_LOGIC_V2=1` env var present.

If any of the three is false → fall back to legacy code path
(`last swing low/high before brk.idx`).

If `enabled=true` AND `warn_only=true` (regardless of env var):
- Compute new SL.
- Log a structured INFO/DEBUG line with `legacy_sl`, `v2_sl`,
  `legacy_distance_pct`, `v2_distance_pct`, `source` (`structural` or
  `atr_fallback`), `atr14`.
- Use **legacy SL** for the actual order.

### 2.4 Immediate-trigger prevention

After SL is computed and rounded:

1. Best bid/ask (or last trade price) must NOT already be on the SL side of
   entry by more than `tick_size × 2`. If it is, the signal is rejected with
   `reject_reason='SL_ALREADY_TRIGGERED'` and a structured WARNING log.
2. `position_guard` check is unchanged: SL distance must satisfy
   `min_sl_atr ≤ |entry−SL|/atr14 ≤ max_sl_atr`. PR-B sits **upstream** of
   `position_guard`.

### 2.5 Tick / precision handling

- All math in `Decimal` or `float`; final SL value normalized through
  `client.normalize_price(symbol, side='SL', direction=position.direction)`.
- `price_precision` lookup must NOT introduce a new network call. Use
  `BinanceClient.markets` cache. In `dry_run` / backtest, fall back to a
  cached precision table loaded at startup.

### 2.6 Public API surface

New module `engine/sl_logic.py`:

```python
@dataclass(frozen=True)
class SLLogicParams:
    enabled: bool = False
    bos_range_lookback: int = 3
    atr_period: int = 14
    atr_fallback_mult: float = 1.0
    min_ticks_above_entry: int = 3
    warn_only: bool = True

@dataclass(frozen=True)
class SLResult:
    price: float
    source: Literal["structural", "atr_fallback", "legacy"]
    distance: float
    atr14: float

def compute_sl(
    direction: Literal["LONG", "SHORT"],
    entry_price: float,
    brk_idx: int,
    df: pd.DataFrame,             # entry-TF OHLCV up to and including brk_idx
    params: SLLogicParams,
    tick_size: float,
    legacy_sl: float,             # passed through when disabled or warn_only
) -> SLResult
```

`generate_signals` in `engine/signals.py` calls `compute_sl` and uses the
returned `price` per §2.3 gate semantics.

---

## 3. Tests required (TDD — RED first, then GREEN)

All test files live under `tests/`. No production-path edit before all 17
tests are RED.

### 3.1 Unit tests — `tests/test_sl_logic.py` (10 tests)

1. `test_long_uses_break_range_low_when_distance_above_atr`
2. `test_short_uses_break_range_high_when_distance_above_atr`
3. `test_long_falls_back_to_atr_when_structural_too_tight`
4. `test_short_falls_back_to_atr_when_structural_too_tight`
5. `test_long_sl_rounded_floor_to_tick`
6. `test_short_sl_rounded_ceil_to_tick`
7. `test_immediate_trigger_widens_by_one_tick`
8. `test_atr_zero_returns_minimum_ticks_distance`
9. `test_lookback_clamped_to_available_history`
10. `test_disabled_returns_legacy_value`

### 3.2 Integration tests — `tests/test_signals.py` (4 tests)

11. `test_signal_uses_v2_sl_when_enabled_and_not_warn_only_and_env`
12. `test_signal_logs_both_sls_when_warn_only`
13. `test_signal_rejected_when_immediate_trigger`
14. `test_position_guard_still_runs_after_v2_sl`

### 3.3 Regression tests (2 tests)

15. `test_legacy_sl_path_unchanged_when_flag_off`
16. `test_aggressive_v1_config_loads_without_sl_logic_block`

### 3.4 Backtest determinism (1 test)

17. `test_backtest_deterministic_with_sl_logic_v2`

### 3.5 Coverage gate

`pytest tests/test_sl_logic.py tests/test_signals.py -v` must show 17 PASS, 0 FAIL.
Full suite (`pytest tests/ backend/tests/ -q`) must show 0 regressions.

---

## 4. Validation gates before live deploy

PR-B is **default-OFF** on merge. Activating it on production requires **all
four** gates to pass in order. Each gate produces an artifact under
`docs/validation/2026-05-pr-b/`.

### Gate 1 — Test suite (CI)

- Command: `python -m pytest tests/ backend/tests/ -q`
- Required: 17 new tests pass, 0 regressions.
- Artifact: CI green check on PR.

### Gate 2 — Backtest replay (7-day live window)

- Command:
  ```
  python -m backtest.cli portfolio \
      --symbols <10-symbol-universe> --period 7d \
      --config configs/config.aggressive_v1.yaml --balance 2900 --sl-logic-v2
  ```
- Three side-by-side runs:
  - **A — Legacy:** `enabled=false` (current code path).
  - **B — V2 warn-only:** `enabled=true, warn_only=true` (logs new SL but uses legacy).
  - **C — V2 active:** `enabled=true, warn_only=false`.
- Required:
  - C net PnL ≥ A net PnL (neutral or better on the 7-day replay).
  - C max drawdown ≤ A max drawdown × 1.15.
  - OP and FIL net PnL improve under C vs A, OR show no statistically
    meaningful change (7-day sample is small).
- Artifact: `docs/validation/2026-05-pr-b/backtest-replay.md` with three
  `result.json` summaries.

**Failure handling:** if C materially worse than A:
- Re-tune parameters: extract per-trade SL distance + MAE from B's warn-only
  logs; pick `atr_fallback_mult` that matches the realized MAE distribution.
- Or: H2 was wrong; escalate to Utku, park PR-B.

### Gate 3 — Paper / dry-run window (48–72h)

- Deploy PR-B to production VPS with `dry_run=true`, `sl_logic.enabled=true`,
  `warn_only=false`, `EFLOUD_ALLOW_SL_LOGIC_V2=1`. Bot generates signals,
  computes new SL, does NOT place orders.
- Required:
  - No `SL_ALREADY_TRIGGERED` storm (< 5% of signals rejected for this reason).
  - No exception/crash in `sl_logic.compute_sl`.
  - Mean `|sl − entry|/atr14` sits in `[1.0, 2.5]` (audit scorer's sweet spot).
  - ≥ 5 distinct symbols produce ≥ 1 signal in the window.
- Artifact: `docs/validation/2026-05-pr-b/paper-run.md` with structured-log
  summary.

### Gate 4 — Breaker reset + live activation

- Bot may be TRIPPED at activation time. **PR-B does not change the breaker
  reset rule.** Breaker reset is a separate Utku decision.
- On reset:
  - Flip `sl_logic.enabled=true`, `warn_only=false`, `EFLOUD_ALLOW_SL_LOGIC_V2=1`.
  - Keep `aggressive_v1` otherwise unchanged.
  - Run 48h with `safety.max_position_notional_pct` capped at **half** of the
    current value, until 10+ closed trades observed under the new SL rule.
- Rollback condition: if first 10 closed trades net < −2% of starting balance,
  flip `warn_only=true` (config-only edit, no code change). Bot keeps logging
  both SLs. Alert Hermes + Utku.

---

## 5. Default-on recommendation

**On merge: DEFAULT-OFF. Flip default-on only after Gate 4 holds for two
weeks of live operation.**

Reasoning:
- Changes SL price on every new entry. Direct PnL impact.
- 7-day dataset too small to confidently prefer new rule without
  backtest + paper validation.
- `warn_only` is a free in-production observation channel; do not skip it.
- Default-off + env-gate + config-gate matches PR #42, PR #47 ergonomics.

After two weeks of Gate 4 stability, a follow-up PR may:
- Flip default `enabled` to `true`.
- Keep default `warn_only=true` until 30 days of clean operation.
- Remove the `EFLOUD_ALLOW_SL_LOGIC_V2` env gate after 60 days of clean
  operation.

---

## 6. Out of scope (explicit)

- ❌ No order/cancel/close on currently open positions.
- ❌ No edit to `aggressive_v1` config or any risk parameter.
- ❌ No breaker reset (independent Utku decision).
- ❌ No universe filtering. OP and FIL stay.
- ❌ No `risk_per_trade` / `max_open_positions` change.
- ❌ No exchange API surface change.
- ❌ No new network calls (use cached precision table).
- ❌ No mixing with PR-C (accounting/funding) or other workstreams in the
  same branch.

---

## 7. Open questions deferred to Utku

1. After Gate 3 passes, half exposure (recommended) or full exposure on
   first activation?
2. PR-B + PR #47/#42 deploy ordering: confirmed PR #47/#42 deploy first
   (defensive, independent); PR-B's Gates 2/3 can run in parallel.
3. If Phase 0 returns "interim H2 verdict" due to missing journal data, is
   PR-B allowed to merge with `warn_only=true` default and skip Gates 2/3
   until journal data is available? Default answer: **no**. Merge but do
   not deploy until journal lands.

---

## 8. References

- [v1 spec (deprecated)](./2026-05-12-pr-b-sl-logic-spec.md)
- [Brainstorming notes](./2026-05-12-pr-b-brainstorming-notes.md)
- [Phase 0 script spec](./2026-05-12-pr-b-phase0-script-spec.md)
- [Implementer prompt](./2026-05-12-pr-b-implementer-prompt.md)
- Live code reference: `engine/signals.py` `# SL / TP` block (the section
  being replaced by `compute_sl`).
- Live code reference: `engine/safety/position_guard.py` `min_sl_atr` /
  `max_sl_atr` checks (unchanged; PR-B sits upstream).
- Audit scorer reference: `engine/audit/scorer.py::score_sl_distance` (the
  scorer that defines the "sweet spot" band).
