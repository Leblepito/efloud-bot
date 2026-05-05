# Epic 1b — Backtest Validation Execution — Design

**Author:** Leblepito + Claude
**Date:** 2026-05-05
**Status:** Approved (no formal spec-review loop; this is execution plan, not new code)
**Parent:** `docs/superpowers/specs/2026-05-05-efloud-roadmap.md` (Aşama 1)
**Related:** `docs/superpowers/specs/2026-05-04-backtest-design.md` (Epic 1a — implementation, ~done)

> **For agentic workers:** Use `superpowers:executing-plans` while running phases; use `superpowers:verification-before-completion` before claiming results are valid. STOP and surface to owner if any failure mode in §5 fires.

---

## 1. Goal

Execute the implemented backtest subsystem on `phase2_1k` config and decide whether the strategy is profitable enough to start a 30-90 day live track-record period (Aşama 3). Output: a go/no-go decision document.

## 2. Scope

**In:**
- Phase A — portfolio mode, 10 symbols × 1y (asıl validation)
- Phase A — single mode, top-3 symbols by net PnL (diagnostic, run after portfolio)
- Phase B — live-vs-backtest reconcile against live data since 2026-05-02 (engine parity check)

**Out:**
- Phase C — grid search (only triggered if Phase A is borderline; see §6)
- Strategy redesign (Epic 6 territory; only triggered if Phase A fails)
- Engine code changes (Epic 1a is frozen for this validation)

## 3. Where & How

- **Machine:** Local (the user's Windows). Hetzner is reserved for live bot CPU.
- **Worktree:** `C:/Users/utkuc/Downloads/efloud-bot-backtest` on `feature/backtest-subsystem`.
- **Config:** `configs/config.phase2_1k.yaml` (existing live config baseline).
- **Cache:** `cache/` under the backtest worktree; verify populated for 1y of 10 symbols × 15m bars + funding rates. If missing, run prefetch script first.
- **Output:** `reports/backtests/{run_id}/` (uuid4 short id auto-generated).

## 4. Acceptance — GO Thresholds

Strategy must clear ALL of these for **GO**:

| Metric | Threshold | Source |
|--------|-----------|--------|
| Total return (1y, net of fees+funding+slippage) | > 0% | summary.md |
| Sharpe (annualized) | > 0.5 | summary.md |
| Max drawdown | < 30% | summary.md |
| Win rate | > 35% | summary.md |
| Profit factor | > 1.2 | summary.md |
| Total trade count | > 100 | trades.csv row count |
| Phase B mean abs fill-price drift | < 5% | reconcile output |

Thresholds calibrated for crypto futures 5x leverage; revisited after first run if data shows they're miscalibrated.

## 5. Failure Modes — STOP and surface to owner

- Engine raises uncaught exception during Phase A
- `reports/backtests/{run_id}/summary.md` not produced after a phase finishes
- Total return ≤ 0% AND max DD ≥ 30% (clearly unprofitable + risky — owner reviews)
- Phase B fill-price drift > 5% mean abs (parity bug in engine; **must fix before any track record**)
- Cache prefetch fails for any symbol after 3 retries

## 6. Decision Tree

After Phase A + B run:

| Condition | Decision | Next |
|-----------|----------|------|
| All metrics ≥ GO threshold AND Phase B drift < 5% | **GO** | Brainstorm Aşama 2 (Epic 3+4) |
| 1-2 metrics within 20% below threshold (borderline) | **OPTIMIZE** | Run Phase C grid (limited Epic 6 entry) → re-validate |
| 3+ metrics fail OR total return ≤ 0% | **ITERATE** | Full Epic 6 brainstorming (strategy redesign) |
| Phase B drift ≥ 5% | **FIX FIRST** | Engine parity bug; not Aşama 2 yet |

## 7. Deliverables

- `reports/backtests/{run_id}/{summary.md, trades.csv, equity.json, provenance.json}` — auto by CLI
- `docs/superpowers/specs/2026-05-05-backtest-validation-results.md` — manual: threshold comparison + decision + recommended next epic
- Both committed; `efloud_state` memory updated with results

## 8. Estimated effort

- Cache verify/prefetch: 5-10 min (skip if populated)
- Phase A portfolio: 30-90 min compute
- Phase A single-mode top-3: 15 min compute
- Phase B reconcile: 5 min
- Results doc + commits: 30 min
- **Total: half-day to one day, mostly compute time**

## 9. Open questions

- Are GO thresholds (especially Sharpe 0.5, Max DD 30%) right for Lead Trader appeal? → calibrate after first run.
- Should single-mode top-3 use top by net PnL, by Sharpe, or by trade count? → default: top-3 by net PnL; revisit if portfolio output shows odd distributions.
