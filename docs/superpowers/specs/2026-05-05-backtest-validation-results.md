# Epic 1b — Backtest Validation Results

**Date:** 2026-05-05
**Run analysed:** `reports/backtests/phase_a_2026-05-05_2de8bd/` (started 17:46, finished 21:09; ~3h 23min)
**Config:** `configs/config.phase2_1k.yaml` ($2000 wallet, 5x leverage)
**Symbols:** BTC, ETH, BNB, XRP, ADA, DOGE, SOL, BCH, LINK, TRX (10 symbols)
**Period:** 1 year historical, 15m bars
**Decision:** **ITERATE** — strategy redesign required (Epic 6)
**Parent:** `docs/superpowers/specs/2026-05-05-backtest-validation-design.md`

---

## 1. Decision summary

The current `phase2_1k` strategy fails 5 of 7 GO thresholds and posts a **−43.75% net return** over 1 year. Per the decision tree in the validation design (§6: "3+ metrics fail OR total return ≤ 0%"), the result is **ITERATE**.

Aşama 2 (Epic 3+4) and Aşama 3 (track record) cannot start with this strategy — a Lead Trader application would be rejected on track record alone. Epic 6 (strategy redesign) is now the critical path.

## 2. Metrics vs GO thresholds

| Metric | Threshold | Actual | Status |
|--------|-----------|--------|--------|
| Total return (1y, net) | > 0% | **−43.75%** | ❌ FAIL |
| Sharpe (annualized-like) | > 0.5 | **0.03** | ❌ FAIL |
| Max drawdown | < 30% | **44.24%** | ❌ FAIL |
| Win rate | > 35% | 40.5% | ✅ PASS |
| Profit factor | > 1.2 | **1.08** | ❌ FAIL |
| Total trades | > 100 | 1709 | ✅ PASS |
| Phase B drift | < 5% | not measured | N/A — Phase B not run; ITERATE path bypasses it for now |

**Balance trajectory:** Initial $2000 → Peak $2013 (only +$13 high-water mark) → Final $1124.97 (−$875 net loss).

## 3. Per-symbol breakdown

```
Symbol      Return    MaxDD   Sharpe  Trades  Win%   PF
TRX/USDT    +0.16%   0.42%   0.140      20  45.0%  1.36
DOGE/USDT   −3.12%   3.59%  −0.240      38  34.2%  0.59
ETH/USDT    −4.68%   4.92%   0.100     232  44.0%  1.28
BNB/USDT    −5.06%   5.47%  −0.040     267  37.8%  0.91
ADA/USDT    −5.41%   6.99%   0.060      88  44.3%  1.16
BTC/USDT    −5.47%   5.56%   0.130     237  47.3%  1.37
XRP/USDT    −5.66%   5.66%   0.030     138  42.8%  1.06
BCH/USDT    −8.30%   8.76%  −0.010     244  34.8%  0.98
SOL/USDT    −8.98%   9.19%   0.140     248  44.0%  1.39
LINK/USDT  −12.71%  12.72%  −0.020     185  36.2%  0.95
```

Only TRX (20 trades, marginal +0.16%) is positive. 9/10 symbols negative. Strategy does not generalise across the universe.

Note: every symbol's max drawdown is approximately the absolute value of its return — this is the signature of a **slow bleed without large winning runs**. Equity curve climbs briefly, then loses; never reaches a meaningfully higher peak before falling below it.

## 4. Diagnostic findings

### 4.1 SL-heavy exit distribution

```
SL:  59.6% (1018 trades)
TP2: 33.4% (571 trades)
TP1:  7.0% (120 trades)
```

Three of every five trades exit on stop-loss. The R:R structure is not compensating: even when TP2 hits more often than TP1 (suggesting trends do continue when caught), the SL-rate dominates total pnl arithmetic.

### 4.2 LONG bias is broken

```
LONG:  887 trades  →  total PnL = −$31    (mean −$0.04)
SHORT: 822 trades  →  total PnL = +$292   (mean +$0.36)
```

