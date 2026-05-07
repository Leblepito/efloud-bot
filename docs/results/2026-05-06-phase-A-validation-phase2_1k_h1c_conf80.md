# Phase A — Strategy Validation (2026-05-06)

**Config:** `configs/config.phase2_1k_h1c_conf80.yaml` ($2000 + 5x + 2.0% notional cap = $200/trade)
**Period:** 365 days
**Initial balance:** $2,000

## Per-symbol results

| Symbol | Trades | Win % | Return % | Max DD % | PF | Sharpe-like | Skipped Cycles |
|--------|-------:|------:|---------:|---------:|---:|------------:|---------------:|
| BTC/USDT | 22 | 50.0 | 0.88 | 0.36 | 3.38 | 0.46 | 0 |
| ETH/USDT | 39 | 66.7 | 3.86 | 0.83 | 5.36 | 0.7 | 0 |
| XRP/USDT | 21 | 61.9 | 0.8 | 0.73 | 3.11 | 0.47 | 0 |
| DOGE/USDT | 14 | 64.3 | 0.92 | 1.26 | 3.93 | 0.6 | 0 |
| SOL/USDT | 19 | 73.7 | 2.39 | 0.53 | 6.03 | 0.81 | 0 |
| BNB/USDT | 31 | 64.5 | 0.73 | 0.56 | 2.4 | 0.36 | 0 |
| TRX/USDT | 13 | 76.9 | 0.04 | 0.28 | 14.65 | 1.1 | 0 |
| LINK/USDT | 18 | 66.7 | 1.79 | 0.97 | 3.81 | 0.61 | 0 |
| BCH/USDT | 19 | 63.2 | 0.32 | 0.53 | 2.97 | 0.35 | 0 |
| ADA/USDT | 21 | 66.7 | 0.33 | 1.16 | 3.49 | 0.55 | 0 |

## Portfolio (all 10 symbols)

- **Total trades:** 213
- **Win rate:** 62.4%
- **Total return:** 11.29%
- **Max DD (MTM):** 2.83%
- **Profit factor:** 3.5
- **Sharpe-like:** 0.51
- **Final balance:** $2,225.72
- **Peak balance:** $2,241.42

## Ranking (by total_return_pct)

- **ETH/USDT**: 3.86% (39 trades)
- **SOL/USDT**: 2.39% (19 trades)
- **LINK/USDT**: 1.79% (18 trades)
- **DOGE/USDT**: 0.92% (14 trades)
- **BTC/USDT**: 0.88% (22 trades)
- **XRP/USDT**: 0.8% (21 trades)
- **BNB/USDT**: 0.73% (31 trades)
- **ADA/USDT**: 0.33% (21 trades)
- **BCH/USDT**: 0.32% (19 trades)
- **TRX/USDT**: 0.04% (13 trades)

## Recommendations (next steps)

- **Strongest 3 (focus candidates):** ETH/USDT, SOL/USDT, LINK/USDT
- **Weakest 3 (drop candidates):** ADA/USDT, BCH/USDT, TRX/USDT
- **Phase C grid:** consider running the confluence × notional grid on the strongest 5-7 symbols only.

## Reports directory
`reports\backtests\phase_a_2026-05-06_phase2_1k_h1c_conf80_dc30e5`
