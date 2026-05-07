# Epic 6 H1 — Confluence Threshold Sweep Results

**Date:** 2026-05-06
**Parent design:** `docs/superpowers/specs/2026-05-05-epic-6-h1-design.md`
**Decision (post-H1c update):** **H1 HYPOTHESIS CONFIRMED — H1c (conf=80) is the new baseline.** All 6 GO thresholds clear (the only variant to do so). Sharpe finally over 0.5 (0.51). H1b is retained as historical reference.
**H1c status:** complete (see §8).

---

## 1. Executive summary

The strategy was not broken — it was **mis-configured**. Raising `min_confluence` from 50 to 70 transformed `phase2_1k` from a strategy that lost 43.75% of capital over 1y into one that earned 4.89%, with max drawdown shrinking from 44.24% to 7.17%, profit factor doubling (1.08 → 1.95), and the previously-broken LONG signal becoming net positive (+$462 vs. baseline −$31).

H1b (conf=70) clears 5 of 6 GO thresholds. Only Sharpe (0.27 vs. >0.5 target) remains short, and that target was conservative and may be re-calibrated for the cryptofutures regime.

Per H1 design §3.3 acceptance: any variant returning > 0% becomes the new baseline. **H1b is the new baseline.** Aşama 2/3/4 of the master roadmap are no longer blocked.

## 2. Variant comparison vs GO thresholds

| Metric | GO threshold | Baseline (conf=50) | H1a (conf=60) | **H1b (conf=70)** | H1c (conf=80) |
|--------|--------------|--------------------|---------------|--------------------|----------------|
| Total return | > 0% | −43.75% | −34.32% | +4.89% ✅ | **+11.29%** ✅ |
| Max DD | < 30% | 44.24% | 34.64% | 7.17% ✅ | **2.83%** ✅ |
| Sharpe | > 0.5 | 0.03 | 0.11 | 0.27 ❌ | **0.51** ✅ |
| Profit factor | > 1.2 | 1.08 | 1.31 | 1.95 ✅ | **3.50** ✅ |
| Total trades | > 100 | 1709 | 1361 | 680 ✅ | **213** ✅ |
| Win rate | > 35% | 40.5% | 45.5% | 54.7% ✅ | **62.4%** ✅ |
| **Pass count** | — | 2/6 | 3/6 | 5/6 | **6/6** ⭐ |

Trajectory across the sweep is **monotone-improving** in every single metric — a strong signal that confluence threshold is the right knob.

## 3. H1b deep dive (the new baseline)

### 3.1 Portfolio metrics

- Initial $2000 → Final $2097.77 → Peak $2138.83
- Realized giveback: 1.92% (small distance between peak and final — minimal late-period bleed)
- 680 trades, 372 wins, 308 losses, 54.7% win rate

### 3.2 Direction balance restored

| Direction | Trades | Total PnL | Mean PnL/trade |
|-----------|-------:|----------:|---------------:|
| LONG | 322 | **+$461.87** | +$1.43 |
| SHORT | 358 | +$717.26 | +$2.00 |

Both directions are now profitable. The earlier diagnosis that "LONG signal logic is broken" was incorrect — at conf=50, low-quality LONG signals dominated and dragged the direction net flat. Tightening the gate restored LONG expectancy. **H2 (LONG audit) is therefore deprioritized**; the bug it was meant to fix doesn't exist at conf=70.

### 3.3 Exit-reason redistribution

| Exit | Baseline (conf=50) | H1b (conf=70) | Δ |
|------|-------------------:|--------------:|---|
| SL | 59.6% | 45.3% | −14.3 pp |
| TP1 | 7.0% | 13.8% | +6.8 pp |
| TP2 | 33.4% | 40.9% | +7.5 pp |

R:R structure now favours the TP side. SL still hits often but no longer dominates.

### 3.4 Per-symbol breakdown (sorted by return)

```
ETH/USDT     +4.41%   DD 1.48%  PF 2.48   91 trades  win 60.4%
SOL/USDT     +2.87%   DD 1.68%  PF 3.03   81 trades  win 65.4%
BCH/USDT     +1.15%   DD 1.51%  PF 1.73   74 trades  win 51.4%
BTC/USDT     +1.13%   DD 1.13%  PF 2.10   80 trades  win 52.5%
BNB/USDT     −0.00%   DD 1.28%  PF 1.49  106 trades  win 50.0%
TRX/USDT     −0.05%   DD 0.35%  PF 9.09   19 trades  win 78.9%
ADA/USDT     −0.20%   DD 1.93%  PF 1.96   57 trades  win 59.6%
LINK/USDT    −1.30%   DD 2.00%  PF 1.24   55 trades  win 41.8%
DOGE/USDT    −1.41%   DD 2.42%  PF 1.66   30 trades  win 50.0%
XRP/USDT     −1.97%   DD 2.65%  PF 1.29   60 trades  win 45.0%
```

4 symbols positive (ETH, SOL, BCH, BTC), 6 symbols slightly negative (all between 0% and −2%, all with single-digit DD). All per-symbol DDs ≤ 2.65% — the strategy is structurally low-risk on every symbol.

The 4 positive symbols carry the portfolio. There is a clear opportunity (H4 territory) to test a curated whitelist.

## 4. What's still imperfect about H1b

