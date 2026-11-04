---
name: efloud-master-orchestrator
description: "Master orchestrator for Efloud SMC trading agents."
version: 1.0.0
author: Hermes Agent
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [orchestration, agent, trading-bot, smc, automation]
    related_skills: [efloud-smc-concepts, efloud-smc-setup-rules, efloud-risk-management, efloud-tradingview-integration]
---

> ⚠️ **INCUBATOR TASLAĞI — AKTİF DEĞİL.** Yazar: hermes (commit `645a5dc`). Kullanmadan önce aynı klasördeki `REVIEW.md`'yi oku; buradaki sayılar canlı config DEĞİLDİR (kaynak: `configs/config.phase2_1k.yaml`).

# Efloud Master Orchestrator

## When to Use

Use as the main entry point for autonomous trading agents that implement the full Efloud SMC/Price Action methodology. Coordinates data fetching, analysis, signal generation, risk checks, and order execution.

## Agent Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    Efloud Master Agent                       │
├─────────────────────────────────────────────────────────────┤
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────┐  │
│  │ Data Layer  │→ │ Analysis    │→ │ Signal & Risk       │  │
│  │ (TV/Exchange)│  │ (SMC Engine)│  │ (Setup Rules + Risk)│  │
│  └─────────────┘  └─────────────┘  └─────────────────────┘  │
│         │               │                    │               │
│         ▼               ▼                    ▼               │
│  ┌─────────────────────────────────────────────────────┐   │
│  │              Order Execution Layer                   │   │
│  │  (OrderManager → Exchange → Reconcile → Journal)    │   │
│  └─────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────┘
```

## Main Loop (Per Symbol, Per Cycle)

```python
class EfloudMasterAgent:
    def __init__(self, config: dict):
        self.config = config
        self.tv_client = TradingViewClient(config['tradingview'])
        self.exchange = BinanceClient(config['exchange'])
        self.zone_detector = EfloudZoneDetector()
        self.setup_rules = EfloudSetupRules()
        self.risk_mgmt = EfloudRiskManagement()
        self.order_mgr = OrderManager(self.exchange, config)
        self.state = AgentState()
    
    async def run_cycle(self, symbol: str):
        # 1. FETCH: Multi-timeframe data
        data = await self.fetch_multitf_data(symbol)
        
        # 2. ANALYZE: Detect zones & structure
        zones = self.zone_detector.detect(data)
        
        # 3. BIAS: Determine HTF direction
        bias = self.determine_htf_bias(data['htf'], zones)
        
        # 4. SETUP: Find valid setups per rules
        setups = self.setup_rules.find_setups(symbol, bias, zones, data)
        
        # 5. CONFIRM: Check mLTF confirmation
        confirmed = [s for s in setups if self.check_confirmation(s, data['mtf'])]
        
        # 6. RISK: Validate against risk limits
        valid = [s for s in confirmed if self.risk_mgmt.validate(s, self.state)]
        
        # 7. EXECUTE: Place orders
        for setup in valid:
            await self.execute_setup(setup)
        
        # 8. MANAGE: Reconcile open positions
        await self.order_mgr.reconcile()
        
        # 9. JOURNAL: Record state
        self.state.persist()
```

## Skill Coordination

| Phase | Skill Used | Output |
|-------|------------|--------|
| Data Fetch | efloud-tradingview-integration | OHLCV per TF |
| Zone Detection | efloud-smc-concepts | Colored zones, levels |
| Bias & Confluence | efloud-smc-concepts | HTF bias, WO/MO/PWO/RL |
| Setup Evaluation | efloud-smc-setup-rules | Valid setups with entry/SL/TP |
| Confirmation Check | efloud-smc-setup-rules | mLTF CHoCH/BOS verified |
| Risk Validation | efloud-risk-management | Position size, heat check |
| Order Execution | (efloud-bot engine) | Server-side SL/TP |
| Reconcile | (efloud-bot engine) | Exchange ↔ Local sync |

## Configuration

```yaml
# master_agent.yaml
agent:
  symbols:
    - BTCUSDT
    - ETHUSDT
    - SOLUSDT
    - BNBUSDT
    - XRPUSDT
    - LINKUSDT
    - AVAXUSDT
    - LTCUSDT
    - DOTUSDT
    - ADAUSDT
  
  timeframes:
    htf: ["4H", "D", "W"]
    ltf: ["1H", "2H"]
    mtf: ["5m", "15m"]
  
  cycle_interval_sec: 300  # 5 minutes
  
  tradingview:
    enabled: true
    webhook_port: 8080
    
  exchange:
    name: binance
    market_type: futures
    testnet: false
    
  risk:
    max_daily_loss_pct: 3.0
    max_weekly_dd_pct: 8.0
    max_concurrent_risk_pct: 5.0
    max_positions: 8
    risk_per_trade_pct: 1.5
    
  setup_rules:
    min_rr: 1.5
    require_confirmation: true
    confirmation_tfs: ["5m", "15m"]
    
  zones:
    colors:
      demand: "blue"      # Blue Box
      pullback: "green"   # Green Box
      supply: "red"       # Red Box
      rl_zone: "purple"   # Purple Box
      trendline: "red"    # Red Line
