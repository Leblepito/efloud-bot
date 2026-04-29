# Efloud Bot Mainnet Migration Scripts

This directory contains the execution scripts for the 3-phase mainnet migration process.

## Overview

The migration follows a progressive approach:
- **Phase 1**: Mainnet dry run (real data, no real orders)
- **Phase 2**: Live trading with reduced risk (10 USDT max loss per trade)
- **Phase 3**: Full scale live trading (20 USDT max loss per trade)

## Scripts

### `execute_phase1.py`
- Executes Phase 1: Mainnet dry run
- Uses real market data but places NO real orders
- Validates safety systems and risk calculations
- **Requirements**: `BINANCE_API_KEY`, `BINANCE_API_SECRET`

### `execute_phase2.py`
- Executes Phase 2: Live trading with reduced risk
- **WARNING**: Trades with REAL MONEY
- **Requirements**: 
  - Successful Phase 1 completion
  - `EFLOUD_ALLOW_MAINNET=1` environment variable
  - `BINANCE_API_KEY`, `BINANCE_API_SECRET`
- User confirmation required before trading

### `execute_phase3.py`
- Executes Phase 3: Full scale live trading
- **WARNING**: Trades with FULL RISK
- **Requirements**:
  - Successful Phase 1 AND Phase 2 completion
  - `EFLOUD_ALLOW_MAINNET=1` environment variable
  - `BINANCE_API_KEY`, `BINANCE_API_SECRET`
- User confirmation required before trading

### `validate_phase_completion.py`
- Validates phase completion status
- Checks readiness for next phase
- Usage: `python scripts/validate_phase_completion.py {1|2|3|all}`

## Usage Examples

```bash
# Check system readiness
python scripts/validate_phase_completion.py all

# Execute Phase 1 (dry run)
python scripts/execute_phase1.py

# Validate Phase 1 completion
python scripts/validate_phase_completion.py 1

# Execute Phase 2 (live trading - reduced risk)
export EFLOUD_ALLOW_MAINNET=1
python scripts/execute_phase2.py

# Validate Phase 2 completion  
python scripts/validate_phase_completion.py 2

# Execute Phase 3 (full scale trading)
python scripts/execute_phase3.py
```

## Safety Features

1. **Environment Protection**: Live trading requires `EFLOUD_ALLOW_MAINNET=1`
2. **Phase Progression**: Later phases require completion of earlier phases
3. **User Confirmation**: Live trading phases require explicit user confirmation
4. **Risk Limits**: Each phase has specific risk limitations
5. **Comprehensive Logging**: All executions are logged with timestamps

## Configuration Files Required

- `configs/config.phase1.yaml` - Phase 1 configuration
- `configs/config.phase2.yaml` - Phase 2 configuration  
- `configs/config.phase3.yaml` - Phase 3 configuration

## Environment Variables

```bash
# Required for all phases
export BINANCE_API_KEY="your_api_key"
export BINANCE_API_SECRET="your_api_secret"

# Required for live trading phases (2 and 3)
export EFLOUD_ALLOW_MAINNET=1
```

## Safety Warnings

⚠️ **Phase 2 and 3 trade with REAL MONEY**
⚠️ **Ensure you understand the risks before proceeding**
⚠️ **Start with small amounts and monitor closely**
⚠️ **Have stop-loss mechanisms in place**

## Support

For issues or questions, refer to the main project documentation and the MAINNET_GECIS_REHBERI.md file.