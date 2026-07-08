# C4 — NET-cost min_confluence sweep (2026-07-08)

**Audit finding:** `docs/handoff/2026-06-20-algorithm-audit-and-next-session-plan.md` C4 —
live `min_confluence: 55` sits between two GROSS-only figures quoted in
`configs/config.phase2_1k.yaml:101-105` (conf=50 → PF 1.35, conf=80 → PF 2.34),
themselves traced (via `docs/audit/03_strategy_review.md:35-48`) to an ad-hoc,
**uncommitted** script (`c:\tmp\verify_s1.py`) that explicitly excluded
commission/funding. Audit direction: "NET-cost conf sweep on the Edge
Measurement Core (PR #227); raise toward 80 or justify 50/55 with NET + OOS
evidence."

## What this run is (and isn't)

This is a **real** run of the production backtest engine
(`backtest.engine.run_backtest`) against **real** cached OHLCV data
(`cache/ohlcv/`, 2025-05-15..2026-05-14), with a **real** NET-cost model
enabled (`commission_pct=0.04`% round-trip taker + `funding_pct_per_8h=0.01`%
average symmetric drag) — not a re-estimate, not the ad-hoc gross-only script.

It is **not** the full-scope sweep the audit and
`configs/grids/confluence_x_notional.yaml` envisioned (10 symbols x 300+ days).
The sandbox this was run in has 2 CPU cores and a ~45s ceiling per command
with no persistent background execution; the engine's per-bar position
lifecycle bookkeeping gets materially heavier once real trades are open, so a
90-day single-symbol run did not finish in 45s while 75 days did (~9-12s).
Scope was capped accordingly. Tool: `scripts/c4_confluence_sweep.py` (checked
into the repo so a full run can be reproduced on unconstrained hardware —
parallelize across symbols/confluence values for a real production pass).

## Results (75-day window ending 2026-07-08, historical 4h/1h/15m chain)

| Symbol | conf | trades | PF | return% | maxDD% | commission | funding |
|---|---|---|---|---|---|---|---|
| BTC/USDT | 50 | 15 | 2.50 | 0.80 | 0.29 | 2.42 | 0.26 |
| BTC/USDT | 55 | 14 | 3.19 | 0.92 | 0.29 | 2.26 | 0.24 |
| BTC/USDT | 80 |  6 | 2.43 | 0.35 | 0.29 | 0.96 | 0.18 |
| ETH/USDT | 50 |  8 | 1.41 | 0.24 | 0.45 | 1.28 | 0.36 |
| ETH/USDT | 55 |  8 | 1.39 | 0.23 | 0.45 | 1.28 | 0.36 |
| ETH/USDT | 80 |  6 | 2.40 | 0.39 | 0.32 | 0.96 | 0.04 |

## Interpretation — directional signal only, not a verdict

Sample sizes (6-15 trades per cell) are **far too small** for a statistically
significant PF comparison — this does not reproduce or refute the original
PF 1.35/2.34 claim, which was itself never NET-cost or OOS-validated either.

One thing worth flagging to the operator: **conf=80 was the most
cross-symbol-consistent** cell (PF 2.43 BTC / 2.40 ETH — nearly identical),
while conf=50/55 varied much more across the two symbols (BTC PF 2.5-3.2 vs
ETH PF 1.4). Consistency across independent instruments is a weak but
directionally suggestive signal that conf=80's edge is less symbol-specific
noise than conf=50/55's — in the same direction as the audit's original
(gross, ad-hoc) recommendation, though this run does not show conf=50/55 as
badly as PF 1.35.

## Recommendation

Do not change the live `min_confluence: 55` off this run alone — the sample
is too small. Two honest options for the operator:
1. **Run the full sweep** (`scripts/c4_confluence_sweep.py --symbols
   BTC/USDT,ETH/USDT,...,10 symbols --period-days 300+`) on unconstrained
   hardware (a normal PC/VPS, not this sandbox) to get a statistically usable
   sample before touching the live value.
2. **If a decision is needed now**, this run's only signal (cross-symbol PF
   consistency favoring higher confluence) points the same direction as the
   audit — a nudge toward 65-80 would be the lower-risk move — but this is a
   judgment call for the operator to make explicitly, not something to apply
   silently from a 2-symbol/75-day sample.
