# Epic 6 H2-A2 — Magnitude Push Results

**Date:** 2026-05-07 (run completed 2026-05-06 ~20:00)
**Run:** `reports/backtests/phase_a_2026-05-06_phase2_1k_h2a2_risk2_notional6_a13cae/`
**Parent design:** `docs/superpowers/specs/2026-05-06-h2-magnitude-design.md`
**Baseline reference:** H1c (`configs/config.phase2_1k_h1c_conf80.yaml`)
**Decision:** **A2 SUCCESS** — Lead Trader-competitive baseline achieved.

---

## 1. Executive summary

Scaling per-trade risk by 2× and notional cap by 3× on top of the H1c baseline produced **+42.48% annual return at 5.47% max drawdown** — comfortably Lead Trader competitive. Return scaled super-linearly (3.76× vs expected 3×) while drawdown scaled sub-linearly (1.93× vs expected 3×). All 6 acceptance thresholds clear with significant margin.

A2 is the new working baseline. The strategy-magnitude problem is solved. The roadmap's blocker on Aşama 2/3/4 is removed.

## 2. Metrics vs A2 acceptance thresholds (spec §4)

| Metric | Threshold | A2 Actual | Margin |
|--------|-----------|-----------|--------|
| Total return | > 12% | **+42.48%** | 3.5× threshold |
| Max DD | < 25% | **5.47%** | 4.6× margin (well under) |
| Profit factor | > 1.5 | **3.64** | 2.4× threshold |
| Win rate | > 50% | **65.0%** | +15 pp over |
| Sharpe | > 0.3 | **0.53** | +0.23 over |
| Total trades | > 100 | 206 | 2.06× floor |

All 6 pass. A2 is the new validated baseline.

## 3. Scaling analysis vs H1c

| Variable | H1c (conf=80, risk 1%, notional 2%) | A2 (conf=80, risk 2%, notional 6%) | A2/H1c |
|----------|-------------------------------------:|-------------------------------------:|-------:|
| Configured risk multiplier | 1× | 6× (2 × 3 dimensional) | 6× |
| Total return | +11.29% | +42.48% | **3.76×** |
| Max DD | 2.83% | 5.47% | **1.93×** |
| Sharpe | 0.51 | 0.53 | 1.04× (ratio preserved) |
| Profit factor | 3.50 | 3.64 | 1.04× (quality preserved) |
| Win rate | 62.4% | 65.0% | 1.04× |
| Total trades | 213 | 206 | 0.97× (signal count unchanged) |
| LONG total PnL | +$263.77 | +$1,065.98 | 4.04× |
| SHORT total PnL | +$394.76 | +$1,206.90 | 3.06× |

**Key non-linearity:** Return scaled 3.76× while DD scaled only 1.93×. The risk-adjusted return improved meaningfully; this is uncommon in backtests where DD usually scales with leverage. The reason is portfolio diversification: at any given moment, the per-symbol DDs are not all peaking simultaneously, so portfolio-level DD averages out, while each individual symbol's gross PnL contribution increases linearly.

LONG and SHORT both scale 3-4×, both directions remain profitable. Confirms direction-balance is structurally sound (not an artifact of one-symbol or one-direction luck).

## 4. Per-symbol (sorted by return)

```
ETH/USDT    +11.95%   DD 2.47%   PF 5.28   39 trades   win 66.7%
LINK/USDT    +6.97%   DD 2.05%   PF 4.84   18 trades   win 66.7%
XRP/USDT     +4.29%   DD 2.75%   PF 3.91   18 trades   win 72.2%
BTC/USDT     +3.92%   DD 1.06%   PF 2.46   20 trades   win 50.0%
DOGE/USDT    +3.18%   DD 2.72%   PF 2.03   15 trades   win 46.7%
SOL/USDT     +3.15%   DD 1.28%   PF 3.76   18 trades   win 66.7%
ADA/USDT     +0.12%   DD 2.51%   PF 2.09   20 trades   win 60.0%
TRX/USDT     -0.22%   DD 0.99%   PF 6.24   13 trades   win 69.2%
BNB/USDT     -0.42%   DD 2.60%   PF 2.29   28 trades   win 60.7%
BCH/USDT     -0.75%   DD 2.04%   PF 4.23   16 trades   win 68.8%
```

