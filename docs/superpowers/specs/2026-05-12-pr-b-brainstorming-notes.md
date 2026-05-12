# PR-B Brainstorming Notes — SL Logic Rework Decision Gate

**Date:** 2026-05-12
**Status:** Closed (decision gate passed 2026-05-12)
**Owners:** Utku (decision), Claude (architect)
**Outcome:** Phase 0 evidence PR first; PR-B implementation gated on H2 dominance.

---

## Why this note exists

PR-B (SL price logic rework) had been queued for several days. Before writing the
spec we paused to confirm we were investing in the right cause. This document
captures the brainstorming session that produced the decision and the spec.

It is **not** an implementation plan. It is the deliberation that justifies one.

---

## 1. The observation that triggered the rework

7-day live window snapshot (2026-05-05 through 2026-05-12):

| Metric | Value |
|---|---|
| Closed trades | 245 |
| Win rate | 61.6% |
| Net PnL | ~ −$13 |
| Loss concentration | OP/USDT + FIL/USDT ≈ 90% of total losses |
| Universe | 10-symbol aggressive_v1 |

A 61.6% win rate paired with net-negative PnL is the classic "small wins, big
losses" footprint. That can mean: SL too tight, SL at wrong price, strategy
expectancy too thin, or accounting drift. We did **not** assume up-front which
one — that is the discipline this brainstorm enforces.

---

## 2. Four hypotheses considered

We enumerated four non-exclusive hypotheses, each falsifiable with data we either
already have or can extract from `trades` + `trade_audits` + `trade_journal.jsonl`.

### H1 — Mechanical SL placement / protection failure

The strategy's intended SL price was reasonable, but the order system failed to
place or maintain it (no SL on exchange, orphan position, aggregate coverage
gap, TP-missing).

**Evidence already supporting H1:**
- Live log pattern: "entry success + SL fail + local state not opened".
- SUI symbol: aggregate STOP coverage only, no TP, marked orphan in current
  open positions.
- ETH/FIL state-drift cases observed.
- PRs #47 (atomic entry rollback) and #42 (orphan protection) exist *because*
  this failure mode is real.

**Falsification:** per-trade audit showing OP+FIL losers had
`outcome="SL"`, `sl_score ≥ 5.0`, and observed close price within slippage
tolerance of `t.sl`.

### H2 — Wrong SL price logic (the hypothesis PR-B addresses)

SL is mechanically placed correctly, but at the wrong price. Current code at
`engine/signals.py` (`# SL / TP` block) uses the **last swing low/high before
the break index**. Utku's spec says SL should be the **break candle range's
low (LONG) / high (SHORT)** with an ATR fallback when that range is too tight.

**Evidence already supporting H2:**
- `TIGHT_SL` and `TP_UNDERSHOT` error tags exist in post-mortem code.
- `position_guard.py` rejects SL distance < `min_sl_atr × atr14` — guard had
  to be defensive against tight strategy SLs.

**Falsification:** OP+FIL losers with `sl_score ≥ 8` (audit scorer's sweet
spot) **and** `MAE_pct >> sl_distance_pct` — meaning SL distance was reasonable
and the market just kept moving. That picture means H3, not H2.

### H3 — Poor strategy expectancy / aggressive config too loose

SL is fine, orders are fine, strategy itself has slight negative expectancy at
the current aggressive thresholds (confluence floor 55, BOS triggers enabled,
10 symbols).

**Evidence already supporting H3:**
- `aggressive_v1` deliberately lowered confluence floors (top 70→55, mid
  80→65, XRP 85→75) and enabled BOS continuation triggers on 2026-05-08.
- 245 trades / 7 days is statistically thin: −$0.05 expectancy per trade with
  standard error far exceeding the point estimate.

**Falsification:** per-symbol expectancy showing OP+FIL with `MAE > 2× ATR`
on losers consistently, BTC/ETH/ADA/etc. with positive expectancy net of
fees+funding. (Universe filtering is ruled out by Utku, so a positive
falsification of H3 escalates to signal-quality work, not SL work.)

### H4 — Reconcile / accounting / reporting mismatch

The bot's reported PnL differs from exchange-realized PnL due to close-price
estimation, fee/funding under-counting, or reconcile timing.

**Evidence already supporting H4:**
- Issue #46 (FIL accounting/reconcile mismatch) tracks this.
- `OrderManager.reconcile()` uses `_estimate_exit_price` — heuristic, not
  fetched fill price.
- Live funding accounting was a known follow-up in the backtest design doc
  (Phase B).

**Falsification:** direct comparison of `trades.pnl_usdt` against Binance's
`userTrades` / `income` endpoint over the same window. Agreement within
fee+funding tolerance kills H4.

---

## 3. Mapping to existing or planned PRs

| Hypothesis | Mitigation | Status |
|---|---|---|
| H1 | PR #47 (atomic entry rollback), PR #42 (orphan protection) | Merged not deployed |
| **H2** | **PR-B (this work)** | Spec phase |
| H3 | Strategy iteration (confluence, signal filters, regime adaptation) | Out of PR-B scope |
| H4 | PR-C / Issue #46 | Investigation pending |

---

## 4. Why we did not just write PR-B

