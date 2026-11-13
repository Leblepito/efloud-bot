# FVG pullback entry: 4h bias, OB-anchored SL, OB/BB TP1, liquidity TP2 (shadow) — design

**Date:** 2026-11-14 · **Status:** operator-approved. The operator chose "Geri çekilmede FVG limit" and "Önce gölge,
sonra canlı".

## Why

The operator asked why the bot sends "📍 Fiyat bölgede — bot teyit mumu bekliyor" but opens no position, and whether
the live algorithm matches their setup.

### Live behaviour (logs, 2026-11-08 → 13)

Lifecycle counts:

| Stage | Count |
|---|---|
| setups | 215 |
| zone touches | 77 |
| confirmations | 22 |
| orders | 9 |

- 11 confirmations were rejected by `pos_guard` (exposure over 6x) and 2 by the breaker.
- The Po3 gate blocked 25 times.
- On ETH (zone `[1953.02-1959.6]`, 2026-11-13 20:00), price touched the lower edge and then fell out. No 15m bullish
  engulfing closed inside the zone, so `confirmation.py` never confirmed.

### The operator's setup against the live logic

| Rule | Operator | Live (`smc_v2.luxalgo.enabled: true`) |
|---|---|---|
| Bias | 4h for a 15m entry | 12h LuxAlgo swing trend (profile `mid` HTF = 12h, `swing_length` 50) |
| Trigger | CHoCH/BOS | CHoCH + BOS in the bias direction ✅ |
| Entry zone | the FVG left by the break | the break's order block; FVG is only a confluence tag |
| Entry trigger | limit on the pullback into the FVG | 15m engulfing close inside the zone, then MARKET |
| SL | a little beyond the OB candle that made the break | OB extreme − 0.5 ATR, floor 2 ATR ✅ |
| TP1 | next OB / BB | nearest of opposite OB, FVG, EQH, pivot, equilibrium, trail top |
| TP2 | liquidity in the trade direction | any next candidate beyond TP1 (ETH: TP1 2077.41, TP2 2077.81) |

## What this change does

It adds a **shadow** path that runs the operator's setup next to the live path and logs what it would have done.
- It places no orders, changes no live state and is invisible to the live entry path.
- It sits behind the new key `smc_v2.fvg_entry: off | shadow`; absent or unknown means `off`. A `live` value is
  deliberately not accepted yet.
- The live LuxAlgo path is untouched.

### Setup rules (pure function `engine/smc_v2/fvg_entry.py::build_plans`)

1. **Bias.** LuxAlgo `swing_trend` on the **4h** frame (`df_mtf`, profile `mid`), same `LuxConfig` as the live path.
   A bias of `UNDEF` means no plans.
2. **Break.** Every 15m LuxAlgo break (CHoCH or BOS, internal or swing) that:
   - points in the bias direction;
   - lies within `risk.recency_bars`;
   - has an order block.
3. **FVG.** The newest same-direction LuxAlgo FVG with `ob.idx < fvg.idx <= break.idx + 2` (the displacement that
   made the break), not yet mitigated. If there is none, there is no plan; there is no fallback to the OB.
4. **Entry.** A limit at the FVG near edge: LONG at `fvg.top`, SHORT at `fvg.bot`. It fills on the first 15m bar
   whose wick reaches it.
5. **SL.** `calc_sl(direction, entry, zone=FVG, htf_swing_anchor=OB extreme, atr15m, safety)`. This is the same
   function, buffer (`sl_atr_buffer` 0.5) and floor/ceiling (`min_sl_atr` 2, `max_sl_atr` 5) as live. `SLTooFarError`
   means no plan.
6. **TP1.** The nearest **opposite OB or breaker** beyond entry with at least `risk.min_rr` (1.8) × risk.
   - LONG: active BEAR OB `bot`, or mitigated BULL OB `bot` (a bullish OB broken through is a bearish breaker).
   - SHORT: mirror.
   - No such level means no plan.
7. **TP2.** The nearest **liquidity** in the trade direction at least 0.5 R beyond TP1:
   - LONG: EQH `price_b` or swing-high pivot, less `tp_wick_buffer_r` × risk;
   - SHORT: EQL `price_b` or swing-low pivot, plus `tp_wick_buffer_r` × risk.

   With none, TP2 is `None` and the whole position exits at TP1, as live does for `tp2 is None`.

### Shadow lifecycle (`FvgShadowBook`, in memory, per orchestrator)

The book runs once per closed 15m bar, per symbol, after the live LuxAlgo scan, inside `try/except`. An error logs a
warning and never touches the live path.

Each plan is identified by (symbol, direction, break bar ts, FVG idx ts) and is logged once at creation:
`[fvg shadow] setup+`. The bars after the plan's creation bar are then walked:

| State | Event on a bar | Result |
|---|---|---|
| pending | wick reaches entry | `filled` |
| pending | price reaches TP1 before entry | `cancelled` (ran away) |
| pending | `smc_v2.luxalgo.pullback_timeout_bars` (48) bars pass | `expired` |
| filled | SL and TP on the same bar | SL first (conservative) |
| filled | TP1 hit, TP2 set | 50 % closes; SL moves to entry (mirrors `lifecycle.py`) |
| filled | TP2 or BE stop | `exit` |

- Only the `filled` row and the `exit` row log anything.
- There is no separate "invalidated" state: price cannot close beyond the SL without first reaching the limit entry, so that case is a fill followed by a stop.
- On the bar that reaches TP1, a touch of the break-even stop counts before TP2.
- A plan skipped because its (symbol, direction) is busy is not retried later.
- Backtests force the key `off` (`backtest/engine.py::_offline_run_config`); the shadow costs a second LuxAlgo pass per bar.
- The `exit` line carries `gross_r` and `net_r`. `net_r` subtracts a round-trip cost of 0.07 % of notional
  (maker entry + taker exit), expressed in R.
- One open plan per (symbol, direction); a newer plan for a busy key is skipped.
- Restart loses the book. That is accepted for a shadow.

## Report and the go-live bar

`tools/fvg_shadow_report.py` reads the log lines (from a file or stdin) and prints, per symbol and in total:
- counts per state;
- closed trades and win rate;
- average gross and net R.

To switch to live (a later, separate PR with its own review), all of these must hold:
- ≥ 30 closed shadow trades;
- net avg R > 0;
- net avg R above the live v2 trades over the same dates.

This is the same bar `touch_entry` already states.

## Out of scope

- Any change to the live entry, SL or TP.
- Persisting the shadow book, and Telegram messages for shadow events.
- The exposure cap (`pos_guard` 6x) and the Po3 gate. They are reported here for the operator only.

## Tests (no network)

- `build_plans`, on synthetic `LuxResult` objects:
  - the bias filter, and `UNDEF`;
  - FVG selection in its window, and no FVG means no plan;
  - the LONG and SHORT entry edge;
  - SL equals `calc_sl` with the OB anchor;
  - TP1 picks the OB or breaker and respects `min_rr`;
  - TP2 picks liquidity ≥ 0.5 R beyond TP1, or `None`.
- `FvgShadowBook`, on synthetic bars: fill; ran-away cancel; invalidation; expiry; SL-first on the same bar;
  TP1 → BE → BE exit; TP1 → TP2; single-target TP1; dedup; one open plan per key; `net_r` < `gross_r`.
- The orchestrator hook:
  - `off` does not call the book;
  - `shadow` calls it;
  - an exception inside the book does not propagate.
- The report parses lines and aggregates them.
