# FVG shadow: SL variant B (operator SL) + canonical NET cost — design (2026-11-14)

**Status:** operator-approved scope (ECC spec §6 item 3 / Fable Ö5; operator 2026-11-14 "sıradaki işleri önerdiğin şekilde yap").
Shadow only — no order path, live v2 untouched.

## Why
`docs/STRATEGY_INTENT.md` step 6: the operator's SL is "the breaking OB candle's far wick ∓ 0.2 %, not ATR" (six
statements). The FVG shadow today uses `calc_sl` (OB anchor ∓ 0.5 ATR, floor 2 ATR, cap 5 ATR,
`engine/smc_v2/fvg_entry.py` build_plans), so even ≥ 30 forward closes would not measure the operator's setup. The
shadow's NET also uses a flat 0.07 % round trip, one of four cost models (ADR-0011 context).

## Design
1. `build_plans(..., sl_mode="atr" | "ob_pct", sl_pct=0.002)`:
   - `atr` = today's `calc_sl` path, byte-identical output.
   - `ob_pct`: LONG `sl = ob.bot × (1 − sl_pct)`, SHORT `sl = ob.top × (1 + sl_pct)`; no ATR floor/cap; skip if
     `risk <= 0`. TP1/TP2 are searched with this plan's own risk (min_rr unchanged).
   - `FvgPlan.variant` = "A" (atr) | "B" (ob_pct); `key` includes the variant.
2. `FvgShadowBook` tracks one open plan per (symbol, direction, variant). Every log line carries ` v=A|v=B`.
3. Canonical NET cost (ADR-0011), from config `backtest:` + `backtest/slippage.py` defaults:
   - commission `backtest.commission_pct` per leg, both legs (entry counted as taker — conservative, no maker fee
     in config);
   - exit slippage: SL and BE `sl_slip_pct` (0.10 %), TP1/TP2 `exit_slip_pct` (0.05 %); limit entry 0;
   - funding `backtest.funding_pct_per_8h` × hours held / 8 (from fill bar to exit bar);
   - `cost_r = cost_pct × entry / risk`; exit lines log `gross_r`, `net_r`, `cost_r`.
4. Config: `smc_v2.fvg_entry_sl_variants` (list; absent → `[atr]` = no behaviour change). Prod config sets
   `[atr, ob_pct]`.
5. `tools/fvg_shadow_report.py` groups by (symbol, variant); lines without `v=` count as A.

## Out of scope
Book persistence across restarts; cost-budget gate (Ö8); any live order path (Ö9, after ADR-0011).

## Tests (TDD)
- ob_pct SL math LONG/SHORT; ATR caps not applied; TP1 uses variant risk.
- `atr` mode output unchanged vs current tests.
- two variants for the same break → two tracks, independent exits, `v=` tags.
- canonical cost: SL vs TP slippage, funding by hold time, `cost_r` value.
- config absent → only A; report groups by variant and accepts legacy lines.
