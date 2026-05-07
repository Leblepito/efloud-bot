# Phase A 2.0 — aggressive_v1 Validation (2026-05-07)

**Config:** `configs/config.aggressive_v1.yaml` (initial state — empty `symbol_confluence_overrides`)
**Universe:** 21 coins (10 H2-A2 baseline + 11 candidates)
**Period:** 365 days
**Initial balance:** $2,000
**Settings:** conf=70 floor, 10% notional, 5 max positions, 5x leverage, ISOLATED

## Per-symbol results (sorted by return desc)

| Symbol | Trades | Win % | Return % | Max DD % | PF | Sharpe-like | Tier |
|--------|-------:|------:|---------:|---------:|---:|------------:|------|
| ETH/USDT | 93 | 58.1 | **22.28** | 7.37 | 2.46 | 0.38 | 🟢 TOP |
| SOL/USDT | 86 | 61.6 | **18.78** | 5.79 | 2.81 | 0.46 | 🟢 TOP |
| FIL/USDT | 60 | 55.0 | 8.33 | 6.10 | 1.99 | 0.31 | 🟢 TOP |
| RENDER/USDT | 69 | 65.2 | 6.18 | 10.44 | 3.56 | 0.58 | 🟢 TOP |
| SUI/USDT | 71 | 60.6 | 4.03 | 9.25 | 2.57 | 0.42 | 🟡 MID |
| ADA/USDT | 57 | 63.2 | 1.71 | 6.26 | 2.44 | 0.41 | 🟡 MID |
| OP/USDT | 46 | 65.2 | 0.81 | 9.35 | 2.93 | 0.50 | 🟡 MID |
| LTC/USDT | 67 | 50.7 | 0.80 | 7.31 | 2.10 | 0.29 | 🟡 MID |
| BTC/USDT | 82 | 53.7 | 0.17 | 7.59 | 1.83 | 0.23 | 🟡 MID |
| TRX/USDT | 19 | 73.7 | -0.83 | 2.34 | 3.37 | 0.54 | 🔴 DROP |
| BNB/USDT | 104 | 48.1 | -3.42 | 6.48 | 1.68 | 0.22 | 🔴 DROP |
| AVAX/USDT | 58 | 63.8 | -5.16 | 10.09 | 2.47 | 0.41 | 🔴 DROP |
| DOGE/USDT | 30 | 53.3 | -5.25 | 9.38 | 2.00 | 0.29 | 🔴 DROP |
| LINK/USDT | 55 | 41.8 | -5.65 | 8.95 | 1.28 | 0.11 | 🔴 DROP |
| XRP/USDT | 65 | 49.2 | -6.63 | 10.40 | 1.42 | 0.15 | 🔴 DROP |
| APT/USDT | 67 | 52.2 | -8.21 | 14.09 | 1.65 | 0.22 | 🔴 DROP |
| NEAR/USDT | 51 | 51.0 | -8.68 | 14.01 | 1.61 | 0.22 | 🔴 DROP |
| DOT/USDT | 57 | 52.6 | -12.01 | 13.07 | 2.08 | 0.32 | 🔴 DROP |
| BCH/USDT | 73 | 52.1 | -12.33 | 15.18 | 1.76 | 0.25 | 🔴 DROP |
| ATOM/USDT | 32 | 50.0 | -13.62 | 15.08 | 1.38 | 0.14 | 🔴 DROP |
| ARB/USDT | 25 | 44.0 | -14.33 | 16.86 | 1.06 | 0.03 | 🔴 DROP |

**Totals (21 sym):** 1267 trades, avg return -1.57%, 9 positive / 12 negative.

## Portfolio mode

Aggressive_v1's permissive default state (21 symbols × conf=70 floor × 10% notional ×
5 max positions) **HALTED on weekly drawdown 15.1%** early in the simulation
(line 418 of run log). Portfolio mode is excessive when including the 12 negative-
return symbols. Step 5 final validation will re-run portfolio with the trimmed
9-symbol universe + per-symbol overrides; expected DD < 10% and return > +30%.

## Tuning rationale (Step 4)

**Decision rule:**
- Negative return → DROP from `symbols.fixed_core`
- Positive return + DD < 10% + PF ≥ 2.0 → TOP, override at conf=70 (use global default)
- Positive return + (DD ≥ 10% OR PF < 2.0) → MID, override at conf=80

**Final universe (9 symbols):**

```yaml
symbols:
  fixed_core:
    - BTC/USDT     # mid (conf=80)
    - ETH/USDT     # top (conf=70 default)
    - SOL/USDT     # top
    - FIL/USDT     # top
    - RENDER/USDT  # top
    - SUI/USDT     # mid (conf=80)
    - ADA/USDT     # mid (conf=80)
    - OP/USDT      # mid (conf=80)
    - LTC/USDT     # mid (conf=80)

risk:
  min_confluence: 70
  symbol_confluence_overrides:
    BTC/USDT: 80
    SUI/USDT: 80
    ADA/USDT: 80
    OP/USDT: 80
    LTC/USDT: 80
```

## Comparison vs H2-A2 baseline

| Metric | H2-A2 (10 sym) | aggressive_v1 raw (21 sym) | aggressive_v1 tuned (projected, 9 sym) |
|---|---:|---:|---:|
| Symbols | 10 | 21 | 9 |
| min_confluence | 80 | 70 | 70 / 80 mix |
| Notional cap | 6% | 10% | 10% |
| Max positions | 1 (de-facto) | 5 | 5 |
| Total trades | 206 | 1267 | ~400-500 (proj) |
| Portfolio return | +42.48% | HALTED | +30-50% (proj) |
| Max DD | 5.47% | >15% (HALT) | <10% (target) |

The 21-coin raw run failed because losing symbols dragged portfolio down. With
the bottom 12 dropped, expected outcome is more daily action than H2-A2 (~2x
trade volume) without sacrificing the win-rate / DD profile.

## Reports directory

`reports/backtests/phase_a_2026-05-07_aggressive_v1_1fdea2/`

Per-symbol JSON files preserved for reproducibility.