```

## State Management

```python
@dataclass
class AgentState:
    # Portfolio
    balance: float
    equity: float
    open_positions: dict[str, Position]
    daily_pnl: float
    weekly_pnl: float
    
    # Risk
    consecutive_losses: int
    last_trade_time: datetime
    heat_by_symbol: dict[str, float]
    
    # Signals
    active_setups: dict[str, Setup]
    pending_confirmations: dict[str, Confirmation]
    
    # Journal
    trade_journal: list[TradeRecord]
    
    def persist(self):
        """Save to JSON/DB for crash recovery."""
        
    def restore(self):
        """Load on startup."""
```

## Error Handling & Resilience

| Error Type | Handling |
|------------|----------|
| TV webhook timeout | Retry 3x, fallback to tvDatafeed |
| Exchange API error | Exponential backoff, max 3 retries |
| Zone detection failure | Skip symbol, alert operator |
| Confirmation timeout | Cancel pending setup |
| Order placement fail | Rollback, alert, journal |
| Reconcile mismatch | Force sync from exchange |
| Network partition | Pause trading, preserve state |

## Monitoring & Alerts

### Key Metrics
- **Signal generation rate**: setups/cycle
- **Confirmation rate**: confirmed/setups
- **Fill rate**: executed/confirmed
- **Win rate**: winning trades / total
- **Avg R:R**: realized
- **Portfolio heat**: current vs limit
- **Daily/weekly PnL**: vs limits

### Alert Channels
- Telegram: trade signals, errors, daily summary
- Webhook: custom integrations
- Logs: structured JSON for analysis

## Deployment

### Docker Compose (Add to efloud-bot stack)
```yaml
services:
  efloud-master-agent:
    image: efloud-bot:latest
    command: python -m agents.master_agent
    env_file: .env.production
    volumes:
      - efloud_state:/app/state
      - efloud_logs:/app/logs
    depends_on:
      - efloud-bot
    restart: unless-stopped
```

### Scaling
- **Single agent**: All symbols, sequential cycles
- **Parallel agents**: Split symbols across agents (per efloud-bot V2/V3 pattern)
- **Stateless workers**: Zone detection, confirmation check can be parallelized

## Message Validation Reference

Test agent against these 35 messages:

| Msg | Symbol | Expected Agent Action |
|-----|--------|----------------------|
| 11 | DXY | Detect Red Line, bearish conf → SHORT |
| 12 | ETHUSDT | Blue Box + mLTF conf → LONG, TP MO |
| 17 | AVAXUSDT | Breaker/Mitigation + conf → LONG |
| 19 | LINKUSDT | Imbalance confluence + pullback → LONG |
| 20 | BTCUSD | RL Zone respect, WO-MO conf → LONG |
| 21 | BNBUSDT | Zone mapping, partial TP, re-entry |
| 22 | BTCUSD | Stop to entry, risk off |
| 26 | LINKUSDT | Resistance TP, pullback target |
| 28 | LINKUSDT | Full exit at resistance |
| 29 | BTCUSD | RL Zone hold, no add |
| 30 | PEPEUSDT | No conf → NO TRADE |
| 31 | BTCUSD HTF | Range play detection |
| 32 | LTCUSDT | Green Box wait, conf → LONG |
| 33 | BTCUSD LTF | PWO-MO, profit taking |
| 34 | PEPEUSDT | Mitigation + conf → LONG |
| 35 | LINKUSDT | 11% TP, 5% pullback, re-entry |

## Backtest Validation

Run agent in shadow mode on historical data:
1. Replay TV data for Aug 2023
2. Compare agent signals vs actual messages
3. Target: ≥ 80% signal match, ≥ 60% win rate
4. Tune zone detection, confirmation sensitivity

## Future Extensions

- **ML-enhanced zone detection**: Train on chart images
- **Multi-agent swarm**: Specialized agents per symbol/group
- **Adaptive risk**: Kelly criterion based on win rate
- **Cross-exchange arbitrage**: Spot/futures basis trades
- **On-chain data integration**: Funding rates, open interest