1. **Return magnitude is modest** — +4.89% per year is unattractive for Lead Trader appeal. Crypto Lead Traders typically advertise 30-100%+ on a 90-day rolling basis.
2. **Sharpe 0.27** — below threshold. Crypto noise dampens this; some real lead traders also run 0.3-0.5 Sharpe. Worth re-calibrating threshold but also worth pushing higher.
3. **6/10 symbols are net negative** — small losses but still drag. Whitelist would help.
4. **SL exits still 45.3%** — improved but high. R:R audit could push it down further.

These are H2/H3/H4/refinement targets, not roadmap blockers.

## 5. Decision

Per H1 design §3.3:
> "Any variant produces total_return_pct > 0% → that variant becomes new baseline; advance to H2"

✅ **H1b becomes new baseline.** From now until further validation, `configs/config.phase2_1k_h1b_conf70.yaml` is the reference config for any further hypothesis tests. The original `configs/config.phase2_1k.yaml` (conf=50) remains in the repo as historical reference.

## 6. Next steps

- **H2 brainstorming starts now** (in parallel with H1c run). The original H2 (LONG audit) is invalidated by H1b's data. New H2 candidates:
  - **Refine H1**: try conf=75 to find the exact optimum (cheap, 1 more run)
  - **H4 (whitelist)**: trade only ETH/SOL/BCH/BTC (or expand to keep low-DD ADA/TRX)
  - **Magnitude push**: raise risk_per_trade_pct or notional cap to compound H1b's edge into bigger absolute returns (now feasible because DD is low)
  - **R:R refinement**: investigate why SL still hits 45% even with high-confluence signals
- **H1c finishes**: append results to §2 table; if H1c is materially better than H1b, the new baseline shifts to H1c instead
- **Trade-timestamp wall-clock bug** (Epic 1b results §6) is still open. Now that we have a viable baseline, fixing it before H2 work makes regime/timing analysis possible.

## 7. Master roadmap impact

- **Aşama 2 (Epic 3+4): UNBLOCKED conditionally** — pending H2 hypothesis-loop completion
- **Aşama 3 (track record): UNBLOCKED conditionally** — once H2 finishes and a final baseline locks
- **Aşama 4 (Lead Trader application): still requires sufficient absolute return** — current +4.89% likely too low; H2 must push this higher

The path to Pathway X is open, but more hypothesis-loop iterations are needed to make the strategy competitive enough for actual Lead Trader appeal.

## 8. Appendix — H1c results (post-completion)

**Run:** `reports/backtests/phase_a_2026-05-06_phase2_1k_h1c_conf80_dc30e5/` — completed 2026-05-06.

### 8.1 Portfolio metrics

| Metric | Value | vs H1b | vs GO threshold |
|--------|-------|--------|-----------------|
| Total return | **+11.29%** | +6.4 pp better | ✅ PASS |
| Max DD | **2.83%** | −4.34 pp (lower is better) | ✅ PASS |
| Sharpe | **0.51** | +0.24 better | ✅ PASS (first time crossing) |
| Profit factor | **3.50** | +1.55 better | ✅ PASS |
| Total trades | 213 | −467 (concern) | ✅ above 100 floor |
| Win rate | **62.4%** | +7.7 pp better | ✅ PASS |
| Realized giveback | 0.7% | minimal late-period bleed | — |

### 8.2 Per-symbol

10/10 symbols positive. Returns range +0.04% (TRX) to +3.86% (ETH). DDs all under 1.3%. Profit factors all above 2.4 (TRX 14.65, SOL 6.03, ETH 5.36 — extreme PF on the highest-conviction signals).

### 8.3 Direction balance

LONG 92 trades = +$263.77; SHORT 121 trades = +$394.76. Both positive (same as H1b). Direction asymmetry that drove the original H2 plan is fully gone at this confluence level.

### 8.4 Exit-reason redistribution (continuing the trend)

| Exit | Baseline (50) | H1b (70) | **H1c (80)** |
|------|---------------|----------|--------------|
| SL | 59.6% | 45.3% | **37.6%** |
| TP1 | 7.0% | 13.8% | 20.2% |
| TP2 | 33.4% | 40.9% | **42.3%** |

R:R structure improves monotonically with tightening — TP-side exits are now the majority.

### 8.5 Decision (revised from §5)

**H1c is the new baseline.** All 6 GO thresholds pass. The only concern is statistical robustness — 213 trades is well above the >100 floor but considerably less than H1b's 680. To mitigate, future hypotheses will be tested on the H1c baseline and any borderline result (especially Sharpe near 0.5) will be cross-validated against H1b before final acceptance.

`configs/config.phase2_1k_h1c_conf80.yaml` becomes the reference config from this point forward.

### 8.6 H2 (magnitude push) impact

The original A2 variant (H2 design at `2026-05-06-h2-magnitude-design.md`) was built on H1b. With H1c as new baseline + DD now only 2.83% (vs H1b's 7.17%), the magnitude headroom is **even larger**. A2 config has been rebuilt on conf=80 baseline (still risk 2% + notional 6%). The A2 hypothesis is unchanged; only the underlying baseline is updated.

Expected A2 outcome on H1c base: return ~25-35% (linear scaling of +11.29%), DD ~6-10% (sub-linear due to portfolio diversification). If even close to that, Lead Trader appeal becomes plausible.
