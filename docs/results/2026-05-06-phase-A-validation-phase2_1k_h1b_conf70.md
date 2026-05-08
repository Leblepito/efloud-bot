# Phase A — Strategy Validation (2026-05-06)

**Config:** `configs/config.phase2_1k_h1b_conf70.yaml` ($2000 + 5x + 2.0% notional cap = $200/trade)
**Period:** 365 days
**Initial balance:** $2,000

## Per-symbol results

| Symbol | Trades | Win % | Return % | Max DD % | PF | Sharpe-like | Skipped Cycles |
|--------|-------:|------:|---------:|---------:|---:|------------:|---------------:|
| BTC/USDT | 80 | 52.5 | 1.13 | 1.13 | 2.1 | 0.3 | 0 |
| ETH/USDT | 91 | 60.4 | 4.41 | 1.48 | 2.48 | 0.38 | 0 |
| XRP/USDT | 60 | 45.0 | -1.97 | 2.65 | 1.29 | 0.11 | 0 |
| DOGE/USDT | 30 | 50.0 | -1.41 | 2.42 | 1.66 | 0.21 | 0 |
| SOL/USDT | 81 | 65.4 | 2.87 | 1.68 | 3.03 | 0.48 | 0 |
| BNB/USDT | 106 | 50.0 | -0.0 | 1.28 | 1.49 | 0.17 | 0 |
| TRX/USDT | 19 | 78.9 | -0.05 | 0.35 | 9.09 | 0.98 | 0 |
| LINK/USDT | 55 | 41.8 | -1.3 | 2.0 | 1.24 | 0.09 | 0 |
| BCH/USDT | 74 | 51.4 | 1.15 | 1.51 | 1.73 | 0.23 | 0 |
| ADA/USDT | 57 | 59.6 | -0.2 | 1.93 | 1.96 | 0.31 | 0 |

## Portfolio (all 10 symbols)

- **Total trades:** 680
- **Win rate:** 54.7%
- **Total return:** 4.89%
- **Max DD (MTM):** 7.17%
- **Profit factor:** 1.95
- **Sharpe-like:** 0.27
- **Final balance:** $2,097.77
- **Peak balance:** $2,138.83

## Ranking (by total_return_pct)

- **ETH/USDT**: 4.41% (91 trades)
- **SOL/USDT**: 2.87% (81 trades)
- **BCH/USDT**: 1.15% (74 trades)
- **BTC/USDT**: 1.13% (80 trades)
- **BNB/USDT**: -0.0% (106 trades)
- **TRX/USDT**: -0.05% (19 trades)
- **ADA/USDT**: -0.2% (57 trades)
- **LINK/USDT**: -1.3% (55 trades)
- **DOGE/USDT**: -1.41% (30 trades)
- **XRP/USDT**: -1.97% (60 trades)

## Recommendations (next steps)

- **Strongest 3 (focus candidates):** ETH/USDT, SOL/USDT, BCH/USDT
- **Weakest 3 (drop candidates):** LINK/USDT, DOGE/USDT, XRP/USDT
- **Phase C grid:** consider running the confluence × notional grid on the strongest 5-7 symbols only.

## Reports directory
`reports\backtests\phase_a_2026-05-06_phase2_1k_h1b_conf70_0c3a3c`
