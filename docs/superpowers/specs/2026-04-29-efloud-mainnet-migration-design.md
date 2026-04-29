# Efloud Bot Mainnet Migration Design
**Date:** 2026-04-29  
**Author:** Claude + User  
**Status:** Approved for Implementation

## Executive Summary

Migration of Efloud SMC trading bot from testnet simulation to live mainnet trading with real funds. The migration implements a 3-phase safety approach with custom risk management for a $1300 futures portfolio, API-based permission detection, and comprehensive safety systems.

## Current State Analysis

**Existing Configuration:**
- **Mode**: Testnet + dry_run simulation
- **Balance**: Config shows 10,000 USDT (placeholder)
- **Risk**: 0.75% per trade, max 7 positions
- **Leverage**: 3x (correct)
- **R:R**: 1:2 minimum (correct)

**Actual Portfolio:**
- **Futures Balance**: 1,250 USDT + 0.10 BNB ≈ $1,300
- **Spot Balance**: $750
- **Total**: $2,196

## Requirements

### Risk Management Rules
**CORRECTED CALCULATION** (fixing critical mathematical error from original):

1. **Maximum Loss**: 2% of total balance per trade (20 USDT max loss for 1000 USDT balance)
2. **Position Size Calculation**: Reverse-engineered from max loss tolerance
   - With 3x leverage and 2% max loss: Position size = (20 USDT / 0.10) / 3 = 66.67 USDT
   - This gives 10% stop loss distance: 20 USDT loss / (66.67 × 3) = 10% price movement
3. **Leverage**: 3x with isolated margin mode  
4. **Revised Position Size**: ~6.67% of balance (not 10%) for safety compliance

### API Permission Management
- **Auto-detect trading permissions** via Binance API account info
- **Tradeable symbols**: Execute normal SMC analysis + orders
- **Read-only symbols**: Analysis only + terminal notifications
- **Dynamic updates**: Support for adding/removing coins via API permissions

### Notification System
- **Terminal-based notifications** for read-only symbols
- **Format**: `🔍 [READONLY] BTC/USDT: BULLISH SIGNAL | Entry: 43,250 | TP1: 45,500 | SL: 41,800`

## Architecture Design

### 1. Configuration Changes

#### Risk Management Overhaul
```yaml
# Updated risk configuration (CORRECTED)
risk:
  starting_balance: 1000              # Actual futures balance
  max_loss_per_trade_usdt: 20         # Absolute dollar risk (2% of 1000 USDT)
  target_stop_distance_pct: 10        # Target 10% stop loss for safety
  max_open_positions: 4               # Conservative: max 80 USDT total risk
  min_rr: 2.0                        # Keep existing 1:2 requirement
  position_size_calculation: "reverse_from_risk"  # Calculate from max loss tolerance
  
exchange:
  leverage: 3                        # Keep existing
  margin_mode: "isolated"            # New: force isolated margin
```

#### Risk Calculator Implementation (CORRECTED)
```python
class CustomRiskCalculator:
    def __init__(self, max_loss_usdt: float = 20.0, leverage: int = 3, target_stop_pct: float = 0.10):
        self.max_loss_usdt = max_loss_usdt
        self.leverage = leverage
        self.target_stop_pct = target_stop_pct
    
    def calculate_position_size(self, available_balance: float) -> float:
        """Calculate position size from maximum acceptable loss"""
        # Reverse calculation: position_size = max_loss / (stop_distance * leverage)
        position_size = self.max_loss_usdt / (self.target_stop_pct * self.leverage)
        
        # Ensure position doesn't exceed available balance
        max_allowed = available_balance * 0.80  # Never use more than 80% of balance
        return min(position_size, max_allowed)
    
    def calculate_notional_exposure(self, position_size: float) -> float:
        """Calculate total notional exposure with leverage"""
        return position_size * self.leverage
    
    def validate_risk_parameters(self, position_size: float, current_price: float, stop_price: float) -> dict:
        """Validate that trade meets risk requirements"""
        actual_stop_distance = abs(current_price - stop_price) / current_price
        notional = position_size * self.leverage
        potential_loss = notional * actual_stop_distance
        
        return {
            'valid': potential_loss <= self.max_loss_usdt,
            'potential_loss_usdt': potential_loss,
            'stop_distance_pct': actual_stop_distance * 100,
            'max_allowed_loss': self.max_loss_usdt
        }
```

### 2. API Permission Detection System