SHORT trades are net positive. LONG trades are net flat. **The strategy's LONG signal is not generating positive expectancy.** This is a logic problem, not a parameter problem.

### 4.3 Fee/funding/slippage burn — root cause of net negativity

```
Gross PnL (LONG + SHORT):  +$261
Net result:                −$875
Implied cost overhead:    ~$1,136
```

The strategy generates positive gross PnL but the costs of executing 1709 trades over 1 year (fees + funding + slippage) eat **~4× the gross profit**. At ~5 trades/day × 10 symbols, the trade frequency itself is the structural problem. **Cannot be optimised away** by parameter sweeps; only signal-density reduction or higher per-trade expectancy can fix it.

## 5. Why Phase C grid optimization will NOT rescue this

Phase C (parameter grid) was the borderline-case fallback. It is **not a viable path here** because:

1. **Fee burn is structural** — fewer parameters won't change that 1709 trades over 1y is too many at this notional. Less coverage = fewer signals fires of the same poor quality.
2. **LONG signal logic broken** — grid search over thresholds doesn't fix a directional bias that's flat-to-negative. This is a code-level issue.
3. **9/10 symbols negative** — the strategy doesn't generalise. Per-symbol parameter tuning would be in-sample overfitting, not optimization.

## 6. Suspicious finding — possible engine bug

Trade `opened_at` / `closed_at` timestamps in `portfolio.json` are wall-clock seconds (e.g., `2026-05-05T12:41:27.759663`) — i.e., the simulation execution time, not the bar's historical time. This does **not** affect P&L metrics (those are computed from price diffs, not timestamps), but it does:

- Make it impossible to do **Phase B live-vs-backtest reconcile** (which needs bar timestamps to align live trades with simulated trades)
- Hide whether trades cluster in specific market regimes

**Action:** before Epic 6 redesign starts, verify and (if needed) fix the trade-timestamp persistence so Phase B reconcile is meaningful and Epic 6 redesign work can be regime-aware.

## 7. Recommended path forward

**Immediate next: Epic 6 brainstorming** — strategy redesign. From this run's diagnostics, the candidate hypotheses to test (in suggested priority order):

1. **Reduce trade frequency** — raise the confluence threshold to halve trade count (~850 in 1y); evaluate whether fee burn drops faster than gross PnL, lifting net into positive.
2. **Audit LONG signal logic** — find the asymmetry between LONG and SHORT generators. Possibly: same confluence rules being applied to two structurally different markets.
3. **Re-tune R:R** — 60% SL hit rate suggests SL too tight or entry timing too late. Wider SL with tighter TP1, or filter entries more strictly.
4. **Per-symbol whitelist (interim)** — ship a config that only trades a curated subset of symbols where the engine has shown profitability historically; revisit universe expansion later.

**Side tasks before Epic 6 starts implementation:**
- Fix trade-timestamp bug (§6) so future validations have bar-time data
- Decide whether to log trade-level features (regime tag, session, ATR percentile) into trades.csv to help future post-mortem

## 8. What this means for the master roadmap

- **Aşama 1 outcome:** Epic 1a (implementation) ✅ done; Epic 1b (validation) decision = **ITERATE**.
- **Aşama 2 (Epic 3+4) is BLOCKED** until a profitable strategy exists. Self-maintenance + observability for an unprofitable bot serves no track-record purpose.
- **Aşama 3 (track record) is BLOCKED** for the same reason.
- **Aşama 4 (Lead Trader application) is BLOCKED.**
- **Epic 6 is the new critical path** — must produce a strategy variant that clears all 5 currently-failing GO thresholds before the roadmap resumes.

The vision (Pathway X — Binance Lead Trader) is unchanged. The path to it now routes through Epic 6.

## 9. Decision sign-off

This document records the validation outcome for `phase2_1k` as of 2026-05-05. Future Epic 6 variants will produce their own validation runs and decision records under the same naming convention.
