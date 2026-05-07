# Phase A — Strategy Validation (2026-05-06)

**Config:** `configs/config.phase2_1k_h2a2_risk2_notional6.yaml` ($2000 + 5x + 2.0% notional cap = $200/trade)
**Period:** 365 days
**Initial balance:** $2,000

## Per-symbol results

| Symbol | Trades | Win % | Return % | Max DD % | PF | Sharpe-like | Skipped Cycles |
|--------|-------:|------:|---------:|---------:|---:|------------:|---------------:|
| BTC/USDT | 20 | 50.0 | 3.92 | 1.06 | 2.46 | 0.35 | 0 |
| ETH/USDT | 39 | 66.7 | 11.95 | 2.47 | 5.28 | 0.69 | 0 |
| XRP/USDT | 18 | 72.2 | 4.29 | 2.75 | 3.91 | 0.58 | 0 |
| DOGE/USDT | 15 | 46.7 | 3.18 | 2.72 | 2.03 | 0.3 | 0 |
| SOL/USDT | 18 | 66.7 | 3.15 | 1.28 | 3.76 | 0.58 | 0 |
| BNB/USDT | 28 | 60.7 | -0.42 | 2.6 | 2.29 | 0.34 | 0 |
| TRX/USDT | 13 | 69.2 | -0.22 | 0.99 | 6.24 | 0.81 | 0 |
| LINK/USDT | 18 | 66.7 | 6.97 | 2.05 | 4.84 | 0.68 | 0 |
| BCH/USDT | 16 | 68.8 | -0.75 | 2.04 | 4.23 | 0.63 | 0 |
| ADA/USDT | 20 | 60.0 | 0.12 | 2.51 | 2.09 | 0.33 | 0 |

## Portfolio (all 10 symbols)

- **Total trades:** 206
- **Win rate:** 65.0%
- **Total return:** 42.48%
- **Max DD (MTM):** 5.47%
- **Profit factor:** 3.64
- **Sharpe-like:** 0.53
- **Final balance:** $2,849.62
- **Peak balance:** $2,887.01

## Ranking (by total_return_pct)

- **ETH/USDT**: 11.95% (39 trades)
- **LINK/USDT**: 6.97% (18 trades)
- **XRP/USDT**: 4.29% (18 trades)
- **BTC/USDT**: 3.92% (20 trades)
- **DOGE/USDT**: 3.18% (15 trades)
- **SOL/USDT**: 3.15% (18 trades)
- **ADA/USDT**: 0.12% (20 trades)
- **TRX/USDT**: -0.22% (13 trades)
- **BNB/USDT**: -0.42% (28 trades)
- **BCH/USDT**: -0.75% (16 trades)

## Recommendations (next steps)

- **Strongest 3 (focus candidates):** ETH/USDT, LINK/USDT, XRP/USDT
- **Weakest 3 (drop candidates):** TRX/USDT, BNB/USDT, BCH/USDT
- **Phase C grid:** consider running the confluence × notional grid on the strongest 5-7 symbols only.

## Reports directory
`reports\backtests\phase_a_2026-05-06_phase2_1k_h2a2_risk2_notional6_a13cae`
