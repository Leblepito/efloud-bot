# Strategy Parameter Optimization — Handoff Report

**Branch:** `strategy-opt/jun03` · **Date:** 2026-06-03 · **Engine path:** SMC **v1** (production executes v1 under v2-shadow)
**Candidate:** `configs/candidate_opt_best.yaml` · **Review:** `docs/reviews/strategy_optimization_review.md`

> Distinct from `docs/handoff/strategy_optimization_report.md` (a concurrent session's
> *console/frontend* handoff). This report covers the **strategy parameter** work only.

---

## 1. Executive summary

Two signal-quality parameter changes — **`min_confluence 50 → 75`** and
**`recency_bars 40 → 20`** — applied to the real production config
(`configs/config.phase2_1k.yaml`) produce a **Pareto-dominant** improvement on a
multi-symbol backtest:

| Metric (real prod config, 4 sym, 90d) | PROD (conf50) | CANDIDATE (conf75+rec20) | Δ |
|---|---|---|---|
| Sharpe (per-trade) | 0.17 | **0.43** | **2.5×** |
| Profit factor | 1.53 | **2.76** | +80% |
| Win rate | 51% | **59%** | +8 pts |
| Net return | +6.6% | **+9.0%** | higher |
| Max MTM drawdown | 2.20% | **0.71%** | lower |
| Trades | 178 | 119 | −33% |

The edge **held on a fully held-out symbol basket** (cross-sectional out-of-sample),
so it is not curve-fit. It is a **minimal, reversible, two-parameter change**;
production sizing/safety is untouched (already conservative).

**Honest caveats (do not over-read):**
- "Higher Sharpe" = a *smoother, higher-quality* per-trade stream from **~33% fewer
  trades**, not necessarily more total profit. Report net return alongside Sharpe.
- The sub-1% DD above is the *recent 90-day* window. Over a rougher **180-day** window
  with production-like exposure, drawdown reaches **~10-12%** for the candidate (and
  ~13-16% on the aggressive `config.yaml` sizing). The **10% DD target is a function of
  aggregate exposure caps** (`max_total_exposure`, `max_open_positions`) — which prod
  already runs tight — **not** of these signal params.
- The search **neutralized the circuit breaker** to measure raw edge. The live breaker
  (weekly 25% / daily 10%) clips the curve; an operator `--keep-breaker` pass is a
  recommended pre-deploy step (see §9).

---

## 2. Methodology

### 2.1 Safe sweep harness (no git churn)
The plan's `autoresearch` commit/reset loop would, on this dirty working tree, sweep
unrelated uncommitted files into `git commit -am` and discard them on `git reset --hard`.
Instead a **stateless, parallel, in-process** harness was built
(`scripts/autoresearch/sweep.py`): loads OHLCV once per worker, runs
`backtest.engine.run_backtest` across a symbol basket, evaluates a JSON batch of param
overrides via `ProcessPoolExecutor`, logs every trial with objective validity flags
(`valid`/`dd_exceeded`/`low_trades`/`crash`). No `config.yaml` edits, no git churn.

### 2.2 Two correctness fixes
1. **`starting_balance` alignment (critical).** Configs ship `starting_balance` (10000
   on `config.yaml`) ≠ sim `--balance` (2000). The breaker then reads a phantom ~80%
   weekly drawdown and HALTs on tick 1 → zero trades. The harness aligns them
   (`prepare_base_config`, pinned by a regression test).
2. **Breaker neutralized for SEARCH only.** Raised in-memory so the strategy's raw edge
   is measured over the full window; the true MTM drawdown is computed independently in
   the engine and gated via `--dd-limit`. This in-memory config is never serialized to
   YAML and cannot leak to the live bot (confirmed by the Security review).

### 2.3 Performance
`step_every_n_bars=4` (hourly sampling; `recency_bars` keeps signals valid long enough
to preserve ranking) and BLAS/OMP threads pinned to 1 per worker (this pandas-bound
backtest does not parallelize within a process; pinning stops 14×20-thread CPU thrash).

