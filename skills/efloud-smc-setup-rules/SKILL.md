---
name: efloud-smc-setup-rules
description: "Efloud SMC setup rules for entry, exit, confirmation."
version: 1.0.0
author: Hermes Agent
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [smc, setup-rules, entry-rules, exit-rules, invalidation]
    related_skills: [efloud-smc-concepts, efloud-risk-management]
---

# Efloud SMC Setup Rules

## When to Use

Use when evaluating a potential trade setup using Efloud's SMC/Price Action methodology. This skill defines the exact rules for entry, exit, confirmation, and invalidation.

## Setup Evaluation Checklist

### Pre-Setup Requirements (All Must Pass)

1. **HTF Bias Identified**
   - Determine trend direction on 4H/D/W
   - Mark key levels: WO, MO, PWO, RL Zone
   - Identify major Order Blocks (Blue/Red boxes)

2. **LTF Confluence Zone Located**
   - Find WO-MO or PWO-MO intersection
   - Mark Blue Box (demand) / Green Box (pullback target)
   - Mark Red Box / Red Line (supply/resistance)
   - Verify RL Zone (Purple Box) status

3. **Liquidity Targets Mapped**
   - Swing highs/lows (EQH/EQL)
   - HTF/LTF imbalance confluence zones
   - Gap fills (Filled Actual Gap)

### Entry Rules (Long)

| Step | Condition | Source Message |
|------|-----------|----------------|
| 1 | Price in Blue Box (demand zone) OR pulling back to Green Box | ETHUSDT, LTCUSDT |
| 2 | **mLTF (5m/15m) Bullish Confirmation**: CHoCH/BOS up + close above structure | All messages |
| 3 | No RL Zone (Purple Box) resistance immediately above | BTCUSD, PEPEUSDT |
| 4 | Volume supports move (not "sığ market") | BTCUSD LTF |
| 5 | Risk:Reward ≥ 1:1.5 to next liquidity | Implicit |

**Entry Trigger:** mLTF confirmation candle close in trade direction

**Entry Variations:**
- **Aggressive**: Enter on mLTF confirmation at Blue Box bottom
- **Conservative**: Wait for pullback to Green Box + mLTF confirmation
- **Breaker/Mitigation**: Enter on retest of broken OB/mitigated level + confirmation

### Entry Rules (Short)

| Step | Condition | Source Message |
|------|-----------|----------------|
| 1 | Price at Red Box / Red Line / RL Zone (supply zone) | DXY, PEPEUSDT |
| 2 | **mLTF (5m/15m) Bearish Confirmation**: CHoCH/BOS down + close below structure | DXY, PEPEUSDT |
| 3 | No major demand (Blue/Green box) immediately below | Implicit |
| 4 | Liquidity target below (swing low, EQH) | Implicit |

**Entry Trigger:** mLTF confirmation candle close down

### Invalidation Rules (Setup Void)

| Condition | Action |
|-----------|--------|
| Price breaks Blue Box bottom (long) / Red Box top (short) with volume | **Cancel setup** - zone failed |
| RL Zone holds and rejects price twice | **Cancel longs** - respect resistance |
| No mLTF confirmation within 8-12 bars of zone test | **Cancel setup** - momentum lost |
| "Sığ market" - low volume, choppy action | **Reduce size or skip** |
| Opposite mLTF confirmation appears | **Reverse bias** if profitable, else exit |

### Exit Rules

#### Take Profit (Scaling Out)

| Level | Action | Source |
|-------|--------|--------|
| **TP1**: First liquidity pool (swing high/low, EQH/EQL) | Close 50-75% | LINKUSDT 11% TP, BNBUSDT 25% TP |
| **TP2**: WO / MO / PWO level | Close 25% | BTCUSD WO-MO, LTCUSDT MO |
| **TP3**: Red Line / Red Box / RL Zone | Close remainder | DXY 105.3, AVAXUSDT $13.75 |
| **Trail**: Stop to entry after TP1 hit | Protect capital | BTCUSD "stop'u entry'e taşıyabilir" |

#### Stop Loss

| Type | Placement | Rule |
|------|-----------|------|
| **Initial** | Below Blue Box (long) / Above Red Box (short) | Zone invalidation |
| **Breakeven** | Move to entry after TP1 hit | Mandatory |
| **Trail** | Trail behind mLTF structure (swing lows/highs) | After TP2 |

### Special Setup Types

#### 1. Range Play (Swing)
- **Condition**: Price between WO-MO / PWO-MO, clear boundaries
- **Entry**: Range bottom (long) / top (short) + mLTF confirmation
- **Target**: Opposite range boundary
- **Source**: BTCUSD HTF "pinpon oynar gibi trade edilebilir"

#### 2. Breakout Continuation
- **Condition**: RL Zone / Red Line broken with volume
- **Entry**: Retest of broken level (now support) + mLTF confirmation
- **Target**: Next liquidity / measured move
- **Source**: BTCUSD "WO bölgesi üzerinde kalırsa... yükselişin devam edeceğini düşünüyorum"

#### 3. Pullback Re-entry
- **Condition**: Prior winning trade, price pulls back to Green Box
- **Entry**: Green Box test + mLTF confirmation
- **Target**: Previous high / next resistance
- **Source**: LINKUSDT "$7.22'ler yeni pullback noktası", LTCUSDT "yeşil kutuya... wick gelmesi akabinde"

#### 4. Breaker/Mitigation Trade
- **Condition**: Failed OB retested from other side
- **Entry**: Mitigation confirmation + mLTF structure break
- **Target**: Opposite liquidity
- **Source**: AVAXUSDT "breaker/mitigation onayı gibi"

## Decision Flow

```
1. HTF Bias? → LONG / SHORT
2. In Zone? (Blue/Green for long, Red/RL for short) → YES/NO
3. mLTF Confirmation? (5m/15m CHoCH/BOS) → YES/NO
4. RL Zone Clear? (for longs) → YES/NO
5. Volume OK? (not sığ market) → YES/NO
6. R:R ≥ 1:1.5? → YES/NO

ALL YES → ENTRY
ANY NO  → WAIT / SKIP
```

## Message References

- ETHUSDT (msg12): Blue box, mLTF confirmation, MO target
- AVAXUSDT (msg17): Breaker/mitigation, support/resistance
- LINKUSDT (msg19): Imbalance confluence, pullback entry
- BTCUSD (msg20): RL Zone, WO-MO/PWO-MO confluence
- BNBUSDT (msg21): Zone mapping, partial TP, trail stop
- BTCUSD (msg22): Stop to entry, risk management
- LINKUSDT (msg26): Resistance, pullback target
- LINKUSDT (msg28): Partial TP 7.5%, full exit at resistance
- BTCUSD (msg29): RL Zone respect, WO-MO confluence
- PEPEUSDT (msg30): Confirmation mandatory
- BTCUSD HTF (msg31): Swing levels, range play
- LTCUSDT (msg32): Confirmation wait, green box entry
- BTCUSD LTF (msg33): PWO-MO, profit taking
- PEPEUSDT (msg34): Confirmation = trade, mitigation
- LINKUSDT (msg35): 11% TP, 5% pullback, re-entry