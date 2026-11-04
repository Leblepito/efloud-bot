---
name: efloud-tradingview-integration
description: "TradingView integration for Efloud SMC live data signals."
version: 1.0.0
author: Hermes Agent
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [tradingview, live-data, webhook, chart-analysis, smc-signals]
    related_skills: [efloud-smc-concepts, efloud-smc-setup-rules, efloud-risk-management]
---

> ⚠️ **INCUBATOR TASLAĞI — AKTİF DEĞİL.** Yazar: hermes (commit `645a5dc`). Kullanmadan önce aynı klasördeki `REVIEW.md`'yi oku; buradaki sayılar canlı config DEĞİLDİR (kaynak: `configs/config.phase2_1k.yaml`).

# TradingView Integration for Efloud SMC

## When to Use

Use when building agents that fetch live market data from TradingView, analyze charts using Efloud SMC concepts, and generate trade signals via webhook or API.

## Architecture Overview

```
TradingView Chart → Pine Script / Webhook → Agent → Efloud SMC Analysis → Signal → Order Manager
```

## Data Sources

### 1. TradingView Webhook (Recommended)
- Pine Script alerts → HTTP webhook → Agent endpoint
- Real-time, low latency
- Supports multiple timeframes

### 2. TradingView Chart Images (OCR)
- Export chart images → Vision model → Extract levels/zones
- For manual chart analysis
- Slower, but captures visual annotations

### 3. TradingView Data API (tvDatafeed)
- Python library for historical data
- No official API, community maintained
- Good for backtesting

## Required Pine Script Indicators

### Core Efloud SMC Indicators

```pinescript
//@version=5
indicator("Efloud SMC Zones", overlay=true)

// Inputs
show_ob = input.bool(true, "Show Order Blocks")
show_breaker = input.bool(true, "Show Breaker Blocks")
show_mitigation = input.bool(true, "Show Mitigation")
show_liquidity = input.bool(true, "Show Liquidity")
show_fvg = input.bool(true, "Show FVG/Imbalance")
show_institutional = input.bool(true, "Show WO/MO/PWO/RL")

// Swing Detection
swing_len = input.int(50, "Swing Length")
internal_len = input.int(5, "Internal Length")

// Order Block Detection
// Bull OB: Down candle before up move
// Bear OB: Up candle before down move

// Breaker Block: Failed OB retested
// Mitigation: Price returns to OB

// Liquidity: Swing highs/lows, Equal highs/lows

// FVG: 3-candle gap

// Institutional Levels
// WO = Weekly Open
// MO = Monthly Open
// PWO = Previous Weekly Open
// RL Zone = Resistance Level (major supply)

// Color Coding (match Telegram)
// Blue Box = Bull OB / Demand
// Green Box = Pullback Target
// Red Box = Bear OB / Supply
// Purple Box = RL Zone
// Red Line = Key Resistance Trendline
```

### Multi-Timeframe Data Request

Agent requests data for:
- **HTF**: 4H, D, W (bias, WO, MO, RL Zone)
- **LTF**: 1H, 2H (structure, WO-MO/PWO-MO confluence)
- **mLTF**: 5m, 15m (confirmation CHoCH/BOS)

## Signal Generation Pipeline

### 1. Data Fetch
```python
async def fetch_market_data(symbol: str, timeframes: list[str]) -> dict:
    """Fetch OHLCV for all required timeframes."""
    data = {}
    for tf in timeframes:
        data[tf] = await tv_client.get_ohlcv(symbol, tf, limit=500)
    return data
```

### 2. Zone Detection
```python
class EfloudZoneDetector:
    def detect_zones(self, htf_data, ltf_data, mtf_data):
        zones = {
            'blue_boxes': [],      # Demand OBs
            'green_boxes': [],     # Pullback targets
            'red_boxes': [],       # Supply OBs
            'purple_box': None,    # RL Zone
            'red_lines': [],       # Key trendlines
            'wo_level': None,
            'mo_level': None,
            'pwo_level': None,
            'fvgs': [],            # Imbalances
            'liquidity': [],       # Swing highs/lows, EQH/EQL
            'breakers': [],        # Breaker blocks
            'mitigations': []      # Mitigated levels
        }
        # ... detection logic
        return zones
```

### 3. Confirmation Check (mLTF)
```python
def check_confirmation(mtf_data, direction: str, zone_price: float) -> bool:
    """Check mLTF (5m/15m) for CHoCH/BOS in trade direction."""
    # Bullish: CHoCH up (lower low → higher high) + close above
    # Bearish: CHoCH down (higher high → lower low) + close below
    # Must occur near zone_price
    return confirmation_found
```

