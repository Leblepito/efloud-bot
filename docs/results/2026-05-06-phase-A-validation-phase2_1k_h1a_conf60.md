# Phase A — Strategy Validation (2026-05-06)

**Config:** `configs/config.phase2_1k_h1a_conf60.yaml` ($2000 + 5x + 2.0% notional cap = $200/trade)
**Period:** 365 days
**Initial balance:** $2,000

## Per-symbol results

| Symbol | Trades | Win % | Return % | Max DD % | PF | Sharpe-like | Skipped Cycles |
|--------|-------:|------:|---------:|---------:|---:|------------:|---------------:|
| BTC/USDT | 184 | 47.3 | -4.61 | 4.76 | 1.31 | 0.12 | 0 |
| ETH/USDT | 187 | 44.9 | -4.14 | 5.03 | 1.31 | 0.11 | 0 |
| XRP/USDT | 124 | 42.7 | -6.28 | 6.74 | 1.03 | 0.01 | 0 |
| DOGE/USDT | 38 | 31.6 | -2.47 | 3.07 | 0.62 | -0.21 | 0 |
| SOL/USDT | 194 | 46.9 | -5.58 | 6.47 | 1.57 | 0.19 | 0 |
| BNB/USDT | 198 | 40.4 | -5.24 | 5.51 | 1.05 | 0.02 | 0 |
| TRX/USDT | 19 | 63.2 | -0.12 | 0.49 | 2.22 | 0.36 | 0 |
| LINK/USDT | 126 | 42.1 | -4.81 | 5.35 | 1.19 | 0.07 | 0 |
| BCH/USDT | 187 | 44.4 | -5.07 | 5.44 | 1.33 | 0.12 | 0 |
| ADA/USDT | 78 | 47.4 | -4.98 | 6.57 | 1.22 | 0.09 | 0 |

## Portfolio (all 10 symbols)

- **Total trades:** 1361
- **Win rate:** 45.5%
- **Total return:** -34.32%
- **Max DD (MTM):** 34.64%
- **Profit factor:** 1.31
- **Sharpe-like:** 0.11
- **Final balance:** $1,313.67
- **Peak balance:** $2,002.46

## Ranking (by total_return_pct)

- **TRX/USDT**: -0.12% (19 trades)
- **DOGE/USDT**: -2.47% (38 trades)
- **ETH/USDT**: -4.14% (187 trades)
- **BTC/USDT**: -4.61% (184 trades)
- **LINK/USDT**: -4.81% (126 trades)
- **ADA/USDT**: -4.98% (78 trades)
- **BCH/USDT**: -5.07% (187 trades)
- **BNB/USDT**: -5.24% (198 trades)
- **SOL/USDT**: -5.58% (194 trades)
- **XRP/USDT**: -6.28% (124 trades)

## Recommendations (next steps)

- **Strongest 3 (focus candidates):** TRX/USDT, DOGE/USDT, ETH/USDT
- **Weakest 3 (drop candidates):** BNB/USDT, SOL/USDT, XRP/USDT
- **Phase C grid:** consider running the confluence × notional grid on the strongest 5-7 symbols only.

## Reports directory
`reports\backtests\phase_a_2026-05-06_phase2_1k_h1a_conf60_1cd4d2`