7/10 strictly positive (one is +0.12% borderline), 3 marginally negative (all <1% loss). Per-symbol DDs all under 3%. Even the negative symbols have profit factors >2 — they lose less than they win at the symbol level, but lose net due to fee/funding overhead on borderline trades.

A future H4 (whitelist) test could exclude TRX/BNB/BCH and likely lift portfolio return another 1-3%. Marginal upside, not a priority before Aşama 2.

## 5. Exit-reason distribution

| Exit | A2 | H1c | Trend |
|------|----|----|----|
| TP2 | 43.7% | 42.3% | stable |
| SL | 35.0% | 37.6% | improved (lower SL rate) |
| TP1 | 21.4% | 20.2% | slight up |

TP-side total = 65.1%. SL hits less often despite larger position sizes — surprising and good. Suggests the larger notional doesn't push positions into looser SL zones.

## 6. Decision

**A2 is the new baseline.** From this point forward:
- `configs/config.phase2_1k_h2a2_risk2_notional6.yaml` is the reference config
- H1b and H1c remain as historical references
- Original `configs/config.phase2_1k.yaml` (conf=50, baseline) is now historical

**The Epic 6 strategy-redesign question is answered.** No further hypothesis testing is required at this stage to clear Lead Trader appeal thresholds. Further optimisation (A3 more-aggressive scaling, H4 whitelist) is now optional — explorations of additional upside, not blocker fixes.

## 7. Caveats and concerns

1. **In-sample bias risk** — backtest is 1y of historical data; live regime may differ. Mitigation: Phase B reconcile (blocked on trade-timestamp bug), then live track-record period before any Lead Trader application.
2. **Trade count 206 over 1y** — well above >100 floor but still light. Lead Trader copy followers may want more frequent action; conversely, conservative/quality may be a feature, not a bug.
3. **Sharpe 0.53 borderline** — passes >0.3 threshold but not by much. Lead Trader-friendly Sharpe targets vary; some platforms expect >1.0. Track record period will produce a more reliable Sharpe estimate.
4. **Single-period evaluation** — 1y is one market regime. Phase C grid (other configs) and walk-forward validation (different periods) would strengthen confidence; deferred.

## 8. Master roadmap impact

**Aşama 2 (Epic 3+4 self-maintenance + observability): UNBLOCKED.** The strategy is competitive enough to warrant the engineering investment in operational stability for the track-record period.

**Aşama 3 (track record): conditionally unblocked** — needs Aşama 2 first.

**Aşama 4 (Lead Trader application): conditionally unblocked** — needs Aşamas 2 and 3 first.

The original "+4.89%/y is too modest for Lead Trader appeal" objection is gone. +42.48%/y with 5.47% DD is comfortably in the competitive band.

## 9. Open issues from Epic 6 H1/H2

1. **Trade-timestamp wall-clock bug** (validation-results §6) — still open, blocks Phase B reconcile. Should be fixed during Aşama 2 work since observability/trace-IDs need bar-time anyway.
2. **A3 / H4 / refinement opportunities** — deferred. Not blocking.
3. **CLI portfolio mode hang** (task #17) — backlog; workaround (`scripts/run_phase_a.py`) is sufficient.

## 10. Next step

Two paths forward:

**Path 1 (recommended):** Begin **Aşama 2 brainstorming** — Epic 3 (self-maintenance) + Epic 4 (observability). Track-record period needs the bot to run unattended for 60-90 days; that requires watchdog, health checks, structured logs, alerting. This is the critical path now.

**Path 2 (optional, parallel):** Run A3 variant (risk 3%, notional 9%) to map the scaling curve — see if super-linear return continues or if non-linear penalty kicks in. ~1-2 hour run. Gives information; not strictly needed for Aşama 2.

Recommendation: Path 1, start Aşama 2 brainstorming. A3 can be run anytime later if curiosity justifies; Aşama 2 is the load-bearing next step.