#### Permission Manager
```python
class PermissionManager:
    def __init__(self, client: BinanceClient):
        self.client = client
        self.tradeable_symbols = []
        self.readonly_symbols = []
    
    def detect_permissions(self, symbol_list: list) -> dict:
        """Detect trading permissions for symbol list"""
        account_info = self.client.get_futures_account()
        permissions = {}
        
        for symbol in symbol_list:
            if self.can_trade_symbol(symbol, account_info):
                permissions[symbol] = "tradeable"
                self.tradeable_symbols.append(symbol)
            else:
                permissions[symbol] = "readonly"
                self.readonly_symbols.append(symbol)
        
        return permissions
    
    def can_trade_symbol(self, symbol: str, account_info: dict) -> bool:
        """Check if symbol can be traded via API restrictions"""
        try:
            # 1. Check if symbol exists in futures exchange
            exchange_info = self.client.get_exchange_info()
            symbol_info = next((s for s in exchange_info['symbols'] if s['symbol'] == symbol.replace('/', '')), None)
            if not symbol_info or symbol_info['status'] != 'TRADING':
                return False
            
            # 2. Check account trading permissions
            if account_info.get('canTrade', False) == False:
                return False
                
            # 3. Validate minimum order size requirements
            min_qty = float(symbol_info['filters'][0]['minQty'])  # LOT_SIZE filter
            min_notional = float(symbol_info['filters'][5]['minNotional'])  # MIN_NOTIONAL filter
            
            # Check if we can meet minimum requirements with our position sizing
            test_position = 67  # USDT (revised position size)
            test_notional = test_position * 3  # With 3x leverage
            
            return test_notional >= min_notional
            
        except Exception as e:
            logging.error(f"Permission check failed for {symbol}: {e}")
            return False  # Fail safe: deny trading if check fails
```

#### Notification System
```python
class NotificationManager:
    def send_readonly_signal(self, symbol: str, signal_data: dict):
        """Send terminal notification for read-only symbols"""
        direction = signal_data['direction']
        entry = signal_data['entry_price']
        tp1 = signal_data['tp1']
        sl = signal_data['sl']
        
        message = f"🔍 [READONLY] {symbol}: {direction} SIGNAL | Entry: {entry:,.0f} | TP1: {tp1:,.0f} | SL: {sl:,.0f}"
        
        # Terminal output
        print(message)
        
        # Log to file
        logging.getLogger("efloud.signals").info(message)
```

### 3. Enhanced Safety Systems

#### Updated Circuit Breakers
```yaml
safety:
  # Daily/Weekly limits adjusted for smaller balance
  daily_loss_limit_pct: 2.0           # 20 USDT max loss per day
  weekly_drawdown_limit_pct: 6.0      # 60 USDT max weekly loss
  consecutive_loss_limit: 2           # More aggressive stopping
  consecutive_pause_min: 60           # 1 hour pause (faster recovery)
  
  # Position guards for 1000 USDT balance
  max_position_notional_pct: 10.0     # Matches position size rule
  max_total_exposure: 2.0             # Max 2000 USDT total notional
  min_balance_reserve: 50             # Always keep 50 USDT reserve
  max_holding_hours: 24               # Faster position cycling
  
  # Emergency stops
  emergency_balance_threshold: 950    # Stop if balance < 950 USDT
  max_single_loss: 25                 # Stop if any position loses > 25 USDT
```

#### Pre-Trade Validation
```python
class SafetyValidator:
    def validate_trade_entry(self, symbol: str, position_size: float, current_balance: float) -> bool:
        """Comprehensive pre-trade safety check"""
        checks = [
            self.check_balance_sufficient(position_size, current_balance),
            self.check_daily_loss_limit(),
            self.check_position_count_limit(),
            self.check_symbol_permissions(symbol),
            self.check_margin_mode_isolated(),
            self.check_emergency_thresholds(current_balance)
        ]
        
        return all(checks)
    
    def check_emergency_thresholds(self, balance: float) -> bool:
        """Emergency stop conditions"""
        if balance < 950:  # 5% total loss
            logging.error("🚨 EMERGENCY STOP: Balance below 950 USDT")
            return False
        return True
```

### 4. Phase Implementation Plan

#### Phase 1: Mainnet Dry Run (Day 1)
**Configuration**: `config.phase1.yaml`
```yaml
exchange:
  testnet: false                     # Real market data
operation:
  dry_run: true                      # Zero risk
  log_level: DEBUG                   # Verbose logging
```

