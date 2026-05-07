# Phase A — Strategy Validation (2026-05-05)

**Config:** `configs/config.phase2_1k.yaml` ($2000 + 5x + 2.0% notional cap = $200/trade)
**Period:** 365 days
**Initial balance:** $2,000

## Per-symbol results

| Symbol | Trades | Win % | Return % | Max DD % | PF | Sharpe-like | Skipped Cycles |
|--------|-------:|------:|---------:|---------:|---:|------------:|---------------:|
| BTC/USDT | 237 | 47.3 | -5.47 | 5.56 | 1.37 | 0.13 | 0 |
| ETH/USDT | 232 | 44.0 | -4.68 | 4.92 | 1.28 | 0.1 | 0 |
| XRP/USDT | 138 | 42.8 | -5.66 | 5.66 | 1.06 | 0.03 | 0 |
| DOGE/USDT | 38 | 34.2 | -3.12 | 3.59 | 0.59 | -0.24 | 0 |
| SOL/USDT | 248 | 44.0 | -8.98 | 9.19 | 1.39 | 0.14 | 0 |
| BNB/USDT | 267 | 37.8 | -5.06 | 5.47 | 0.91 | -0.04 | 0 |
| TRX/USDT | 20 | 45.0 | 0.16 | 0.42 | 1.36 | 0.14 | 0 |
| LINK/USDT | 185 | 36.2 | -12.71 | 12.72 | 0.95 | -0.02 | 0 |
| BCH/USDT | 244 | 34.8 | -8.3 | 8.76 | 0.98 | -0.01 | 0 |
| ADA/USDT | 88 | 44.3 | -5.41 | 6.99 | 1.16 | 0.06 | 0 |

## Portfolio (all 10 symbols)

- **Total trades:** 1709
- **Win rate:** 40.5%
- **Total return:** -43.75%
- **Max DD (MTM):** 44.24%
- **Profit factor:** 1.08
- **Sharpe-like:** 0.03
- **Final balance:** $1,124.97
- **Peak balance:** $2,013.01

## Ranking (by total_return_pct)

- **TRX/USDT**: 0.16% (20 trades)
- **DOGE/USDT**: -3.12% (38 trades)
- **ETH/USDT**: -4.68% (232 trades)
- **BNB/USDT**: -5.06% (267 trades)
- **ADA/USDT**: -5.41% (88 trades)
- **BTC/USDT**: -5.47% (237 trades)
- **XRP/USDT**: -5.66% (138 trades)
- **BCH/USDT**: -8.3% (244 trades)
- **SOL/USDT**: -8.98% (248 trades)
- **LINK/USDT**: -12.71% (185 trades)

## Recommendations (next steps)

- **Strongest 3 (focus candidates):** TRX/USDT, DOGE/USDT, ETH/USDT
- **Weakest 3 (drop candidates):** BCH/USDT, SOL/USDT, LINK/USDT
- **Phase C grid:** consider running the confluence × notional grid on the strongest 5-7 symbols only.

## Reports directory
`reports\backtests\phase_a_2026-05-05_2de8bd`
