# Operator decisions (6 open items) + backtest restore on the live trade logic — design

Date: 2026-11-07 · Author: claude-code · Status: **approved by delegation**. On 2026-11-07 the
operator said: "evaluate the 6 items with brainstorming, answer on my behalf; restore the
backtest, but it must run on the bot's current trade logic; leave the SSH password item for now."

## 1. Decisions

| # | Open item | Decision | Why |
|---|---|---|---|
| 1 | LLM macro sentiment adds ±5 before `min_confluence` (A1); writer `state/` ≠ engine `state_1k/` (A2) | **(a) Telemetry only.** Keep the value in `sig.meta["macro_sentiment"]`, drop the ±5, and make the writer, the engine and the dashboard use the same `state_dir` | ADR-0002 (LLM never changes a trade) and audit H1 (no post-cap bonuses). Prod is already effectively NEUTRAL (A2), so **zero live behaviour change**. The backtest (§3) proves it byte-identical |
| 2 | Structure validation: 23,085/23,085 fallback, synchronous on the hot path (L1) | **Flag, default OFF** (`engine.structure_validation.enabled: false`); when off the call is skipped | Same live outcome as today (always pass-through), minus a dead call. Turning it on later needs ADR-0002's shadow → measure → sign-off. Kept, not deleted (Karpathy #3) |
| 3 | Backtest tooling removed in `562a6a3` | **Restore it, driven by the live trade logic** (§2–§3) | Operator's explicit decision |
| 4 | CLAUDE.md layout | **Constitution only.** Move the dated status narrative (the first-line "Son çalışma…" blurb and "🚀 Son Durum & Güncel Gelişmeler") to `docs/history/claude-md-status-archive.md`, leaving one pointer; the live state lives in `collab/STATUS.md` | `living-docs-governance` roles. Today the dated blocks are what went stale (#329) |
| 5 | Dashboard demo video: which data | **No real account data.** Record the public illustrative page (`u2algo.com/live.html`, already labelled as a simulation) and `premium.html` with Playwright (`ui-demo`) | Nothing private can leak, and the page already carries the simulation disclaimer |
| 6 | sshd `PasswordAuthentication` | **Deferred** (operator: "şimdilik durabilir") | — |

Order: §2 backtest first. Decisions 1 and 2 are then verified with it (identical trades
before/after on the live config), then 4, then 5. Each one is its own PR.

## 2. Backtest restore — approaches

**A. Restore `562a6a3^:backtest/` verbatim + tests, then close the live-parity gaps (recommended).**
The old engine already calls the real `SafeOrchestrator.run_cycle()` with the live config, so
signal, guard, breaker and SMC v2 logic are the live code by construction. The gaps are in what
the harness adds around it (§3.2). Small, reviewable diff; restores 12 test modules that encode
earlier bug fixes (BT-4/9/12/16/17).

B. Write a new harness around `OrderManager` with a simulated exchange client. Highest fidelity
for order placement, but large: it duplicates exchange behaviour and has its own bugs. Rejected
as over-built (Karpathy #2).

C. Replay-only: re-run the live journal through the engine without market simulation. Cannot
evaluate *changes* (no counterfactual fills). Rejected as the gate; kept as a parity check (§3.4).

## 3. Design (approach A)

### 3.1 What is restored
`backtest/{__init__,engine,intrabar,slippage,funding,metrics,montecarlo,grid,comparison,reproducibility,compare_live,cli}.py`,
`scripts/evaluate_backtest_gates.py`, and the 13 removed test modules
(`backend/tests/test_backtest_*.py`, `backend/tests/test_evaluate_backtest_gates.py`,
`tests/test_backtest_max_hold.py`), all from `562a6a3^`. Tests are adapted only where the live
code legitimately changed since 2026-10-31. Every adaptation is listed in the PR.

### 3.2 Live-parity gaps the harness must close

| Gap (old harness) | Live behaviour | Change |
|---|---|---|
| `smc_version` is a parameter, default `"v1"` | Live config: `engine.smc_version: v2` + `smc_v2_symbols` list | Default = read from config (`engine.smc_version`); the parameter only overrides |
| Intrabar exit = SL or TP1 → **100 % close at TP1** | `OrderManager`: TP1 = 50 % (single-target: 100 %), SL → break-even, TP2 = rest (105/105 live trades are dual-target) | Intrabar model uses `lifecycle.partial_close(pos, tp1, 0.5, "TP1")` (which already does BE + single-target), then TP2 on later bars. Pessimistic order inside one bar: SL first, then TP1. TP2 is never filled in the same bar as TP1 |
| Costs default 0 | Binance USD-M taker fees + funding | CLI defaults to NET: commission 0.04 %/side, funding 0.01 %/8 h (flags override; `--gross` for comparison only) |
| LLM / agent team / Kronos may be called | Must never reach a network from a backtest | `run_backtest` forces `agent_team.enabled=false`, `kronos.enabled=false` and patches `engine.agents.llm.make_llm_client` to a null client for the run. Structure validation then passes through, exactly like prod today |
| Breaker/time uses wall clock in places | Live uses real time | Keep the existing `now=sim_now` pass-through. Any remaining wall-clock use found is fixed or listed as a known divergence |

The default run is the **live config file unchanged**: `configs/config.phase2_1k.yaml` (mid, V1 bot).

### 3.3 Data flow
`scripts/prefetch_data.py` (public Binance OHLCV, no key) → `cache/ohlcv` (`data/cache.OHLCVCache`,
sha-verified) → `python -m backtest.cli single|portfolio --config configs/config.phase2_1k.yaml`
→ `reports/backtest/<run-id>/{result.json,provenance.json}`, with provenance = git sha + config
hash + data manifest → optional `scripts/evaluate_backtest_gates.py` verdict (exit code).

### 3.4 Parity check against live (informational)
`backtest.compare_live.reconcile()` is fed the live journal (`state_1k/trade_journal.jsonl`,
copied read-only from the VPS, 105 trades 2026-09-28 → 2026-11-06) and a backtest over the same
window, symbols and config. The report gives match rate by (symbol, direction, ±1 entry bar) plus
PnL drift. It is **not a gate**: live fills, confirmation timing and reconcile closes differ by
nature. Unmatched trades are listed as known divergences.

### 3.5 Error handling
- A failing `run_cycle` stays counted in `skipped_cycles` (existing). The CLI exits non-zero when
  skipped > 1 % of cycles.
- Missing or stale cache keeps the existing loud warning; a missing timeframe is a hard error.
- Windows: `grid` stays serial by default (ProcessPool hang, see memory note), opt-in `--workers`.

### 3.6 Testing
- Restored test modules green (adapted only for documented live-code changes).
- New: exit-model tests (TP1 50 % + BE then TP2; single-target 100 %; SL-before-TP1 in the same
  bar; BE stop after TP1), config-derived `smc_version`, NET-cost CLI default, and a no-network
  guard (a test fails if the LLM factory is reached unpatched during `run_backtest`).
- A smoke backtest on cached data (one symbol, short window) runs in CI time limits, or is marked
  slow.
- `REGRESSION.md`: new `backtest` module (re-render). `TESTS.md`: TEST-BT-* rows. `TESTS.md` §1
  and ADR-0003 "Known gap" are updated to say the gate is runnable again.

## 4. Out of scope
Changing any trading parameter or strategy logic; a full exchange simulator (approach B);
sshd changes (item 6).