**Success Criteria:**
- 2-3 complete analysis cycles without errors
- API permission detection working
- Risk calculations accurate
- Terminal notifications functional

#### Phase 2: Live Trading - Reduced Scale (Days 2-3)
**Configuration**: `config.phase2.yaml`
```yaml
risk:
  max_loss_per_trade_usdt: 10         # Reduced risk: 1% of balance  
  target_stop_distance_pct: 10        # Same stop distance
  max_open_positions: 2               # Limited exposure (max 20 USDT total risk)
operation:
  dry_run: false                     # Live trading
  check_interval_sec: 60             # More frequent monitoring
  position_size_calculation: "reverse_from_risk"
```

**Success Criteria:**
- 3-5 successful live trades
- Positive or neutral P&L
- No safety system violations
- User comfort with live operation

#### Phase 3: Full Scale (Day 7+)
**Configuration**: `config.phase3.yaml`
```yaml
risk:
  max_loss_per_trade_usdt: 20         # Full risk: 2% of balance
  target_stop_distance_pct: 10        # 10% stop distance  
  max_open_positions: 4               # Full capacity (max 80 USDT total risk)
operation:
  check_interval_sec: 30             # Normal monitoring
  position_size_calculation: "reverse_from_risk"
```

**Success Criteria:**
- Stable weekly performance
- Risk management compliance
- Automated operation confidence

### 5. File Structure Changes

```
efloud-bot-v2.1.1.8/
├── configs/
│   ├── config.phase1.yaml          # Mainnet dry run
│   ├── config.phase2.yaml          # Reduced live trading
│   └── config.phase3.yaml          # Full scale live
├── engine/
│   ├── risk/
│   │   └── custom_calculator.py    # New risk calculation
│   ├── permissions/
│   │   └── manager.py              # API permission detection
│   └── notifications/
│       └── terminal.py             # Terminal notification system
└── docs/
    └── migration-log.md            # Phase execution log
```

## Implementation Checklist

### Core Changes
- [ ] Create CustomRiskCalculator class
- [ ] Implement PermissionManager with API detection
- [ ] Build NotificationManager for terminal output
- [ ] Update SafetyValidator with new thresholds
- [ ] Create phase-specific configuration files

### Integration Points
- [ ] Integrate PermissionManager into main loop symbol resolution
- [ ] Replace existing risk calculation with CustomRiskCalculator
- [ ] Add NotificationManager to SafeOrchestrator for read-only symbols
- [ ] Update MainnetGuard to support phase-specific warnings

### Testing & Validation
- [ ] Unit tests for new risk calculation logic
- [ ] Integration tests for permission detection
- [ ] Dry run validation of all systems
- [ ] Manual verification of terminal notifications

### Documentation
- [ ] Update CLAUDE.md with new risk rules
- [ ] Create migration execution log template
- [ ] Document emergency procedures

## Risk Mitigation

### Technical Risks
- **API Permission Detection Failure**: Fallback to manual symbol whitelist
- **Risk Calculation Errors**: Extensive unit testing + dry run validation
- **Connection Issues**: Enhanced retry logic + emergency stops

### Financial Risks
- **Excessive Losses**: Multiple circuit breakers at 2%, 6%, and emergency levels
- **Position Size Errors**: Pre-trade validation + real-time balance checks
- **Leverage Misconfiguration**: Force isolated margin mode + validation

### Operational Risks
- **Configuration Errors**: Phase-based configs + manual review between phases
- **Monitoring Gaps**: Enhanced logging + terminal notifications
- **Emergency Situations**: Clear stop procedures + balance thresholds

## Success Metrics

### Phase 1 (Dry Run)
- Zero configuration errors
- 100% API permission accuracy
- All safety systems functional

### Phase 2 (Reduced Live)
- Positive or neutral P&L over 5 trades
- Zero safety violations
- < 1% daily loss

### Phase 3 (Full Scale)  
- Consistent weekly positive performance
- Risk management compliance > 95%
- Automated operation confidence

## Conclusion

This design provides a structured, safety-first approach to migrating from testnet to live trading with real funds. The 3-phase implementation allows for thorough validation at each step, while the custom risk management system ensures appropriate position sizing for the actual portfolio balance.

The API-based permission detection provides flexibility for dynamic symbol management, and the comprehensive safety systems protect against both technical failures and market volatility.

Implementation should proceed only after thorough review and testing of each component, with particular attention to the risk calculation logic and safety thresholds.