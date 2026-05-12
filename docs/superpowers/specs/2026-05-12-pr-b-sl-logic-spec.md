# PR-B (Issue #45) — SL Price Logic: CHoCH/BoS Break-Range + ATR Fallback [DEPRECATED v1]

> **DEPRECATED — superseded by [2026-05-12-pr-b-sl-logic-spec-v2.md](./2026-05-12-pr-b-sl-logic-spec-v2.md).**
>
> This v1 spec is retained for audit trail only. It captures the initial four-hypothesis
> framing and acceptance criteria that were proposed on 2026-05-12 morning. Later the
> same day, Utku approved a refined direction (canonical v2) that:
>
> 1. Hard-gates PR-B implementation on a Phase 0 evidence PR (see
>    [phase0-script-spec](./2026-05-12-pr-b-phase0-script-spec.md)). Phase 0 is no
>    longer "recommended"; it is a precondition.
> 2. Splits the implementer instructions out of the spec into a separate
>    [implementer prompt](./2026-05-12-pr-b-implementer-prompt.md).
> 3. Codifies the triple activation gate (`enabled=true` AND `warn_only=false`
>    AND `EFLOUD_ALLOW_SL_LOGIC_V2=1`) as the only path to live behavior.
> 4. Acknowledges the production reality that `trade_journal.jsonl` may be empty
>    (later confirmed by PR #48 smoke test: `journal_rows=0`) and adds a journal
>    investigation track before any hypothesis verdict is rendered.
>
> Read v2 first. Use this v1 only when comparing decision history.

**Date:** 2026-05-12
**Status:** DEPRECATED — see v2
**Owners:** Utku (decision), Claude (spec), Hermes (implementation)
**Production impact:** Default-OFF on merge. Validation-gated activation.

Applied project skills:
- `efloud-trading-risk-checklist.md` — Risk-sensitive: changes SL price calculation for every new entry.
- `efloud-bugfix-workflow.md` — Treats this as a behavior change, not a refactor; requires test-first.
- `efloud-deploy-safety.md` — Default-off + validation gate before live exposure.
- `brainstorming.md` — Spec written before any code change.
- `verification-before-completion.md` — Acceptance criteria measurable, falsifiable, gate-based.

---

## 1. Root-cause hypotheses

The 7-day, 245-trade live dataset shows: 61.6% win rate, net ~−$13, OP+FIL ≈ 90% of total losses. Four non-exclusive hypotheses can explain this outcome. Each must be testable with data we either already have or can extract.

### H1 — Mechanical SL placement / protection failure

**Claim:** The strategy's intended SL price was reasonable, but the order system failed to place or maintain it (no SL on exchange, orphan position, aggregate coverage gap, TP-missing, etc.).

**Supports:**
- Live log pattern observed during incident: "entry success + SL fail + local state açılmama" (handoff).
- SUI: aggregate STOP coverage only, no TP, marked orphan in current open positions.
- ETH/FIL: state-drift cases where bot does not see the live position the way the exchange does.
- PR #47 (atomicity) and PR #42 (orphan protection) exist *because* this failure mode is real.

**Would falsify:**
- A per-trade audit (`trade_audits` joined with `trades`) showing that for OP+FIL losers, the SL order was placed on exchange, was reachable by the bot, and the position closed at the planned SL price (not at a worse price, not after a longer delay than expected).
- Specifically: `outcome="SL"`, `sl_score ≥ 5.0`, and observed close price within slippage tolerance of `sl` on the trade row.

**Data extraction needed:**

```sql
-- For OP and FIL losers in the 7-day window:
SELECT t.id, t.symbol, t.direction, t.entry, t.sl, t.exit, t.pnl_usdt, t.reason,
       a.sl_score, a.entry_score, a.overall_score, a.notes
FROM trades t
LEFT JOIN trade_audits a ON a.trade_id = t.id
WHERE t.symbol IN ('OP/USDT','FIL/USDT')
  AND t.pnl_usdt < 0
  AND t.opened_at > NOW() - INTERVAL '7 days'
ORDER BY t.opened_at DESC;
```

If `t.reason = 'RECONCILED'` instead of `'SL'`, or if `t.sl` is NULL/zero, H1 strengthens. If `t.reason = 'SL'` with normal `sl_score`, H1 weakens.

---

### H2 — Wrong SL price logic (the hypothesis PR-B addresses)

**Claim:** SL is mechanically placed correctly, but at the wrong price. Current code uses `last swing low/high *before* the break index`. Utku's spec says SL should be the **break-candle range's low (LONG) / high (SHORT)** of the CHoCH/BoS event itself, with an ATR fallback when that range is too tight.

**Supports:**
- Confirmed in code review of `engine/signals.py` (the section after `# SL / TP`): `sl_c = [s for s in e_sl if s.idx < brk.idx]; sl = sl_c[-1].price if sl_c else price * 0.99`. This is **last swing low before the break**, not the break-candle range low. Same for SHORT direction (`e_sh` swing high before the break).
- `TIGHT_SL` and `TP_UNDERSHOT` error tags exist in the post-mortem code (`engine/lifecycle.py`/`postmortem.py`), suggesting this failure pattern is recognized but the placement rule itself has not been changed.
- `position_guard.py` rejects SL distance < `min_sl_atr` ATR — meaning the guard already had to be defensive against tight SLs from the strategy.

**Would falsify:**
- A per-trade audit showing OP+FIL losers had SL distance well above 1.0× ATR (sweet spot per `audit/scorer.py::score_sl_distance`), and price went deeper than that distance on the move that hit SL.
- Equivalently: `sl_score ≥ 8` on losers + `MAE > ATR × 2` → SL distance was reasonable, market just moved further. That would mean PR-B is unlikely to help and we are debating strategy expectancy, not SL.

**Data extraction needed:**

```sql
-- SL-distance / ATR ratio for OP+FIL losers
SELECT t.symbol, t.direction, t.entry, t.sl,
       abs(t.entry - t.sl) AS sl_distance,
       (a.notes->>'atr_14h')::numeric AS atr_14h,
       abs(t.entry - t.sl) / NULLIF((a.notes->>'atr_14h')::numeric, 0) AS sl_atr_ratio,
       a.sl_score
FROM trades t
JOIN trade_audits a ON a.trade_id = t.id
WHERE t.symbol IN ('OP/USDT','FIL/USDT')
  AND t.pnl_usdt < 0
  AND t.opened_at > NOW() - INTERVAL '7 days';
```

Plus MFE/MAE — already in `journal.py` `TradeSnapshot.max_adverse_excursion_pct`. If `MAE_pct ≤ sl_distance_pct + small_buffer`, the loser barely went into SL → SL was too tight → H2 strong. If `MAE_pct >> sl_distance_pct`, market kept moving → H2 weaker.

---

### H3 — Poor strategy expectancy / aggressive config too loose

**Claim:** SL is fine, orders are fine. The strategy itself has slight negative expectancy at the current aggressive thresholds (confluence floor 55, BOS triggers enabled, 10 symbols).

**Supports:**
- Aggressive config `aggressive_v1` deliberately lowered confluence floors (top 70→55, mid 80→65, XRP 85→75) and accepted BOS continuation triggers — a documented post-zero-trade recalibration on 2026-05-08. Recalibration was correct in direction but the new operating point may sit on the wrong side of break-even.
- Two-symbol concentration (OP+FIL = 90% of loss) by itself is *not* evidence of strategy failure — it can mean those two symbols' liquidity/volatility profile doesn't fit the SMC primitives well at current floors. But Utku has explicitly ruled out universe filtering, so we cannot use it as a remediation.
- 245 trades / 7 days is statistically thin. Net −$13 / 245 trades ≈ −$0.05 expectancy per trade; the standard error on this is much larger than the point estimate.

**Would falsify:**
- Per-symbol P&L distribution showing OP and FIL with `MAE > 2× ATR` consistently on losers (market kept moving against entry beyond any reasonable SL), AND BTC/ETH/ADA/etc. with positive expectancy net of fees+funding.
- That picture means: strategy is fine on 8 symbols, breaks down on 2 — and Utku's "no filtering" rule forces us to live with the drag or fix it via signal quality (confluence/MTF), not via SL.

**Data extraction needed:**

```sql
-- Per-symbol expectancy + trade count, last 7 days
SELECT t.symbol,
       COUNT(*) AS trades,
       SUM(CASE WHEN t.pnl_usdt > 0 THEN 1 ELSE 0 END) AS wins,
       AVG(t.pnl_usdt) AS expectancy,
       SUM(t.pnl_usdt) AS net_pnl,
       AVG(a.overall_score) AS avg_quality_score
FROM trades t
LEFT JOIN trade_audits a ON a.trade_id = t.id
WHERE t.opened_at > NOW() - INTERVAL '7 days'
  AND t.closed_at IS NOT NULL
GROUP BY t.symbol
ORDER BY net_pnl;
```

H3 is the residual hypothesis: it is supported only after H1, H2, H4 are tested and don't explain the loss.

---

### H4 — Reconcile / accounting / reporting mismatch

**Claim:** The bot's reported PnL differs from the exchange's actual realized PnL because of close-price estimation, fee/funding under-counting, or reconcile timing.

**Supports:**
- Issue #46 (FIL accounting/reconcile mismatch) explicitly tracks this.
- `OrderManager.reconcile()` uses `_estimate_exit_price` when a position disappears from exchange-side `bn_open_symbols` — this is a heuristic, not a fetched fill price.
- Funding fees are computed via `backtest/funding.py` for backtest but the live path's funding accounting was a known follow-up in the backtest design doc (Phase B).

**Would falsify:**
- A direct comparison of `trades.pnl_usdt` against Binance's `userTrades` or `income` endpoint over the same window, summed per symbol. If they agree within fee/funding tolerance, H4 is dead.

**Data extraction needed:**
- Bot side: `SELECT symbol, SUM(pnl_usdt) FROM trades WHERE opened_at > NOW() - INTERVAL '7 days' GROUP BY symbol;`
- Exchange side: `compare_live.py` (already exists in repo) extended to pull `fetch_my_trades` + `fetch_funding_history` for the same period.
- Hermes-task scope, separate from PR-B.

---

### Hypothesis-to-PR mapping

| Hypothesis | Mitigation | Status |
|---|---|---|
| H1 | PR #47 (atomicity), PR #42 (orphan protection), PR #42.1 patch | Merged not deployed |
| **H2** | **PR-B (this spec)** | **Spec phase** |
| H3 | Strategy iteration (confluence, signal filters, regime adaptation) | Out of scope here |
| H4 | PR-C / Issue #46 | Investigation pending |

PR-B is necessary only if H2 is at least partly true. The acceptance criteria below include a "guardrail": if backtest+paper validation show no improvement, PR-B does **not** get flipped to default-on.

---

## 2. PR-B acceptance criteria

### 2.1 SL price rule

For a signal triggered by a CHoCH or BoS break at bar index `brk.idx`:

**LONG (BULL break):**
- `SL_structural = min(low[brk.idx - bos_range_lookback : brk.idx + 1])`
  - That is: the lowest low over the `bos_range_lookback` bars ending at and including the break candle.

**SHORT (BEAR break):**
- `SL_structural = max(high[brk.idx - bos_range_lookback : brk.idx + 1])`
  - The highest high over the same window.

**ATR fallback** (applies in both directions):
- Let `atr14 = ATR(period=14)` computed on the entry-TF series up to and including `brk.idx`.
- Let `min_sl_distance = max(atr_fallback_mult × atr14, tick_size × min_ticks_above_entry)`.
- If `|entry_price − SL_structural| < min_sl_distance`, use the ATR fallback:
  - LONG: `SL = entry_price − min_sl_distance`
  - SHORT: `SL = entry_price + min_sl_distance`
- Otherwise: `SL = SL_structural`.

**Final tick/precision normalization:**
- Round SL away from the entry (LONG: floor to tick; SHORT: ceil to tick) using `client.price_precision(symbol)`.
- After rounding, re-check the immediate-trigger guard: `|entry_price − SL| >= tick_size × min_ticks_above_entry`. If violated, widen by one tick.

### 2.2 Parameters (config-driven, all under `risk.sl_logic.*`)

| Param | Default | Range | Comment |
|---|---|---|---|
| `enabled` | **false** | bool | Default-OFF. Must flip in config to activate. |
| `bos_range_lookback` | 3 | 1–10 | Bars from break candle backwards (inclusive). 3 ≈ "break candle + 2 prior bars". |
| `atr_period` | 14 | 7–30 | Standard ATR length for the fallback. |
| `atr_fallback_mult` | 1.0 | 0.5–3.0 | Minimum SL distance in ATRs. Sits inside `position_guard.min_sl_atr` band. |
| `min_ticks_above_entry` | 3 | 1–20 | Hard floor against immediate-trigger after rounding. |
| `warn_only` | true | bool | When `enabled=true` but `warn_only=true`, log the new SL alongside the old, do NOT change behavior. |

### 2.3 Immediate-trigger prevention

After the SL price is computed and rounded:

1. The current best bid/ask (or last trade price) must NOT already be on the SL side of the entry by more than `tick_size × 2`. If it is, the signal is rejected with `reject_reason='SL_ALREADY_TRIGGERED'` and a structured WARNING log.
2. The `position_guard` check is unchanged: SL distance must satisfy `min_sl_atr ≤ |entry−SL|/atr14 ≤ max_sl_atr`. PR-B sits *upstream* of position_guard, and feeds it a (hopefully) sensible distance.

### 2.4 Tick / precision handling

- All prices computed in float, but final SL value is normalized through `client.normalize_price(symbol, side='SL', direction=position.direction)`.
- Add a `price_precision` lookup that does NOT depend on a live exchange call when running in `dry_run` / backtest. The lookup is already provided by `BinanceClient.markets` cache; PR-B must not introduce a new network call.

### 2.5 Behaviour switches

The new SL rule activates only when all three are true:
1. `risk.sl_logic.enabled = true` in active config.
2. `risk.sl_logic.warn_only = false`.
3. `EFLOUD_ALLOW_SL_LOGIC_V2=1` env var present (belt-and-suspenders production gate).

If any of the three is false → fall back to current code path (`last swing low/high before brk.idx`).

---

## 3. Tests required (TDD, before any production-path edit)

### 3.1 Unit tests — pure SL calculator

A new module `engine/sl_logic.py` exposes a pure function:

```python
def compute_sl(
    direction: str,             # "LONG" | "SHORT"
    entry_price: float,
    brk_idx: int,
    df: pd.DataFrame,           # entry-TF OHLCV up to and including brk_idx
    params: SLLogicParams,      # dataclass with the 6 params above
    tick_size: float,
) -> SLResult:                  # {price, source: 'structural'|'atr_fallback', distance, atr14}
```

Tests in `tests/test_sl_logic.py`:

1. `test_long_uses_break_range_low_when_distance_above_atr`
2. `test_short_uses_break_range_high_when_distance_above_atr`
3. `test_long_falls_back_to_atr_when_structural_too_tight`
4. `test_short_falls_back_to_atr_when_structural_too_tight`
5. `test_long_sl_rounded_floor_to_tick`
6. `test_short_sl_rounded_ceil_to_tick`
7. `test_immediate_trigger_widens_by_one_tick`
8. `test_atr_zero_returns_minimum_ticks_distance`  (degenerate: flat bars)
9. `test_lookback_clamped_to_available_history`     (brk_idx < lookback)
10. `test_disabled_returns_legacy_value`            (`enabled=false` → returns legacy SL unchanged)

### 3.2 Integration test — `generate_signals` path

In `tests/test_signals.py`:

11. `test_signal_uses_v2_sl_when_enabled` — synthetic mock-engine, `enabled=true`, `warn_only=false` → `signal.sl` matches the new rule.
12. `test_signal_logs_both_sls_when_warn_only` — `warn_only=true` → signal.sl is the legacy value, but a structured INFO/DEBUG log records both old and new SL with their distances.
13. `test_signal_rejected_when_immediate_trigger` — synthetic bar where current price is already past the proposed SL → signal is dropped with the new reject reason; reject log includes `SL_ALREADY_TRIGGERED`.
14. `test_position_guard_still_runs_after_v2_sl` — chain test, asserting guard's `min_sl_atr` floor is still respected post-PR-B.

### 3.3 Regression tests

15. `test_legacy_sl_path_unchanged_when_flag_off` — full `generate_signals` smoke with `enabled=false`; the existing 60+ tests in `test_signals.py` must continue to pass with byte-identical signal objects.
16. `test_aggressive_v1_config_loads_without_sl_logic_block` — backwards compatibility: configs without `risk.sl_logic` block default to `enabled=false` (the legacy behavior).

### 3.4 Backtest determinism

17. `test_backtest_deterministic_with_sl_logic_v2` — same data + same `enabled=true` config → byte-identical `result.json` across two runs (alphabetical symbol order already enforced in `backtest/engine.py`).

---

## 4. Validation gate before live deploy

PR-B is **default-OFF**. Activating it on production requires **all four** gates to pass in order. Each gate produces a written artifact in `docs/validation/2026-05-pr-b/`.

### Gate 1 — Unit + integration test suite (CI)

- Command: `python -m pytest tests/ backend/tests/ -q`
- Required: 17 new tests pass + 0 regressions on the existing suite.
- Artifact: CI green check on PR-B branch.

### Gate 2 — Backtest replay on 7-day live window

- Command: `python -m backtest.cli portfolio --symbols <10-symbol-universe> --period 7d --config configs/config.aggressive_v1.yaml --balance 2900 --sl-logic-v2`
- Compare three runs side-by-side:
  - **A: Legacy** — `enabled=false` (current code path)
  - **B: V2 warn-only** — `enabled=true, warn_only=true` (logs new SL but uses legacy)
  - **C: V2 active** — `enabled=true, warn_only=false`
- Required acceptance:
  - Run C net PnL ≥ run A net PnL (i.e., new SL rule is at least neutral on the 7-day replay).
  - Run C max drawdown ≤ run A max drawdown × 1.15 (no more than 15% worse DD).
  - Per-symbol report shows OP and FIL net PnL improvement under C vs A, OR no statistically meaningful change (since 7d sample is small).
- Artifact: `docs/validation/2026-05-pr-b/backtest-replay.md` with the three result.json summaries.

**Failure handling:** If C is materially worse than A, **do not deploy**. Either:
- The new rule's parameters need re-tuning (extract per-trade SL distance & MAE from B's warn-only logs; pick `atr_fallback_mult` that matches realized MAE distribution), or
- H2 was wrong and the loss source lies elsewhere (escalate back to Utku).

