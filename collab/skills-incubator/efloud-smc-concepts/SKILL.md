---
name: efloud-smc-concepts
description: "Efloud SMC/Price Action concepts from Telegram analysis."
version: 1.0.0
author: Hermes Agent
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [smc, price-action, trading, order-blocks, breaker-blocks, mitigation, liquidity, confirmation]
    related_skills: [efloud-smc-setup-rules, efloud-tradingview-integration, efloud-risk-management]
---

> ⚠️ **INCUBATOR TASLAĞI — AKTİF DEĞİL.** Yazar: hermes (commit `645a5dc`). Kullanmadan önce aynı klasördeki `REVIEW.md`'yi oku; buradaki sayılar canlı config DEĞİLDİR (kaynak: `configs/config.phase2_1k.yaml`).

# Efloud SMC/Price Action Concepts

## Overview

This skill captures the Smart Money Concept (SMC) and Price Action methodology used by Efloud (Telegram: Efloud TA & Charts). Extracted from 35 analyzed messages (Aug 2023).

## Core Concepts

### 1. Order Blocks & Colored Zones

**Terminology from messages:**
- **Mavi Kutu (Blue Box)** = Primary Order Block / Demand Zone for longs
- **Yeşil Kutu (Green Box)** = Secondary demand / pullback target
- **Mor Kutu (Purple Box)** = RL Zone (Resistance Level) / Supply zone
- **Kırmızı Kutu (Red Box)** = Resistance / Supply zone
- **Kırmızı Çizgi (Red Line)** = Key resistance level / trendline

**Rules:**
- Trade only within defined zones ("Göstermiş olduğum yazılı bölge dışında trade'lemedim")
- Blue box bottoms with confirmation = long entry zones
- Green box = preferred pullback target for entries
- Purple box (RL Zone) = resistance, no new longs until broken with volume
- Red line breaks = potential continuation targets

### 2. Breaker Blocks & Mitigation

**Explicit mentions:**
- "breaker/mitigation onayı gibi" (AVAXUSDT message)
- Mitigation = price returning to test/breach an order block
- Breaker = failed OB that flips role (support→resistance or vice versa)

**Rules:**
- Wait for mitigation confirmation before entry
- Breaker confirmation = price breaks OB then retests from other side
- Both are entry triggers when combined with mLTF confirmation

### 3. Liquidity & Imbalance

**Terminology:**
- "HTF ve LTF imbalace'lerinin kesişimi" (LINKUSDT)
- "Filled Actual Gap" (DXY)
- Liquidity = swing highs/lows, equal highs/lows
- Imbalance = FVG (Fair Value Gap) / inefficient price delivery

**Rules:**
- Target liquidity pools for TP (swing highs/lows, EQH/EQL)
- HTF + LTF imbalance confluence = high probability zones
- Gap fills (Filled Actual Gap) = magnetic targets

### 4. Confirmation (Entry Trigger)

**Critical concept - repeated in almost every message:**
- "Confirmation Yok = Short Pozisyonu Yok" (PEPEUSDT)
- "mLTF bullish confirmation'lar ile (5/15 dk) MO bölgesine kadar long düşünülebilir"
- "bearish confirmation'lar ile işlem alınabilir" (DXY)
- Confirmation = mLTF (5m/15m) structure break (CHoCH/BOS) in trade direction

**Types:**
- **Bullish Confirmation**: mLTF CHoCH/BOS up + candle close above structure
- **Bearish Confirmation**: mLTF CHoCH/BOS down + candle close below structure
- **No confirmation = no trade** (mandatory rule)

### 5. Multi-Timeframe Framework

| Timeframe | Role | Usage |
|-----------|------|-------|
| **HTF** (4H/D/W) | Bias & Key Levels | RL Zone, WO, MO, major OB |
| **LTF** (1H/2H) | Structure & Confluence | PWO-MO kesişimi, WO-MO kesişimi |
| **mLTF** (5m/15m) | **Entry Trigger** | Confirmation (CHoCH/BOS) |

**Rules:**
- HTF bias determines direction (long/short)
- LTF provides confluence zones (WO/MO/PWO intersections)
- mLTF confirmation is MANDATORY for entry
- "Sığ markette confirmation aramanız gerektiğini" (repeated emphasis)