### 4. Signal Assembly
```python
@dataclass
class EfloudSignal:
    symbol: str
    direction: str          # LONG / SHORT
    entry_zone: str         # BLUE_BOX / GREEN_BOX / RED_BOX / RL_ZONE
    entry_price: float
    stop_loss: float
    tp1: float              # First liquidity
    tp2: float              # WO/MO/PWO
    tp3: float              # Red Line / RL Zone
    confirmation_tf: str    # 5m / 15m
    confirmation_type: str  # CHoCH / BOS
    ht_bias: str            # BULLISH / BEARISH / NEUTRAL
    ltf_confluence: list    # WO-MO, PWO-MO, etc.
    risk_reward: float
    setup_quality: str      # A+ / A / B / RANGE
    timestamp: datetime
    chart_url: str          # TradingView chart link
```

## Webhook Endpoint

### Flask/FastAPI Example
```python
from fastapi import FastAPI, Request

app = FastAPI()

@app.post("/webhook/tradingview")
async def tradingview_webhook(request: Request):
    payload = await request.json()
    
    # Parse TradingView alert
    symbol = payload.get("symbol")
    timeframe = payload.get("timeframe")
    message = payload.get("message")  # Custom alert message
    
    # Trigger analysis
    signal = await analyze_symbol(symbol)
    
    if signal and signal.meets_entry_criteria():
        await send_to_order_manager(signal)
        await notify_telegram(signal)
    
    return {"status": "ok"}
```

### TradingView Alert Message Format
```json
{
  "symbol": "{{ticker}}",
  "timeframe": "{{interval}}",
  "price": {{close}},
  "message": "EFLOUD_SMC_CHECK",
  "zone_type": "{{plot_0}}",  // From Pine Script
  "zone_price": {{plot_1}}
}
```

## Chart Analysis via Vision (Alternative)

For manual chart images from Telegram export:

```python
async def analyze_chart_image(image_path: str) -> dict:
    """Extract zones from chart screenshot using vision."""
    prompt = """
    Analyze this TradingView chart for Efloud SMC zones:
    1. Identify colored boxes: Blue (demand), Green (pullback), Red (supply), Purple (RL Zone)
    2. Find Red Lines (key trendlines)
    3. Mark WO, MO, PWO levels
    4. Detect FVGs/Imbalances
    5. Mark swing highs/lows and EQH/EQL
    6. Identify any Breaker/Mitigation blocks
    7. Note current price relative to zones
    Return structured JSON.
    """
    return await vision_model.analyze(image_path, prompt)
```

## Integration with efloud-bot

### Signal → Order Flow
```
EfloudSignal → SafeOrchestrator.run_cycle()
    → PositionGuard.can_open_position()
    → OrderManager.open_position()
    → Server-side SL/TP placement
    → Reconcile each cycle
```

### Config Mapping
```yaml
# config.yaml additions for TradingView integration
tradingview:
  enabled: true
  webhook_url: "http://localhost:8080/webhook/tradingview"
  symbols: ["BTCUSDT", "ETHUSDT", "SOLUSDT", ...]
  timeframes:
    htf: ["4H", "D", "W"]
    ltf: ["1H", "2H"]
    mtf: ["5m", "15m"]
  pine_script_id: "your_script_id"
  alert_webhook_secret: "secret_key"
```

## Message References for Validation

| Message | Symbol | Expected Signal |
|---------|--------|-----------------|
| 11 | DXY | SHORT at Red Line, TP at Filled Gap |
| 12 | ETHUSDT | LONG at Blue Box, TP at MO |
| 17 | AVAXUSDT | LONG at Breaker/Mitigation, TP $13.75 |
| 19 | LINKUSDT | LONG at Imbalance confluence, TP $7.22 |
| 20 | BTCUSD | LONG at WO-MO confluence, respect RL Zone |
| 21 | BNBUSDT | Partial TP at $251, re-entry $238 |
| 30 | PEPEUSDT | SHORT only with confirmation |
| 31 | BTCUSD HTF | Range play $28.5k-$30k |
| 32 | LTCUSDT | LONG at Green Box $78.5, TP MO $90 |
| 34 | PEPEUSDT | LONG at mitigation + confirmation |

## Testing Checklist

- [ ] Webhook receives TradingView alerts
- [ ] Zone detection matches manual analysis
- [ ] Confirmation check works on 5m/15m
- [ ] Signal R:R calculation correct
- [ ] Order placement via OrderManager
- [ ] Reconcile handles TP/SL correctly
- [ ] Portfolio heat limits enforced
- [ ] Telegram notifications sent

## Deployment Notes

- Run webhook server on same VPS as efloud-bot
- Use ngrok/Cloudflare Tunnel for TradingView webhook URL
- Secure with secret token validation
- Monitor webhook latency (< 500ms target)
- Log all signals for audit/backtest