### Gate 3 — Paper / dry-run window (48–72h)

- Deploy PR-B to production VPS with `dry_run=true`, `sl_logic.enabled=true`, `warn_only=false`, and `EFLOUD_ALLOW_SL_LOGIC_V2=1`.
- Bot runs against live market data, generates signals, computes new SLs, but does NOT place orders.
- Required acceptance:
  - No `SL_ALREADY_TRIGGERED` storm (< 5% of signals rejected for this reason).
  - No exceptions / crashes in `sl_logic.compute_sl`.
  - Average `|sl − entry|/atr14` ratio sits in `[1.0, 2.5]` (the audit scorer's sweet spot).
  - At least 5 distinct symbols produce at least 1 signal in the window (sanity: SL logic doesn't filter all signals away).
- Artifact: `docs/validation/2026-05-pr-b/paper-run.md` with structured-log summary.

### Gate 4 — Breaker policy + live activation

- Bot is currently TRIPPED (3 consecutive losses). **PR-B does NOT change the breaker reset rule.**
- Breaker reset happens only after Gate 3 passes AND Utku explicitly approves live activation.
- On reset:
  - Flip `sl_logic.enabled=true`, `warn_only=false`, `EFLOUD_ALLOW_SL_LOGIC_V2=1`.
  - Keep `aggressive_v1` config otherwise unchanged (confluence floors, BOS triggers, etc.).
  - Run for 48h with reduced exposure: `safety.max_position_notional_pct` capped at half of the current value, until 10+ closed trades with the new SL rule are observed.
- Rollback condition: if first 10 closed trades net < −2% of starting balance, flip `warn_only=true` (config-only edit, no code change), let bot continue logging both SLs for diagnostics, alert Hermes/Utku.

---

## 5. Default-off / default-on recommendation

**Recommendation: DEFAULT-OFF on merge. Flip to default-on only after Gate 4 holds for 2 weeks of live operation.**

Reasoning:
- PR-B changes the SL price on every new entry. That is a behavior change with direct PnL impact.
- The 7-day dataset is too small to confidently prefer the new rule over the old without backtest+paper validation.
- The "warn_only" mode gives us a free in-production observation channel before any PnL is at stake.
- Default-off + env-gated + config-gated is the same pattern PR #42 and PR #47 used; consistent operational ergonomics.

Two parameters that should default-on inside PR-B once `enabled=true`:
- `warn_only=false` only after Gates 1–3 pass.
- `EFLOUD_ALLOW_SL_LOGIC_V2=1` only set in production env after Gate 3.

---

## 6. Recommendation: should Hermes implement PR-B now?

**Yes, with the following sequencing.**

### Phase 0 — Before Hermes writes any code (Utku + Claude, ~30 min)

- Run the four SQL extractions in §1 (H1–H4 data) against production DB.
- Build a 4-row table: per-hypothesis evidence found vs. expected-if-true.
- Decide:
  - If H1 dominates → defer PR-B, focus on PR #42/#47 deploy first.
  - If H2 dominates → proceed to Phase 1.
  - If H3 dominates → escalate strategy discussion before any SL work.
  - If H4 dominates → PR-C / Issue #46 takes priority.

This step is **non-negotiable**: PR-B is the wrong investment if H2 isn't where the loss lives. The extractions take maybe an hour wall-clock and avoid days of wasted implementation.

### Phase 1 — Hermes implements per this spec

- Branch: `feature/sl-logic-v2`
- TDD: write the 17 tests first (§3), each failing red, then implement `engine/sl_logic.py` and the `generate_signals` integration to green.
- All changes default-off. No live behavior change on merge.
- Atomic PR. No mixing with PR #42.1 or PR-C.

### Phase 2 — Validation (Claude + Hermes)

- Gate 1: CI.
- Gate 2: backtest replay over the 7-day window, three configs (A/B/C in §4 Gate 2).
- Gate 3: paper run 48–72h.
- Each gate produces a written artifact and a clear go/no-go.

### Phase 3 — Live activation (Utku approves)

- Gate 4. Reduced exposure. 10 trades minimum before unlocking full size.

### If Phase 0 says "data isn't available yet"

`trade_audits` and the `notes` payload should already contain ATR + recent_high/low — the audit pipeline lands per-trade context. If for some symbols audits are missing (the audit engine no-ops gracefully when the pool is None), Phase 0 must include:

- A read-only Python script `scripts/extract_sl_evidence.py` that joins `trades` + `trade_audits` + computes MAE from `journal.py` snapshots in `trade_journal.jsonl`.
- Run it locally against the production DB read replica or a fresh dump.
- Output: CSV with one row per closed trade in the 7-day window: `symbol, direction, entry, sl, exit, reason, pnl, sl_distance, atr14, sl_atr_ratio, mae_pct, mfe_pct, sl_score, overall_score`.

If `trade_journal.jsonl` is not being written in production (worth checking — `lifecycle.py` has the wiring but the production state volume may not include it), then MAE/MFE aren't extractable for past trades and we must:
- Accept that the 7-day evidence is incomplete.
- Run PR-B's warn-only mode (Gate 3) for longer (1–2 weeks) to collect the comparative data before flipping `warn_only=false`.

---

## 7. Out of scope (explicitly)

- **No order/cancel/close actions.** This spec does not modify positions currently open.
- **No production config edit.** `aggressive_v1` stays as-is until Gate 4.
- **No breaker reset.** Independent decision.
- **No universe filtering.** OP and FIL remain in the universe.
- **No `risk_per_trade` / `max_open_positions` changes.**
- **No claim that the aggressive plan is "good" or "bad".** Insufficient data; decision deferred until H1–H4 extractions complete.

---

## 8. Open questions for Utku

1. Are `trade_audits` rows being written in production right now? If not, Phase 0's evidence extraction will be partial.
2. Is `trade_journal.jsonl` persisted on the VPS state volume (so MFE/MAE per closed trade is available)? If not, we lose a key data axis for H2 vs H3 separation.
3. After Gate 3 passes, do you want reduced exposure (half `max_position_notional_pct`) or full exposure on first activation? Recommendation: half.
4. PR-B + PR #42.1 deploy ordering: PR #42.1 (orphan analyzer fixes) is purely defensive and can deploy independently; PR-B's gates are slower. Confirm we deploy PR #42.1 first, run Gate 2/3 for PR-B in parallel.

---

## 9. Next action

**Utku:** answer the 4 questions in §8, and run (or delegate to Hermes) the 4 SQL extractions in §1. Until that data lands, PR-B implementation should NOT start.

**Hermes:** wait. Once Phase 0 confirms H2 is in play, branch off and implement per §3 (TDD) and §2 (rule). No deploys.

**Claude:** review Hermes's PR-B implementation against this spec; produce Gate 2 backtest comparison once code lands.
