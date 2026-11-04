---
name: efloud-risk-management
description: "Efloud risk management: position sizing, stops, scaling."
version: 1.0.0
author: Hermes Agent
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [risk-management, position-sizing, stop-loss, scaling, portfolio-heat]
    related_skills: [efloud-smc-concepts, efloud-smc-setup-rules]
---

> ⚠️ **INCUBATOR TASLAĞI — AKTİF DEĞİL.** Yazar: hermes (commit `645a5dc`). Kullanmadan önce aynı klasördeki `REVIEW.md`'yi oku; buradaki sayılar canlı config DEĞİLDİR (kaynak: `configs/config.phase2_1k.yaml`).

# Efloud Risk Management

## When to Use

Use when calculating position size, setting stops, managing open positions, and controlling portfolio risk per Efloud's methodology.

## Core Risk Principles

### From Messages
- "Gereksiz riskler almayın" - avoid low probability setups
- "Sığ markette confirmation aramanız gerektiğini" - higher bar in chop
- "Stop'u entry'e taşıyabilir veya riskiniz kadar satış gerçekleştirebilirsiniz" - breakeven mandatory
- Partial profit taking at key levels (25%, 50-75%, remainder)
- Respect RL Zone - no new positions against it

## Position Sizing

### Base Risk Per Trade
- **Standard**: 1-2% of account per trade
- **High Conviction** (WO-MO confluence + confirmation): up to 2%
- **Low Conviction / Sığ Market**: 0.5-1% or skip
- **Multiple Entries** (Blue → Green box): Split size 50/50 or 60/40

### Calculation
```
Position Size = (Account Balance × Risk %) / (Entry - Stop Loss)

Example:
- Account: $10,000
- Risk: 1.5% = $150
- Entry: $42,500
- Stop: $42,000 (Blue Box bottom)
- Risk per unit: $500
- Size: $150 / $500 = 0.3 units
```

### Leverage Guidelines
- **Spot / Low Leverage (1-3x)**: Standard sizing
- **Futures (5-10x)**: Reduce notional, same dollar risk
- **High Leverage (10x+)**: Not recommended per methodology

## Stop Loss Rules

### Initial Stop Placement
| Setup Type | Stop Location |
|------------|---------------|
| Blue Box Long | Below Blue Box bottom (demand invalidation) |
| Green Box Long | Below Green Box bottom |
| Breaker/Mitigation Long | Below mitigation low |
| Red Box Short | Above Red Box top (supply invalidation) |
| Red Line Short | Above Red Line break |
| RL Zone Short | Above RL Zone (purple box top) |

### Stop Management

| Phase | Action | Trigger |
|-------|--------|---------|
| **Initial** | Place at zone invalidation | Entry fill |
| **Breakeven** | Move SL to entry | TP1 hit (first liquidity) |
| **Trail** | Trail behind mLTF swings | TP2 hit (WO/MO level) |
| **Full Trail** | Trail behind HTF swings | TP3 hit (Red Line/RL Zone) |

**Rule**: "Stop'u entry'e taşıyabilir" - mandatory after first partial TP

## Scaling Out (Profit Taking)

### Standard Scale-Out Plan

| Tier | Target | % Position | Action |
|------|--------|------------|--------|
| **TP1** | First liquidity (swing high/low, EQH/EQL) | 50-75% | Close, move SL to entry |
| **TP2** | WO / MO / PWO institutional level | 25% | Close, trail SL behind mLTF swings |
| **TP3** | Red Line / Red Box / RL Zone | Remainder | Close, trail behind HTF swings |

### Message Examples
- LINKUSDT: 11% TP at resistance (Red Line), 5% pullback re-entry
- BNBUSDT: 25% TP at $251, trail stop to entry
- BTCUSD: Partial at WO-MO, remainder at RL Zone
- LTCUSDT: Target MO ($90) from Green Box entry

## Portfolio Heat Limits

### Maximum Concurrent Risk
- **Total open risk**: ≤ 5% of account
- **Correlated pairs** (BTC/ETH, major alts): ≤ 3% combined
- **Single direction bias**: ≤ 4% (all longs or all shorts)
- **Max positions**: 5-8 concurrent

### Correlation Management
- BTC + ETH + major alts = correlated → treat as one position for heat
- Stablecoin pairs excluded from heat
- Different timeframe setups (swing + scalp) can stack if risk controlled

## Drawdown Controls

| Drawdown Level | Action |
|----------------|--------|
| **-3% daily** | Stop trading, review setups |
| **-5% weekly** | Reduce size 50%, only A+ setups |
| **-10% monthly** | Stop trading, full review |
| **3 consecutive losses** | Pause 24h, journal review |

## Risk:Reward Requirements

| Setup Quality | Minimum R:R |
|---------------|-------------|
| A+ (WO-MO confluence + confirmation) | 1:2 |
| A (Blue Box + confirmation) | 1:1.5 |
| B (Green Box pullback + confirmation) | 1:1.5 |
| Range play | 1:1 |
| Breaker/Mitigation | 1:1.5 |

**Never enter** if R:R < 1:1 (except range scalp with high win rate)

## Position Management Rules

### Adding to Winners
- **Allowed**: Second entry at Green Box pullback (max 50% of initial)
- **Not allowed**: Adding at resistance, chasing breakouts
- **Pyramid**: Only in strong trend, each add smaller than previous

### Reducing Losers
- **Cut early**: If mLTF structure breaks against position before SL
- **Time stop**: If no movement in 4-8 hours (scalp) / 2-3 days (swing)
- **News/event risk**: Reduce before major events (CPI, FOMC, etc.)

### Psychology Rules
- "Şu dandik markette şunları aldığımıza şükredelim" - take what market gives
- "Yüzdesel olarak kâr az ama en azından bu markette para kazanılabiliyor" - small wins compound
- No revenge trading after loss
- Journal every trade with: setup type, zone, confirmation, R:R, outcome

## Integration with efloud-bot Config

Maps to config.yaml safety section:
```yaml
safety:
  daily_loss_limit_pct: 3.0          # Daily stop
  weekly_drawdown_limit_pct: 8.0     # Weekly stop
  consecutive_loss_limit: 3          # Pause after 3 losses
  consecutive_pause_min: 120         # 2h pause
  max_position_notional_pct: 8.0     # Single trade max
  max_total_exposure: 3.0            # Portfolio heat
  max_holding_hours: 48              # Time stop
  max_pyramid_adds: 2                # Max adds
  min_sl_atr: 0.5                    # Min SL distance
  max_sl_atr: 5.0                    # Max SL distance
  reverse_min_profit_pct: 0.2        # Flip only in profit
```

## Message References

- BNBUSDT (msg21): 25% TP, stop to entry, re-entry at $238
- BTCUSD (msg22): 1% profit, stop to entry, risk off
- LINKUSDT (msg26): 7.5% TP at resistance, pullback target $7.22
- LINKUSDT (msg28): 7.5% TP, full exit at resistance, 10% left
- BTCUSD (msg29): 2% profit, RL Zone respect, no add
- LINKUSDT (msg35): 11% TP, 5% pullback, re-entry at $7.22