### 6. Range & Institutional Levels

**Key Levels Referenced:**
- **WO** (Weekly Open) = Weekly institutional reference
- **MO** (Monthly Open) = Monthly institutional reference
- **PWO** (Previous Weekly Open) = Prior week reference
- **RL Zone** (Resistance Level / Purple Box) = Key resistance
- **WO-MO Kesişimi** = Confluence zone (high probability)
- **PWO-MO Kesişimi** = Confluence zone

**Rules:**
- Price respects WO/MO as magnetic levels
- Confluence of WO+MO = high probability reaction
- RL Zone must break with volume for continuation

### 7. Swing Structure & CHoCH/BOS

**References:**
- "Swing mentalitesinde işlemler alınabilir" (BTCUSD HTF)
- "$28.550 ve $28.650 olmak üzere iki kere destek buldu" (double bottom)
- "2 defadır da mor kutudan yani $30.000 seviyesinden ret alıyor" (rejection)
- Structure breaks at key levels = trade triggers

### 8. Optimal Trade Entry (OTE) Patterns

**From messages:**
- Pullback to Blue/Green box + mLTF confirmation
- "$7.22'ler yeni pullback noktası olabilir" (LINKUSDT)
- "yeşil kutuya, tercihen $78.5'lere doğru, bir wick gelmesi akabinde" (LTCUSDT)
- Mitigation of breaker/OB + confirmation = entry
- Never chase - wait for pullback to zone + confirmation

## Trading Rules Summary

### Mandatory Rules (Never Violate)
1. **No trade without mLTF confirmation** (5m/15m CHoCH/BOS)
2. **Trade only within defined zones** (colored boxes)
3. **Respect RL Zone** - no new longs until broken with volume
4. **Stop loss to entry** once in profit ("stop'u entry'e taşıyabilir")
5. **Partial profits** at key levels ("25% kâr aldım", "büyük ölçüde kırmızı çizgide sattım")

### Risk Management
- Position sizing: defined risk per trade
- Trail stop to entry after partial TP
- Reduce size in "sığ market" (low volume/choppy)
- "gereksiz riskler almayın" - avoid low probability setups

### Trade Management
- Multiple entries possible at different zones (Blue → Green)
- Scale out at resistance levels (Red line, Red box, RL Zone)
- Swing trades: hold for WO/MO targets
- Scalp trades: mLTF confirmation → quick TP at next liquidity

## Message Reference Index

| Message | Symbol | Key Concepts |
|---------|--------|--------------|
| 11 | DXY | Filled Actual Gap, bearish confirmation |
| 12 | ETHUSDT | Blue box, mLTF confirmation, MO/WO |
| 17 | AVAXUSDT | Breaker/mitigation, support/resistance |
| 19 | LINKUSDT | Imbalance confluence, pullback entry |
| 20 | BTCUSD | RL Zone, WO-MO/PWO-MO confluence |
| 21 | BNBUSDT | Comprehensive zone mapping, partial TP |
| 22 | BTCUSD | Stop to entry, risk management |
| 26 | LINKUSDT | Resistance, pullback target, trail stop |
| 28 | LINKUSDT | Partial TP (7.5%), full exit at resistance |
| 29 | BTCUSD | RL Zone respect, WO-MO confluence |
| 31 | BTCUSD HTF | Swing levels, double bottom, range play |
| 32 | LTCUSDT | Confirmation wait, green box entry |
| 33 | BTCUSD LTF | PWO-MO, profit taking, risk off |
| 34 | PEPEUSDT | Confirmation = trade, mitigation concept |
| 35 | LINKUSDT | 11% TP, 5% pullback, re-entry |

## Integration Notes

- These concepts map to efloud-bot engine: SMCEngine, LevelEngine, IntentEngine
- Zones → Order Blocks (OB) in engine
- Confirmation → mLTF CHoCH/BOS in SignalEngine
- WO/MO/PWO/RL → Injected Levels in LevelEngine
- Breaker/Mitigation → BreakerBlock/MitigationBlock in SMCEngine
- Multi-timeframe → HTF/MTF/Entry TF chain in config.yaml