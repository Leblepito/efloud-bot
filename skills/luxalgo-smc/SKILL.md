---
name: luxalgo-smc
description: Reference for the LuxAlgo "Smart Money Concepts" logic as ported in efloud-bot (engine/smc_v2/luxalgo.py) — swing/internal BOS & CHoCH, order blocks and mitigation, FVG, EQH/EQL, premium/discount zones, strong/weak highs-lows, how the engine turns them into setups and TP targets, the live config, monitoring commands and the licence constraint. Use when analysing a chart, explaining a setup, proposing SMC rule changes or porting to Pine.
---

# LuxAlgo SMC in efloud-bot

Source of truth is the code, not this page: `engine/smc_v2/luxalgo.py`
(bar-by-bar port of TradingView script `CnB3fSph`, "Smart Money Concepts (SMC)
[LuxAlgo]"), tests in `tests/engine/test_luxalgo.py`. If this page and the code
disagree, the code wins — fix the page.

## Licence — read first

The original script is published under **CC BY-NC-SA 4.0** (attribution,
**non-commercial**, share-alike). The port is enabled on the live mainnet config
and u2algo is a commercial product. Whether this use is permitted is an open
**operator/legal decision**, not something a role may assume. Until decided:
do not copy this logic into published or sold Pine scripts, marketing material
or customer-facing products, and flag any change that would widen its use.

A copy of the LuxAlgo script whose copyright line was changed to another name
(e.g. "© u2Algo", reviewed 2026-11-03: same functions, defaults and title
`Smart Money Concepts [LuxAlgo]`) is still LuxAlgo's work: it does not change the
licence, and removing the original attribution breaches the BY term. Never adopt
or publish such a file as u2Algo's own.

## Processing order per closed bar (matches Pine)

`deleteOrderBlocks(internal)` → `deleteOrderBlocks(swing)` →
`getCurrentStructure(swing_length)` → `getCurrentStructure(internal_length, internal)` →
`getCurrentStructure(eq_length, equal)` → `displayStructure(internal)` →
`displayStructure(swing)` → `updateTrailingExtremes` → FVG.

## Concepts (as implemented)

- **Pivot / leg(size):** bar[t-size].high > highest(high, size) → bearish leg (pivot
  HIGH); bar[t-size].low < lowest(low, size) → bullish leg (pivot LOW). Recorded only
  when the leg flips; confirmed `size` bars later → no lookahead, but **a swing
  pivot is known 50 bars late** with prod `swing_length: 50`.
- **BOS / CHoCH:** close crosses a not-yet-crossed pivot level. Against the current
  trend bias → CHoCH, with it → BOS. An internal break is ignored when the internal
  pivot equals the swing pivot.
- **Order block:** at the break, the extreme candle in [pivot bar, break-1]: BULL →
  lowest parsed low, BEAR → highest parsed high. Parsed high/low swap on
  high-volatility candles (range ≥ 2×ATR(200)) — the "Order Block Filter" (`ATR`
  or cumulative mean `RANGE`).
- **Mitigation:** `HIGHLOW` (prod) — BULL OB dies when low < OB bottom, BEAR OB when
  high > OB top; `CLOSE` uses close instead.
- **EQH/EQL:** `leg(eq_length)` pivots within `eq_threshold × ATR(200)` of each other.
- **FVG:** low > high[2] and close[1] > high[2] (bear mirror) and bar delta % above
  the auto threshold.
- **Premium/Discount:** from trailing top/bottom — premium [0.95t+0.05b, t],
  equilibrium [0.475…, 0.525…], discount [b, 0.95b+0.05t].
- **Strong/Weak:** swing trend BEAR → top is the Strong High; BULL → bottom is the
  Strong Low.

## From concepts to engine setups (`generate_candidates`)

1. Break direction must equal the HTF bias (BULL/BEAR; UNDEF → nothing).
2. `kinds` filter (prod: CHoCH and BOS), `use_internal` / `use_swing` (prod: both).
3. The break's OB must exist and be unmitigated.
4. `require_premium_discount` (prod: on): LONG only from an OB below equilibrium,
   SHORT only above.
5. Confluence tags on the OB (`zone_confluence`): `SWING_OB` (swing-scope break),
   `OTE` (overlaps 0.618–0.786 retracement), `EQ` (overlaps equilibrium band),
   `FVG` (same-direction unfilled FVG formed after the OB overlaps it), `SWEEP` (OB
   took the prior swing pivot's liquidity). Need ≥ `min_confluence` (prod: 1).
6. Candidate = `AWAITING_PULLBACK` into the OB zone; SL anchor = OB extreme; score =
   10 for swing scope + number of tags. Pullback timeout `pullback_timeout_bars`
   (prod: 48); entry distance capped by `smc_v2.max_entry_dist_atr` (prod: 12.0).

## TP targets (`tp_targets`, `tp_mode: luxalgo`)

Candidates beyond entry: opposite OB near edge, opposite FVG, EQH/EQL and swing
liquidity (pulled inside by `tp_wick_buffer_r` × risk, prod 0.15), equilibrium,
trailing extreme. TP1 = nearest candidate meeting `min_rr`; TP2 = next one strictly
beyond, else fib extension (1.272/1.618/2.618 of the range). Candidates exist but
none meets `min_rr` → `InsufficientTPDistanceError` (no trade); no candidates → RR
projection.

## Live config (`configs/config.phase2_1k.yaml` → `smc_v2.luxalgo`)

`enabled: true`, `swing_length: 50`, `internal_length: 5`, `eq_length: 3`,
`eq_threshold: 0.1`, `ob_filter: ATR`, `ob_mitigation: HIGHLOW`,
`internal_confluence_filter: false`, `fvg_auto_threshold: true`, `use_internal`,
`use_swing`, `require_premium_discount: true`, `kinds: [CHoCH, BOS]`,
`tp_mode: luxalgo`, `min_confluence: 1`, `tp_wick_buffer_r: 0.15`,
`pullback_timeout_bars: 48`. Re-read the file before quoting — it changes.

## Monitoring

```
docker logs -f --since 10m efloud-bot 2>&1 | docker exec -i efloud-bot python scripts/lux_monitor.py follow
docker logs --since 24h efloud-bot 2>&1 | docker exec -i efloud-bot python scripts/lux_monitor.py report
docker exec efloud-bot python scripts/lux_monitor.py state
```

Scan log lines look like `[lux] scan <SYM> htf_bias=… ltf_swing=… ltf_internal=…
last_break=… active_obs=… cands=…`.

## Pitfalls

- Never analyse the still-forming candle; the engine uses closed bars only.
- Swing structure lags by `swing_length` bars; do not "see" a swing break on the
  chart that the engine cannot know yet.
- The TradingView indicator's visuals (e.g. "present" vs "historical" mode, drawn
  boxes) are not the engine; compare numbers from `analyze()`, not screenshots.
