# Phase A — Strategy Validation (2026-05-07)

**Config:** `configs/config.aggressive_v1.yaml` ($2000 + 5x + 2.0% notional cap = $200/trade)
**Period:** 365 days
**Initial balance:** $2,000

## Per-symbol results

| Symbol | Trades | Win % | Return % | Max DD % | PF | Sharpe-like | Skipped Cycles |
|--------|-------:|------:|---------:|---------:|---:|------------:|---------------:|
| ETH/USDT | 89 | 60.7 | 20.47 | 5.79 | 2.74 | 0.44 | 0 |
| SOL/USDT | 76 | 65.8 | 22.76 | 6.74 | 3.41 | 0.55 | 0 |
| FIL/USDT | 64 | 62.5 | 6.77 | 11.49 | 2.78 | 0.47 | 0 |
| RENDER/USDT | 67 | 67.2 | 11.34 | 9.83 | 3.54 | 0.59 | 0 |
| SUI/USDT | 27 | 63.0 | 12.4 | 4.9 | 3.46 | 0.43 | 0 |
| ADA/USDT | 8 | 87.5 | -0.44 | 3.99 | 17.9 | 0.54 | 0 |
| OP/USDT | 16 | 50.0 | -0.68 | 7.73 | 1.71 | 0.24 | 0 |
| LTC/USDT | 17 | 41.2 | 1.49 | 3.74 | 1.37 | 0.13 | 0 |
| BTC/USDT | 24 | 54.2 | 5.6 | 1.81 | 3.97 | 0.54 | 0 |

## Portfolio (all 10 symbols)

- **Total trades:** 364
- **Win rate:** 58.0%
- **Total return:** 49.12%
- **Max DD (MTM):** 11.49%
- **Profit factor:** 2.44
- **Sharpe-like:** 0.38
- **Final balance:** $2,982.42
- **Peak balance:** $3,265.33

## Ranking (by total_return_pct)

- **SOL/USDT**: 22.76% (76 trades)
- **ETH/USDT**: 20.47% (89 trades)
- **SUI/USDT**: 12.4% (27 trades)
- **RENDER/USDT**: 11.34% (67 trades)
- **FIL/USDT**: 6.77% (64 trades)
- **BTC/USDT**: 5.6% (24 trades)
- **LTC/USDT**: 1.49% (17 trades)
- **ADA/USDT**: -0.44% (8 trades)
- **OP/USDT**: -0.68% (16 trades)

## Recommendations (next steps)

- **Strongest 3 (focus candidates):** SOL/USDT, ETH/USDT, SUI/USDT
- **Weakest 3 (drop candidates):** LTC/USDT, ADA/USDT, OP/USDT
- **Phase C grid:** consider running the confluence × notional grid on the strongest 5-7 symbols only.

## Reports directory
`reports\backtests\phase_a_2026-05-07_aggressive_v1_bb0d8f`
