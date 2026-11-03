---
name: plan-replay
description: Monte Carlo odds for a crypto trade plan (entry, stop, target) on Binance USDT-M bars — how often the target comes first vs the stop within a horizon, NET of fees, plus the same plan replayed on every past day at the same time of day. Use to sanity-check an SL/TP placement, compare TP candidates, or put numbers on a strategist proposal. Research only; never places orders.
license: MIT (adapted from day-trader-skill trader-timemachine; see THIRD_PARTY_NOTICES.md)
---

# Plan replay

Adapted from day-trader-skill's Time Machine (MIT, Jake Schincariol) for 24/7
crypto: UTC time-of-day slots instead of NYSE sessions, a horizon in bars
instead of the close, longs and shorts, fees folded into R. Code:
`scripts/desk/plan_replay.py`, tests: `tests/desk/test_plan_replay.py`.

```bash
python scripts/desk/plan_replay.py --symbol BTC/USDT --tf 15m --side long \
    --entry 68000 --stop 67300 --target 69400 --horizon 96            # 24h on 15m
python scripts/desk/plan_replay.py ... --json                         # machine-readable
python scripts/desk/plan_replay.py ... --offline klines.json          # saved Binance kline rows
```

Flags: `--days 60` (history pulled from the public klines endpoint, no key),
`--replays 10000`, `--seed 19`, `--window 2` (slot jitter), `--fee-pct 0.04`
(per side, matches `backtest.commission_pct`).

## How it works

1. **Pool.** Each closed bar → (o, h, l, c) / previous close, filed under its UTC
   slot of the day. Only consecutive bars count; the still-forming bar is dropped.
2. **Replay.** From the entry, draw `horizon` bars from the same slots (± window,
   wrapping midnight), scale to the running price, check **stop first**, then
   target. A bar touching both counts as the stop (conservative).
3. **Odds.** Target first / stop first / neither (still open at the horizon) and
   average NET R. Fees: `cost_R = 2 × fee% × entry / risk`.
4. **History.** The plan's % geometry entered at the same slot on every past day,
   walked forward on real bars — what really happened, not a simulation.
5. **Verdict.** Break-even share of the replays that hit a side is
   `(1 + cost_R) / (1 + R_target)`. Within 5 points → coin flip / break-even;
   5–15 → leans; ≥15 → strongly.

## Reading it

- Quote the seed, horizon, timeframe, data window and last closed bar with every
  number. Same inputs + seed = same numbers on any machine.
- It is a bootstrap of the symbol's own recent bars, not a forecast. Regime
  changes, funding, gaps through the stop and slippage are not modelled (a gap
  through the stop still counts as −1R − fees here; a real fill can be worse).
- It does not know SMC structure. Use it to price an SL/TP geometry, not to pick
  direction. Direction comes from the engine's rules.
- Refusals are answers: fewer than 20 days of data, stop/target on the wrong
  side, risk under 0.05 % of price.

## Who uses it

`strategist` (before/after evidence for TP or SL changes), `risk-manager`
(sanity check on a ticket's geometry), `trade-reviewer` (was the planned R
realistic?). Output goes in the handoff, never into config directly.