### 2.4 Metric note
`sharpe_like = mean(per-trade %)/std(per-trade %)` — per-trade, not annualized;
**invariant to `risk_per_trade` scaling**. With ~100-180 trades the standard error is
~8-10%, so Sharpe gaps under ~0.05 are ties.

### 2.5 Baskets & windows
- Train (search): BTC, ETH, SOL, BNB.
- Held-out OOS: ADA, AVAX, DOT, LINK, ATOM, NEAR (none in training).
- Windows: 90d (recent) for search/confirmation; 180d (older+longer, rougher) for temporal OOS.
- Data: `cache/ohlcv/` ~365d × 20 symbols × {15m,1h,4h,1d}. Balance 2000 USDT.

---

## 3. Confluence & v1/v2 audit (Phase 2)

Confluence score (`engine/confluence.py` + level/AI injection in `signals.py`; gate at
`signals.py:491`, capped 0-100; **identical for v1 and v2**):
HTF bias **+25**, MTF CHoCH **+20**, HTF FVG **+15**, OB **+10** (+5 near-swing, +3 EQ),
OTE **+10**, SFP **+10**, range deviation **+5**, daily aligned **+5** (−5 opposed),
major opening levels **+5**, stacked S/R **+8**, AI sentiment **±5**. A typical
4-concept setup ≈ 65; **production gate = 50** (the worst end of the search).

v1 vs v2 (`engine.smc_version`, `main.py:63`): v1 = instant order; v2 = persisted
`SetupCandidate` state machine (AWAITING_PULLBACK→IN_ZONE→CONFIRMED), execution gated by
`smc_v2_symbols`. **All safety layers run identically regardless of version.**

---

## 4. Search journey (config.yaml center; direction-finding)

**OFAT (one-factor-at-a-time, 4 sym, 90d):** higher `min_confluence` is a monotonic
winner (conf70 Sharpe 0.47 / DD 3.82% vs center-55 0.27 / DD 7.09%); lower `recency_bars`
wins (rec20 0.43); `min_rr 1.8-2.0` mild; `swing_lookback` mixed; `ote_band` ≈ neutral
(weak lever in v1). 3 trials at extremes (conf45/rr2.5/swing3) crashed with an engine
`IndexError` (off-candidate; §8 follow-up).

**Combo:** `conf70-75 + rec20` ~doubled center Sharpe and halved DD; `rr1.8`/`swing8`/
`rec15` added nothing → kept `min_rr`/`swing`/`ote` at baseline (simplicity).

**Cross-sectional OOS (held-out symbols, 90d):** edge HELD on unseen symbols —
conf75+rec20 Sharpe 0.36 / DD 3.04% vs center-baseline 0.14 / DD **10.71% (breached)**.
Not overfit.

**Temporal OOS (180d) & sizing/exposure sweeps:** relative edge holds across time, but
*absolute* DD over the rough window is ~13-16% on aggressive `config.yaml` sizing and
~10-12% with prod-like exposure (`max_total_exposure 1.0`, `max_open 10`). `risk_per_trade`
barely moved DD (exposure caps fit more small positions); **aggregate exposure is the DD
lever** — and production already runs it tight. Exposure-reduced runs even *raised* Sharpe
by concentrating capital.

Full trial logs: `reports/optimization/*_detail.tsv`.

---

## 5. Confirmation on the REAL production config (the actionable result)

Re-baselined against `configs/config.phase2_1k.yaml` (the `.env.production`-active config:
conf50, risk 1.0%, max_open 10, exposure 1.0, breaker daily-10/weekly-25), 4 sym, 90d, v1:

| Config | Sharpe | Net% | DD | Trades | PF | WR |
|---|---|---|---|---|---|---|
| **conf75 + rec20 (candidate)** | **0.43** | +9.03% | 0.71% | 119 | **2.76** | 59% |
| conf70 + rec20 | 0.38 | +7.43% | 0.75% | 126 | 2.66 | 58% |
| **conf50 (current production)** | 0.17 | +6.59% | 2.20% | 178 | 1.53 | 51% |

The candidate **dominates production on every axis** here, and conf75 beats conf70,
confirming the choice. Absolute returns are modest because prod sizing is conservative —
which is precisely why prod DD stays sub-2.2% on this window.

---

## 6. Final candidate

`configs/candidate_opt_best.yaml` = `config.phase2_1k.yaml` + exactly two deltas:
`risk.min_confluence 50 → 75`, `risk.recency_bars 40 → 20`. Everything else (sizing,
exposure, breaker, smc_v2-shadow posture) = production. `testnet`+`dry_run` forced ON in
the file; deploy posture is a Hermes decision.

---

## 7. Verification (Phase 4)

- **Full targeted suite** `pytest backend/tests tests`: **1263 passed, 6 skipped** —
  the pre-existing baseline. All work is additive (sweep scripts + tests + report; zero
  engine edits) → no regression surface.
- **Safety guards** (103 targeted tests): CircuitBreaker (state roundtrip/balance-sync/
  consecutive-loss/sim-time), PositionGuard (pause/quirks/FP), **MainnetGuard**
  (`test_main_om_wiring`; `guard.py:201` aborts live mainnet without
  `EFLOUD_ALLOW_MAINNET=1`), entry-drift, reverse-on-profit, reconcile↔breaker — all pass.
- **New harness tests** (`tests/test_sweep_harness.py`): **15 passed** — pins the
  `starting_balance` alignment, breaker neutralize/keep, `ote_band` fan-out, and the
  `classify` truth table (incl. boundaries).

---

## 8. gstack virtual-team review (Phase 5)

4 parallel role agents (CEO / Eng Manager / QA / Security) using gstack playbooks.
Verdicts: CEO/Eng/Security **approve_with_nits**, QA **changes_requested**. Security
confirmed the harness **cannot place orders** (no client, no subprocess/shell/secrets;
neutralization stays in memory). **All actionable code findings were fixed**
(`resolve_timeframes` call, 15 harness unit tests, honest candidate header, `gen_batch`
label, neutralization banner). Deferred follow-ups: engine `IndexError` at param extremes,
`min_trades` floor → 30, run-provenance capture, PR scope hygiene. Detail:
`docs/reviews/strategy_optimization_review.md`.

---

## 9. Recommended next steps (Hermes / operator)

1. **Pre-deploy `--keep-breaker` pass** on the candidate over 180d to quantify how often
   the weekly-25% breaker fires (likely rarely — total 180d DD ~10-12% spread over weeks):
   `python scripts/autoresearch/sweep.py --experiments reports/optimization/rebaseline.json --base-config configs/config.phase2_1k.yaml --keep-breaker --period-days 180 --smc-version v1`
2. **Deploy as a monitored experiment**, not a silent tweak. The change cuts trade
   frequency ~33-45%. Pre-commit a rollback: e.g. live PF < 1.5 or win-rate < 50% over
   the first N trades → revert `min_confluence` to 50. Reversion is two lines.
3. **Scope the PR** to only `scripts/autoresearch/{sweep,gen_batch}.py`,
   `configs/candidate_opt_best.yaml`, `tests/test_sweep_harness.py`, and the two docs —
   keep unrelated working-tree drift out.
4. **File the engine `IndexError` follow-up** (conf45/rr2.5/swing3): capture a traceback,
   reproduce single-symbol, add a config-load input guard so out-of-range params fail
   loud rather than crashing mid-cycle.
5. **Confirm execution path**: the deltas were validated on v1 (prod executes v1 under
   v2-shadow). If v2 execution is ever enabled, re-run the sweep with `--smc-version v2`.