Three of the four hypotheses do not require PR-B at all. If H1 dominates, PR
#47 + PR #42 are the right fix and PR-B is misallocated effort. If H3 dominates,
we are wrestling strategy expectancy and a new SL formula will not improve net
PnL (it may shift where losses sit, but not the sign of the expectancy). If H4
dominates, the apparent loss is partly accounting noise and we are correcting
the wrong number.

PR-B only pays off if **H2 is at least partly true**. Therefore PR-B must
come **after** evidence collection, not before.

---

## 5. Decision

**Sequencing approved 2026-05-12:**

1. **PR-A (already merged):** PR #47 + PR #42 deploy when ready (independent
   defensive value regardless of hypothesis verdict). Not blocking PR-B.

2. **Phase 0 evidence PR (the immediate next step):** Hermes builds
   `scripts/extract_sl_evidence.py` per
   [phase0-script-spec](./2026-05-12-pr-b-phase0-script-spec.md). Read-only.
   Outputs CSV + summary markdown that surfaces H1-H4 indicators per-symbol.
   It does **not** decide the verdict.

3. **Utku verdict gate:** Utku reviews the Phase 0 evidence offline and writes
   one of:
   - "H2 dominant, GO PR-B" → step 4.
   - "H1 dominant" / "H3 dominant" / "H4 dominant" → PR-B parks; alternate
     workstream activates.
   - "Need more data" → extend window or add metrics; revisit gate.

4. **PR-B implementation:** Hermes implements per
   [sl-logic-spec-v2](./2026-05-12-pr-b-sl-logic-spec-v2.md) following the
   [implementer prompt](./2026-05-12-pr-b-implementer-prompt.md). Default-OFF
   on merge. Validation-gated activation.

---

## 6. Non-obvious calls made during the brainstorm

- **No universe filtering allowed.** OP and FIL stay. Even if H3 turns out to
  be dominant, removing the two symbols is not on the table. Reason: Utku
  wants the strategy to be robust across the universe; symbol-specific
  whitelists hide the real problem.

- **Default-OFF, even after a positive Phase 0 verdict.** PR-B changes SL
  pricing on every new entry. The 7-day dataset is too small to justify
  flipping default-on without backtest + paper validation gates. We adopted
  the same default-off + env-var-gated + warn-only-first pattern that PR #42
  and PR #47 already use; consistent operational ergonomics.

- **`warn_only` as a free in-production observation channel.** With
  `enabled=true, warn_only=true`, the bot computes the new SL but does not use
  it — it logs both old and new SL with their distances. That gives us
  comparative data in live conditions before any PnL is at risk. This is a
  feature, not a stepping stone — keep it usable after Gate 4 too.

- **Triple AND-gate for live activation.** `enabled=true` (config) **AND**
  `warn_only=false` (config) **AND** `EFLOUD_ALLOW_SL_LOGIC_V2=1` (env).
  Belt-and-suspenders pattern matching `EFLOUD_ALLOW_MAINNET` precedent.

- **No backwards-compat shim required.** Configs without `risk.sl_logic`
  block default to `enabled=false` (the legacy behavior). One test enforces
  this so it cannot drift.

---

## 7. Risks acknowledged before starting

- **Phase 0 may return ambiguous evidence.** Three hypotheses can be partly
  true at once. Utku owns the call; the script does not vote.

- **`trade_journal.jsonl` may not be populated in production.** Lifecycle
  code wires it up but the state volume mount or instantiation may be broken.
  If so, MAE/MFE per past trade is not extractable and the H2/H3 separation
  weakens. (Note: confirmed real on 2026-05-12 by PR #48 smoke test —
  `journal_rows=0`. Investigation track added before any verdict.)

- **245 trades is a small sample.** Even a clean Phase 0 verdict will have
  wide confidence intervals. We accept this and rely on Gate 2 (backtest
  replay) and Gate 3 (paper run) to add evidence before flipping warn_only=false.

- **Aggressive plan recalibration on 2026-05-08 confounds the dataset.** The
  7-day window includes some pre-recalibration trades. Phase 0 script's
  `--since` flag lets Utku narrow the window if needed.

---

## 8. What is explicitly NOT in scope of this brainstorm

- No order/cancel/close actions on currently open positions.
- No edit to `aggressive_v1` config or any risk parameter.
- No breaker reset decision.
- No universe filtering decision.
- No `risk_per_trade` / `max_open_positions` change.
- No claim that the aggressive plan is "good" or "bad" — insufficient data;
  deferred until H1-H4 extractions complete.

---

## 9. Decision artifacts produced from this brainstorm

| Artifact | Status |
|---|---|
| [sl-logic-spec-v2.md](./2026-05-12-pr-b-sl-logic-spec-v2.md) | Canonical PR-B spec |
| [sl-logic-spec.md](./2026-05-12-pr-b-sl-logic-spec.md) | v1 spec, deprecated, kept for audit |
| [phase0-script-spec.md](./2026-05-12-pr-b-phase0-script-spec.md) | Read-only evidence tool spec |
| [implementer-prompt.md](./2026-05-12-pr-b-implementer-prompt.md) | PR-B implementer handoff |

---

## 10. Closure

Brainstorm closed 2026-05-12. No further hypothesis enumeration before
Phase 0 evidence lands. If Phase 0 surfaces a fifth hypothesis nobody
anticipated (e.g. liquidity-driven slippage on a specific exchange tier),
reopen this note rather than amending it silently.
