---
name: efloud-trading-risk-checklist
description: Mandatory checklist before changing config.yaml risk: or safety: blocks, leverage, position sizing, confluence threshold, or any trading-behavior parameter. Use whenever a parameter that affects live PnL is being tuned.
---

# efloud-trading-risk-checklist

`config.yaml` `risk:` and `safety:` blocks directly determine money lost or
preserved. A single typo = real loss. Follow this checklist **before** the change
is committed.

## 1. Impact analysis

Identify which metric the change moves:

| Parameter | Primary impact |
|-----------|----------------|
| `risk_per_trade_pct` | Position size → drawdown depth |
| `max_open_positions` | Exposure breadth → correlation risk |
| `min_rr` | Win rate floor → trade count |
| `min_confluence` | Selectivity → trade frequency |
| `daily_loss_limit_pct` | Daily blowup cap |
| `weekly_drawdown_limit_pct` | Weekly blowup cap |
| `consecutive_loss_limit` | Cooldown trigger |
| `max_position_notional_pct` | Single-trade sizing cap |
| `max_total_exposure` | Portfolio leverage cap |
| `leverage` | Liquidation distance |
| `margin_mode` | Liquidation cascade isolation |

State explicitly: "This change moves <metric> by <direction>, expected effect <X>."

## 2. Backtest validation

- Run **before/after** on the same period:
  ```bash
  python test_backtest_multi.py
  # or
  python -m backtest.engine --config config.yaml --period 90d
  ```
- Compare: total return, Sharpe, max DD, win rate, profit factor, # trades.
- If max DD increases or Sharpe drops > 10% — STOP, rethink.

## 3. Backout plan

- Record previous value + commit hash that contains it.
- Single-command revert: `git revert <commit>` or manual config restore.
- Note in PR: "Revert: change `<param>` from `<new>` back to `<old>`."

## 4. Live observation gate

Before deploying with `dry_run: false`:
- Deploy with `dry_run: true` first.
- Observe **at least 1 full cycle** (default 30s) plus 1 signal generation event.
- Check `efloud_bot.log` for `WEAKNESS`, `BREAKER`, `ORPHAN`, `HALT` keywords.

## 5. Approval

PR description must include a **Before/After table**:

```markdown
| Param | Before | After | Reason |
|-------|--------|-------|--------|
| risk.min_confluence | 55 | 60 | Reduce false positives in ranging regimes |
| risk.risk_per_trade_pct | 0.75 | 0.50 | Drawdown control after PR #30 incident |

Backtest delta (90d, 7 regimes):
- Total return: +X% → +Y%
- Max DD: -Z% → -W%
- Sharpe: A → B
```

Hermes/Utku sign-off **required** before merge.

## 6. Post-deploy monitoring

- First 24h: check daily report (`ops/daily_report/`).
- Telegram alerts: any new WEAKNESS / BREAKER / HALT? Investigate immediately.
- Compare actual PnL to backtest expectation; significant divergence (> 2σ) → investigate.

## Hard rules
- No risk param change without backtest evidence.
- No risk param change without Hermes/Utku approval.
- No simultaneous change to multiple risk params (atomic PR rule).
- No production deploy with `dry_run: false` directly — always dry_run first.
