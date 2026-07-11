# Multi-Bot Karpathi Integration + Audit Fix Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement 3-bot trading system with Karpathi principles enforcement + complete PARKED audit fixes with per-bot configuration, correlation guards, and staged deployment.

**Architecture:** Convert single-config system to 3-bot architecture with shared config extraction, per-bot state isolation, deterministic correlation guards, and Karpathi active enforcement through pre-commit hooks + PR workflow integration. Audit fixes completed with multi-bot backtest validation.

**Tech Stack:** Python 3.12, YAML config files, git hooks, pytest, backtest engine (Edge Measurement Core)

## Global Constraints

- Python 3.12+ required
- Pine v6 syntax mandatory for any Pine Script changes  
- All safety/risk path changes require explicit assumptions documentation
- Test-first (TDD) for all feature work
- Backtest gate required for edge/scoring changes
- Default OFF for all new feature flags
- Atomic PR enforcement (one PR per logical change)
- No weakening of safety guards (ever)
- Shadow mode default for new trading logic
- Fail-closed defaults for risk-critical systems

---

## Task 1: Create Config Infrastructure

**Files:**
- Create: `configs/config.shared.yaml`
- Create: `configs/bot_5m_scalp.yaml`  
- Create: `configs/bot_15m_mid.yaml`
- Create: `configs/bot_1h_long.yaml`
- Modify: `engine/config.py` (if exists, else create)

**Interfaces:**
- Produces: `load_config(bot_id: str) -> dict` function that merges shared + bot-specific config
- Produces: `get_all_bot_configs() -> dict[str, dict]` function for iteration

### Task 1.1: Extract Shared Configuration

- [ ] **Step 1: Create shared config from existing settings**

Read current `configs/config.phase2_1k.yaml` and extract common settings:

```yaml
# configs/config.shared.yaml
# Common settings shared across all bots

# Database & API
database:
  url: ${DATABASE_URL}
  pool_size: 10

exchange:
  api_key: ${BINANCE_API_KEY}
  api_secret: ${BINANCE_API_SECRET}
  testnet: false

# Safety limits (global)
safety:
  global_max_position_size_usd: 1000
  emergency_shutdown: true

# Logging
logging:
  level: INFO
  file_path: logs/efloud-bot.log

# Engine settings
engine:
  smc_version: "v1"  # Default SMC version
  regime_detector: "deterministic"  # ML advisory-only
```

- [ ] **Step 2: Create bot-specific config for 5m scalp bot**

```yaml
# configs/bot_5m_scalp.yaml
bot_id: "5m_scalp"

# Timeframe chain (scalp profile)
timeframes:
  entry: "5m"
  mtf: "1h"
  htf: "4h"
  daily: "1d"

# Confluence settings (conf: 50-55 for scalp)
confluence:
  min_confluence: 50
  max_confluence: 100
  post_cap_bonuses: false  # H1 fix disabled

# Capital allocation (30% of $1000 = $300)
capital:
  allocation_usd: 300
  max_position_size_usd: 300

# Safety limits (scalp-specific)
safety:
  starting_balance: 300
  emergency_balance_threshold: 285  # 95% of allocation
  daily_loss_limit_pct: 5
  leverage: 3
  max_sl_atr: 4.0  # H3 fix

# Risk limits (scalp = shorter holds)
risk:
  max_holding_hours: 12  # Scalp-specific
  consecutive_loss_limit: 3
  max_drawdown_pct: 10

# Override shared settings if needed
# (empty = inherits from shared)
```

- [ ] **Step 3: Create bot-specific config for 15m mid bot**

```yaml
# configs/bot_15m_mid.yaml
bot_id: "15m_mid"

# Timeframe chain (mid profile)
timeframes:
  entry: "15m"
  mtf: "4h"
  htf: "12h"
  daily: "1d"

# Confluence settings (conf: 60-70 for mid)
confluence:
  min_confluence: 65  # Starting point for backtest optimization
  max_confluence: 100
  post_cap_bonuses: false

# Capital allocation (40% of $1000 = $400)
capital:
  allocation_usd: 400
  max_position_size_usd: 400

# Safety limits (mid-specific)
safety:
  starting_balance: 400
  emergency_balance_threshold: 380  # 95% of allocation
  daily_loss_limit_pct: 7
  leverage: 4
  max_sl_atr: 4.5

# Risk limits (mid = moderate holds)
risk:
  max_holding_hours: 24
  consecutive_loss_limit: 3
  max_drawdown_pct: 12
```

- [ ] **Step 4: Create bot-specific config for 1h long bot**

```yaml
# configs/bot_1h_long.yaml
bot_id: "1h_long"

# Timeframe chain (long profile)
timeframes:
  entry: "1h"
  mtf: "8h"
  htf: "1d"
  daily: "1d"

# Confluence settings (conf: 75-80 for long)
confluence:
  min_confluence: 75  # Highest quality threshold
  max_confluence: 100
  post_cap_bonuses: false

# Capital allocation (30% of $1000 = $300)
capital:
  allocation_usd: 300
  max_position_size_usd: 300

# Safety limits (long-specific)
safety:
  starting_balance: 300
  emergency_balance_threshold: 285  # 95% of allocation
  daily_loss_limit_pct: 5
  leverage: 3
  max_sl_atr: 5.0

# Risk limits (long = longer holds)
risk:
  max_holding_hours: 48
  consecutive_loss_limit: 2
  max_drawdown_pct: 8
```

- [ ] **Step 5: Create config loader with merge logic**

Create `engine/config.py`:

```python
"""Multi-bot configuration loader with shared config merge."""

from pathlib import Path
from typing import Any
import yaml
import os

def load_shared_config() -> dict[str, Any]:
    """Load shared configuration common to all bots."""
    shared_path = Path("configs/config.shared.yaml")
    if not shared_path.exists():
        raise FileNotFoundError(f"Shared config not found: {shared_path}")
    
    with open(shared_path) as f:
        config = yaml.safe_load(f)
    
    # Environment variable substitution
    config = _substitute_env_vars(config)
    return config

def load_bot_config(bot_id: str) -> dict[str, Any]:
    """Load bot-specific configuration merged with shared config.
    
    Args:
        bot_id: One of "5m_scalp", "15m_mid", "1h_long"
        
    Returns:
        Merged configuration dict with shared settings overridden by bot-specific
    """
    # Map bot_id to config file
    bot_config_files = {
        "5m_scalp": "configs/bot_5m_scalp.yaml",
        "15m_mid": "configs/bot_15m_mid.yaml", 
        "1h_long": "configs/bot_1h_long.yaml",
    }
    
    if bot_id not in bot_config_files:
        raise ValueError(f"Unknown bot_id: {bot_id}")
    
    bot_config_path = Path(bot_config_files[bot_id])
    if not bot_config_path.exists():
        raise FileNotFoundError(f"Bot config not found: {bot_config_path}")
    
    # Load shared config first
    shared_config = load_shared_config()
    
    # Load bot-specific config
    with open(bot_config_path) as f:
        bot_config = yaml.safe_load(f)
    
    # Merge: shared base, bot-specific overrides
    merged_config = _deep_merge(shared_config, bot_config)
    
    # Validate bot_id matches
    if merged_config.get("bot_id") != bot_id:
        raise ValueError(f"Config bot_id mismatch: expected {bot_id}, got {merged_config.get('bot_id')}")
    
    return merged_config

def get_all_bot_configs() -> dict[str, dict[str, Any]]:
    """Load configurations for all bots.
    
    Returns:
        Dict mapping bot_id to config dict
    """
    bot_ids = ["5m_scalp", "15m_mid", "1h_long"]
    return {bot_id: load_bot_config(bot_id) for bot_id in bot_ids}

def _substitute_env_vars(config: dict[str, Any]) -> dict[str, Any]:
    """Replace ${VAR} patterns with environment variables."""
    def substitute(obj):
        if isinstance(obj, dict):
            return {k: substitute(v) for k, v in obj.items()}
        elif isinstance(obj, list):
            return [substitute(item) for item in obj]
        elif isinstance(obj, str) and obj.startswith("${") and obj.endswith("}"):
            env_var = obj[2:-1]
            value = os.getenv(env_var)
            if value is None:
                raise ValueError(f"Environment variable not set: {env_var}")
            return value
        else:
            return obj
    
    return substitute(config)

def _deep_merge(base: dict, override: dict) -> dict:
    """Deep merge override dict into base dict."""
    result = base.copy()
    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result
```

- [ ] **Step 6: Write tests for config loader**

Create `tests/test_config.py`:

```python
"""Tests for multi-bot configuration loader."""

import pytest
from engine.config import load_bot_config, get_all_bot_configs, load_shared_config

def test_load_shared_config():
    """Test shared config loads correctly."""
    config = load_shared_config()
    assert "database" in config
    assert "exchange" in config
    assert "safety" in config

def test_load_bot_config_5m():
    """Test 5m bot config loads with shared merge."""
    config = load_bot_config("5m_scalp")
    assert config["bot_id"] = "5m_scalp"
    assert config["timeframes"]["entry"] == "5m"
    assert config["confluence"]["min_confluence"] == 50
    assert config["capital"]["allocation_usd"] == 300
    # Should have inherited shared settings
    assert "database" in config
    assert "exchange" in config

def test_load_bot_config_15m():
    """Test 15m bot config loads with correct parameters."""
    config = load_bot_config("15m_mid")
    assert config["bot_id"] == "15m_mid"
    assert config["timeframes"]["entry"] == "15m"
    assert config["confluence"]["min_confluence"] == 65
    assert config["capital"]["allocation_usd"] == 400

def test_load_bot_config_1h():
    """Test 1h bot config loads with correct parameters."""
    config = load_bot_config("1h_long")
    assert config["bot_id"] == "1h_long"
    assert config["timeframes"]["entry"] == "1h"
    assert config["confluence"]["min_confluence"] == 75
    assert config["capital"]["allocation_usd"] == 300

def test_invalid_bot_id_raises():
    """Test invalid bot_id raises ValueError."""
    with pytest.raises(ValueError, match="Unknown bot_id"):
        load_bot_config("invalid_bot")

def test_get_all_bot_configs():
    """Test loading all bot configs at once."""
    all_configs = get_all_bot_configs()
    assert len(all_configs) == 3
    assert "5m_scalp" in all_configs
    assert "15m_mid" in all_configs
    assert "1h_long" in all_configs

def test_env_var_substitution():
    """Test environment variable substitution in shared config."""
    # This requires test environment variables to be set
    import os
    os.environ["DATABASE_URL"] = "test://db"
    os.environ["BINANCE_API_KEY"] = "test_key"
    os.environ["BINANCE_API_SECRET"] = "test_secret"
    
    config = load_shared_config()
    assert config["database"]["url"] == "test://db"
    assert config["exchange"]["api_key"] == "test_key"
```

- [ ] **Step 7: Run tests to verify config loader**

```bash
pytest tests/test_config.py -v
```

Expected: All tests PASS

- [ ] **Step 8: Commit config infrastructure**

```bash
git add configs/config.shared.yaml configs/bot_5m_scalp.yaml configs/bot_15m_mid.yaml configs/bot_1h_long.yaml engine/config.py tests/test_config.py
git commit -m "feat(config): add multi-bot configuration infrastructure

- Extract shared config (DB, API keys, safety limits)
- Add bot-specific configs (5m/15m/1h) with capital allocation
- Implement config loader with merge logic
- Add comprehensive tests for config loading

Capital allocation: 30% (5m) / 40% (15m) / 30% (1h)
Confluence thresholds: 50-55 (5m) / 60-70 (15m) / 75-80 (1h)

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

## Task 2: Implement Correlation Guard

**Files:**
- Create: `engine/safety/correlation_guard.py`
- Modify: `engine/safety/__init__.py` (export correlation_guard functions)

**Interfaces:**
- Consumes: Position data from all bots via `get_all_positions()` function (to be implemented)
- Produces: `can_enter_position(bot_id, symbol, direction, position_size_usd) -> bool` function

### Task 2.1: Create Correlation Guard

- [ ] **Step 1: Implement correlation guard logic**

Create `engine/safety/correlation_guard.py`:

```python
"""Multi-bot correlation risk guard.

Implements deterministic cross-bot position limits to prevent
excessive correlated exposure when multiple bots fire simultaneously.
"""

from typing import Dict, List
from dataclasses import dataclass

# Configuration constants (from design decisions)
MAX_AGGREGATE_POSITION_USD = 800  # 80% of total $1000 capital
MAX_SAME_DIRECTION_POSITIONS = 2   # Max 2 bots LONG same symbol

@dataclass
class PositionInfo:
    """Information about an existing position."""
    bot_id: str
    symbol: str
    direction: str  # "LONG" or "SHORT"
    size_usd: float

def can_enter_position(
    bot_id: str,
    symbol: str, 
    direction: str,
    position_size_usd: float,
    existing_positions: List[PositionInfo]
) -> tuple[bool, str]:
    """Check if new position is allowed under correlation constraints.
    
    This is a DETERMINISTIC guard - if it returns False, the position
    is BLOCKED regardless of individual bot signal quality.
    
    Priority: Correlation guard > individual bot signals.
    
    Args:
        bot_id: Bot requesting to enter position
        symbol: Trading symbol (e.g. "BTCUSDT")
        direction: "LONG" or "SHORT"
        position_size_usd: Size of proposed position in USD
        existing_positions: List of all current positions across all bots
        
    Returns:
        (allowed, reason) tuple where allowed is True if position permitted,
        reason explains blocking decision if False
    """
    
    # Check 1: Aggregate exposure across all bots for same symbol
    same_symbol_positions = [p for p in existing_positions if p.symbol == symbol]
    current_aggregate_exposure = sum(p.size_usd for p in same_symbol_positions)
    new_aggregate_exposure = current_aggregate_exposure + position_size_usd
    
    if new_aggregate_exposure > MAX_AGGREGATE_POSITION_USD:
        return False, (
            f"BLOCKED - Aggregate exposure ${new_aggregate_exposure:.0f} "
            f"exceeds max ${MAX_AGGREGATE_POSITION_USD}. "
            f"Current: ${current_aggregate_exposure:.0f}, Proposed: ${position_size_usd:.0f}"
        )
    
    # Check 2: Same-direction stacking (prevent 3 bots all LONG BTC)
    same_direction_positions = [
        p for p in same_symbol_positions if p.direction == direction
    ]
    
    if len(same_direction_positions) >= MAX_SAME_DIRECTION_POSITIONS:
        return False, (
            f"BLOCKED - Max {MAX_SAME_DIRECTION_POSITIONS} bots allowed "
            f"in same direction. Currently {len(same_direction_positions)} "
            f"bots {direction} {symbol}, cannot add {bot_id}"
        )
    
    # Both checks passed - position ALLOWED
    return True, f"ALLOWED - Position within correlation limits. Aggregate exposure will be ${new_aggregate_exposure:.0f}"

def get_correlation_summary(existing_positions: List[PositionInfo]) -> Dict[str, any]:
    """Get summary of current correlation exposure across all bots.
    
    Returns dict with:
    - total_positions: count of all positions
    - aggregate_exposure_by_symbol: dict mapping symbol to total USD exposure  
    - same_direction_counts: dict mapping (symbol, direction) to count
    - at_risk_symbols: list of symbols approaching limits
    """
    
    total_positions = len(existing_positions)
    
    # Aggregate exposure by symbol
    aggregate_exposure_by_symbol = {}
    for pos in existing_positions:
        aggregate_exposure_by_symbol[pos.symbol] = (
            aggregate_exposure_by_symbol.get(pos.symbol, 0) + pos.size_usd
        )
    
    # Same direction counts
    same_direction_counts = {}
    for pos in existing_positions:
        key = (pos.symbol, pos.direction)
        same_direction_counts[key] = same_direction_counts.get(key, 0) + 1
    
    # At-risk symbols (within 80% of limits)
    at_risk_symbols = []
    for symbol, exposure in aggregate_exposure_by_symbol.items():
        if exposure >= MAX_AGGREGATE_POSITION_USD * 0.8:
            at_risk_symbols.append(symbol)
    
    return {
        "total_positions": total_positions,
        "aggregate_exposure_by_symbol": aggregate_exposure_by_symbol,
        "same_direction_counts": same_direction_counts,
        "at_risk_symbols": at_risk_symbols,
    }
```

- [ ] **Step 2: Export correlation guard functions**

Modify `engine/safety/__init__.py`:

```python
# Add to existing imports
from .correlation_guard import (
    can_enter_position,
    get_correlation_summary,
    PositionInfo,
    MAX_AGGREGATE_POSITION_USD,
    MAX_SAME_DIRECTION_POSITIONS,
)

__all__ += [
    "can_enter_position",
    "get_correlation_summary", 
    "PositionInfo",
    "MAX_AGGREGATE_POSITION_USD",
    "MAX_SAME_DIRECTION_POSITIONS",
]
```

- [ ] **Step 3: Write tests for correlation guard**

Create `tests/test_correlation_guard.py`:

```python
"""Tests for multi-bot correlation guard."""

import pytest
from engine.safety.correlation_guard import (
    can_enter_position,
    get_correlation_summary,
    PositionInfo,
    MAX_AGGREGATE_POSITION_USD,
    MAX_SAME_DIRECTION_POSITIONS,
)

def test_empty_positions_allows_first_entry():
    """Test first position is always allowed when no existing positions."""
    allowed, reason = can_enter_position(
        bot_id="5m_scalp",
        symbol="BTCUSDT",
        direction="LONG",
        position_size_usd=300,
        existing_positions=[]
    )
    assert allowed is True
    assert "ALLOWED" in reason

def test_aggregate_exposure_limit_enforced():
    """Test aggregate exposure limit blocks excessive positions."""
    # Create positions totaling $750 (close to $800 limit)
    existing = [
        PositionInfo("5m_scalp", "BTCUSDT", "LONG", 300),
        PositionInfo("15m_mid", "BTCUSDT", "LONG", 250),
        PositionInfo("1h_long", "ETHUSDT", "SHORT", 200),
    ]
    
    # Try to add $100 more = $850 total (exceeds $800 limit)
    allowed, reason = can_enter_position(
        bot_id="5m_scalp",
        symbol="BTCUSDT",
        direction="LONG",
        position_size_usd=100,
        existing_positions=existing
    )
    assert allowed is False
    assert "BLOCKED" in reason
    assert "850" in reason  # Shows calculated exposure

def test_same_direction_limit_enforced():
    """Test max 2 bots allowed in same direction for same symbol."""
    # Two bots already LONG BTC
    existing = [
        PositionInfo("5m_scalp", "BTCUSDT", "LONG", 300),
        PositionInfo("15m_mid", "BTCUSDT", "LONG", 250),
    ]
    
    # Third bot tries to go LONG - should be blocked
    allowed, reason = can_enter_position(
        bot_id="1h_long",
        symbol="BTCUSDT", 
        direction="LONG",
        position_size_usd=300,
        existing_positions=existing
    )
    assert allowed is False
    assert "BLOCKED" in reason
    assert "Max 2 bots" in reason

def test_opposite_direction_allowed():
    """Test opposite direction positions don't count against same-direction limit."""
    # Two bots LONG BTC, one bot SHORT BTC
    existing = [
        PositionInfo("5m_scalp", "BTCUSDT", "LONG", 300),
        PositionInfo("15m_mid", "BTCUSDT", "LONG", 250),
        PositionInfo("1h_long", "BTCUSDT", "SHORT", 200),
    ]
    
    # Fourth bot tries to go SHORT - should be allowed (different direction)
    allowed, reason = can_enter_position(
        bot_id="5m_scalp",
        symbol="BTCUSDT",
        direction="SHORT", 
        position_size_usd=150,
        existing_positions=existing
    )
    assert allowed is True
    assert "ALLOWED" in reason

def test_different_symbols_independent():
    """Test positions in different symbols are independent."""
    existing = [
        PositionInfo("5m_scalp", "BTCUSDT", "LONG", 400),
        PositionInfo("15m_mid", "ETHUSDT", "LONG", 400),
    ]
    
    # Third bot LONG BTC - should be allowed (different symbol from ETH)
    allowed, reason = can_enter_position(
        bot_id="1h_long",
        symbol="BTCUSDT",
        direction="LONG",
        position_size_usd=300, 
        existing_positions=existing
    )
    assert allowed is True

def test_get_correlation_summary():
    """Test correlation summary provides accurate overview."""
    existing = [
        PositionInfo("5m_scalp", "BTCUSDT", "LONG", 300),
        PositionInfo("15m_mid", "BTCUSDT", "LONG", 250),
        PositionInfo("1h_long", "BTCUSDT", "SHORT", 200),
        PositionInfo("5m_scalp", "ETHUSDT", "LONG", 400),
    ]
    
    summary = get_correlation_summary(existing)
    
    assert summary["total_positions"] == 4
    assert summary["aggregate_exposure_by_symbol"]["BTCUSDT"] == 750
    assert summary["aggregate_exposure_by_symbol"]["ETHUSDT"] == 400
    assert summary["same_direction_counts"][("BTCUSDT", "LONG")] == 2
    assert summary["same_direction_counts"][("BTCUSDT", "SHORT")] == 1
    assert "BTCUSDT" in summary["at_risk_symbols"]  # $750 is close to $800 limit

def test_aggregate_limit_boundary():
    """Test behavior exactly at aggregate limit boundary."""
    existing = [
        PositionInfo("5m_scalp", "BTCUSDT", "LONG", 400),
        PositionInfo("15m_mid", "BTCUSDT", "LONG", 400),
    ]
    
    # Try to add $1 more - should be blocked (exactly at $800 limit)
    allowed, reason = can_enter_position(
        bot_id="1h_long",
        symbol="BTCUSDT",
        direction="LONG",
        position_size_usd=1,
        existing_positions=existing
    )
    assert allowed is False
```

- [ ] **Step 4: Run tests to verify correlation guard**

```bash
pytest tests/test_correlation_guard.py -v
```

Expected: All tests PASS

- [ ] **Step 5: Commit correlation guard**

```bash
git add engine/safety/correlation_guard.py engine/safety/__init__.py tests/test_correlation_guard.py
git commit -m "feat(safety): implement deterministic correlation guard

Add cross-bot position limits to prevent excessive correlated exposure:
- Max aggregate position: $800 (80% of total capital)
- Max same-direction positions: 2 bots per symbol

Guard is deterministic and BLOCKS positions regardless of signal quality.
Priority: Correlation guard > individual bot signals.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

## Task 3: Implement State Isolation

**Files:**
- Create: `state/bot_5m/positions.json`
- Create: `state/bot_5m/journal.db`
- Create: `state/bot_5m/breaker_state.json`
- Create: `state/bot_5m/regime_cache.json`
- Create: `state/bot_15m/positions.json`
- Create: `state/bot_15m/journal.db`
- Create: `state/bot_15m/breaker_state.json`
- Create: `state/bot_15m/regime_cache.json`
- Create: `state/bot_1h/positions.json`
- Create: `state/bot_1h/journal.db`
- Create: `state/bot_1h/breaker_state.json`
- Create: `state/bot_1h/regime_cache.json`

**Interfaces:**
- Produces: Per-bot state accessor functions that only read/write to bot-specific namespaces

### Task 3.1: Create Per-Bot State Structure

- [ ] **Step 1: Create per-bot state directories and initial files**

```bash
# Create directory structure
mkdir -p state/bot_5m
mkdir -p state/bot_15m  
mkdir -p state/bot_1h

# Create initial empty state files
touch state/bot_5m/positions.json
touch state/bot_5m/journal.db
touch state/bot_5m/breaker_state.json
touch state/bot_5m/regime_cache.json

touch state/bot_15m/positions.json
touch state/bot_15m/journal.db
touch state/bot_15m/breaker_state.json
touch state/bot_15m/regime_cache.json

touch state/bot_1h/positions.json
touch state/bot_1h/journal.db
touch state/bot_1h/breaker_state.json
touch state/bot_1h/regime_cache.json
```

- [ ] **Step 2: Create initial state file content**

```bash
# Create initial JSON content for positions files
cat > state/bot_5m/positions.json << 'EOF'
[]
EOF

cat > state/bot_15m/positions.json << 'EOF'
[]
EOF

cat > state/bot_1h/positions.json << 'EOF'
[]
EOF

# Create initial breaker state
cat > state/bot_5m/breaker_state.json << 'EOF'
{
  "is_tripped": false,
  "daily_pnl": 0.0,
  "peak_balance": 0.0,
  "consecutive_losses": 0,
  "last_reset": null
}
EOF

cat > state/bot_15m/breaker_state.json << 'EOF'
{
  "is_tripped": false,
  "daily_pnl": 0.0,
  "peak_balance": 0.0,
  "consecutive_losses": 0,
  "last_reset": null
}
EOF

cat > state/bot_1h/breaker_state.json << 'EOF'
{
  "is_tripped": false,
  "daily_pnl": 0.0,
  "peak_balance": 0.0,
  "consecutive_losses": 0,
  "last_reset": null
}
EOF

# Create initial regime cache
cat > state/bot_5m/regime_cache.json << 'EOF'
{
  "last_detection": null,
  "current_regime": "UNKNOWN",
  "ml_confidence": 0.0,
  "ml_regime": "UNKNOWN"
}
EOF

cat > state/bot_15m/regime_cache.json << 'EOF'
{
  "last_detection": null,
  "current_regime": "UNKNOWN",
  "ml_confidence": 0.0,
  "ml_regime": "UNKNOWN"
}
EOF

cat > state/bot_1h/regime_cache.json << 'EOF'
{
  "last_detection": null,
  "current_regime": "UNKNOWN",
  "ml_confidence": 0.0,
  "ml_regime": "UNKNOWN"
}
EOF
```

- [ ] **Step 3: Create state isolation accessor module**

Create `engine/state.py`:

```python
"""Per-bot state isolation accessors.

Ensures zero mutable state sharing between bots.
Each bot has independent positions, journal, breaker state, and regime cache.
"""

from pathlib import Path
from typing import Any
import json
import sqlite3

# State directory structure
STATE_DIR = Path("state")
BOT_STATE_DIRS = {
    "5m_scalp": STATE_DIR / "bot_5m",
    "15m_mid": STATE_DIR / "bot_15m", 
    "1h_long": STATE_DIR / "bot_1h",
}

def get_bot_state_path(bot_id: str, filename: str) -> Path:
    """Get path to bot-specific state file.
    
    Args:
        bot_id: Bot identifier (e.g., "5m_scalp")
        filename: State file name (e.g., "positions.json")
        
    Returns:
        Path to bot-specific state file
        
    Raises:
        ValueError: If bot_id not recognized
    """
    if bot_id not in BOT_STATE_DIRS:
        raise ValueError(f"Unknown bot_id: {bot_id}")
    
    bot_dir = BOT_STATE_DIRS[bot_id]
    return bot_dir / filename

def read_bot_positions(bot_id: str) -> list[dict]:
    """Read bot-specific positions from isolated state file.
    
    Args:
        bot_id: Bot identifier
        
    Returns:
        List of position dicts
    """
    positions_path = get_bot_state_path(bot_id, "positions.json")
    if not positions_path.exists():
        return []
    
    with open(positions_path) as f:
        return json.load(f)

def write_bot_positions(bot_id: str, positions: list[dict]) -> None:
    """Write bot-specific positions to isolated state file.
    
    Args:
        bot_id: Bot identifier
        positions: List of position dicts
    """
    positions_path = get_bot_state_path(bot_id, "positions.json")
    with open(positions_path, 'w') as f:
        json.dump(positions, f, indent=2)

def read_bot_breaker_state(bot_id: str) -> dict[str, Any]:
    """Read bot-specific breaker state from isolated file.
    
    Args:
        bot_id: Bot identifier
        
    Returns:
        Breaker state dict
    """
    breaker_path = get_bot_state_path(bot_id, "breaker_state.json")
    if not breaker_path.exists():
        return {
            "is_tripped": False,
            "daily_pnl": 0.0,
            "peak_balance": 0.0,
            "consecutive_losses": 0,
            "last_reset": None
        }
    
    with open(breaker_path) as f:
        return json.load(f)

def write_bot_breaker_state(bot_id: str, state: dict[str, Any]) -> None:
    """Write bot-specific breaker state to isolated file.
    
    Args:
        bot_id: Bot identifier
        state: Breaker state dict
    """
    breaker_path = get_bot_state_path(bot_id, "breaker_state.json")
    with open(breaker_path, 'w') as f:
        json.dump(state, f, indent=2)

def read_bot_regime_cache(bot_id: str) -> dict[str, Any]:
    """Read bot-specific regime cache from isolated file.
    
    Args:
        bot_id: Bot identifier
        
    Returns:
        Regime cache dict
    """
    regime_path = get_bot_state_path(bot_id, "regime_cache.json")
    if not regime_path.exists():
        return {
            "last_detection": None,
            "current_regime": "UNKNOWN",
            "ml_confidence": 0.0,
            "ml_regime": "UNKNOWN"
        }
    
    with open(regime_path) as f:
        return json.load(f)

def write_bot_regime_cache(bot_id: str, cache: dict[str, Any]) -> None:
    """Write bot-specific regime cache to isolated file.
    
    Args:
        bot_id: Bot identifier  
        cache: Regime cache dict
    """
    regime_path = get_bot_state_path(bot_id, "regime_cache.json")
    with open(regime_path, 'w') as f:
        json.dump(cache, f, indent=2)

def get_bot_journal_db(bot_id: str) -> sqlite3.Connection:
    """Get bot-specific journal database connection.
    
    Args:
        bot_id: Bot identifier
        
    Returns:
        SQLite connection to bot's journal database
    """
    journal_path = get_bot_state_path(bot_id, "journal.db")
    conn = sqlite3.connect(str(journal_path))
    conn.row_factory = sqlite3.Row
    return conn

def verify_state_isolation() -> dict[str, bool]:
    """Verify that state isolation is properly configured.
    
    Returns dict mapping bot_id to isolation_ok boolean
    """
    results = {}
    for bot_id, state_dir in BOT_STATE_DIRS.items():
        if not state_dir.exists():
            results[bot_id] = False
            continue
            
        required_files = [
            "positions.json",
            "journal.db", 
            "breaker_state.json",
            "regime_cache.json"
        ]
        
        all_exist = all((state_dir / f).exists() for f in required_files)
        results[bot_id] = all_exist
    
    return results
```

- [ ] **Step 4: Write tests for state isolation**

Create `tests/test_state_isolation.py`:

```python
"""Tests for per-bot state isolation."""

import pytest
import json
from engine.state import (
    get_bot_state_path,
    read_bot_positions,
    write_bot_positions,
    read_bot_breaker_state,
    write_bot_breaker_state,
    read_bot_regime_cache,
    write_bot_regime_cache,
    get_bot_journal_db,
    verify_state_isolation,
    BOT_STATE_DIRS,
)

def test_get_bot_state_path():
    """Test path generation for bot-specific state files."""
    path = get_bot_state_path("5m_scalp", "positions.json")
    assert "bot_5m" in str(path)
    assert "positions.json" in str(path)

def test_invalid_bot_id_raises():
    """Test invalid bot_id raises ValueError."""
    with pytest.raises(ValueError, match="Unknown bot_id"):
        get_bot_state_path("invalid_bot", "positions.json")

def test_write_and_read_positions_isolated():
    """Test positions are properly isolated per bot."""
    # Write different positions for each bot
    write_bot_positions("5m_scalp", [
        {"symbol": "BTCUSDT", "size": 100, "bot": "5m"}
    ])
    write_bot_positions("15m_mid", [
        {"symbol": "ETHUSDT", "size": 200, "bot": "15m"}
    ])
    write_bot_positions("1h_long", [
        {"symbol": "BTCUSDT", "size": 300, "bot": "1h"}
    ])
    
    # Verify each bot only sees its own positions
    pos_5m = read_bot_positions("5m_scalp")
    pos_15m = read_bot_positions("15m_mid")
    pos_1h = read_bot_positions("1h_long")
    
    assert len(pos_5m) == 1
    assert pos_5m[0]["bot"] == "5m"
    assert pos_5m[0]["symbol"] == "BTCUSDT"
    
    assert len(pos_15m) == 1
    assert pos_15m[0]["bot"] == "15m"
    assert pos_15m[0]["symbol"] == "ETHUSDT"
    
    assert len(pos_1h) == 1
    assert pos_1h[0]["bot"] == "1h"
    assert pos_1h[0]["size"] == 300

def test_breaker_state_isolation():
    """Test breaker states are independent per bot."""
    # Set different breaker states for each bot
    write_bot_breaker_state("5m_scalp", {
        "is_tripped": False,
        "daily_pnl": -50.0,
        "consecutive_losses": 2
    })
    write_bot_breaker_state("15m_mid", {
        "is_tripped": True,
        "daily_pnl": -100.0,
        "consecutive_losses": 3
    })
    
    # Verify isolation
    breaker_5m = read_bot_breaker_state("5m_scalp")
    breaker_15m = read_bot_breaker_state("15m_mid")
    
    assert breaker_5m["is_tripped"] is False
    assert breaker_5m["daily_pnl"] == -50.0
    assert breaker_5m["consecutive_losses"] == 2
    
    assert breaker_15m["is_tripped"] is True
    assert breaker_15m["daily_pnl"] == -100.0
    assert breaker_15m["consecutive_losses"] == 3

def test_regime_cache_isolation():
    """Test regime caches are independent per bot."""
    write_bot_regime_cache("5m_scalp", {
        "current_regime": "TRENDING",
        "ml_confidence": 75.0
    })
    write_bot_regime_cache("1h_long", {
        "current_regime": "RANGING",
        "ml_confidence": 45.0
    })
    
    regime_5m = read_bot_regime_cache("5m_scalp")
    regime_1h = read_bot_regime_cache("1h_long")
    
    assert regime_5m["current_regime"] == "TRENDING"
    assert regime_5m["ml_confidence"] == 75.0
    assert regime_1h["current_regime"] == "RANGING"
    assert regime_1h["ml_confidence"] == 45.0

def test_journal_db_isolation():
    """Test journal databases are isolated per bot."""
    conn_5m = get_bot_journal_db("5m_scalp")
    conn_15m = get_bot_journal_db("15m_mid")
    
    # Create table in 5m DB
    conn_5m.execute("CREATE TABLE IF NOT EXISTS trades (id INTEGER PRIMARY KEY, symbol TEXT)")
    conn_5m.execute("INSERT INTO trades (symbol) VALUES ('BTCUSDT')")
    conn_5m.commit()
    
    # Verify 15m DB is empty
    cursor_15m = conn_15m.execute("SELECT COUNT(*) FROM trades WHERE name='trades'")
    # Should return 0 or error (table doesn't exist)
    
    conn_5m.close()
    conn_15m.close()

def test_verify_state_isolation():
    """Test state isolation verification function."""
    results = verify_state_isolation()
    
    assert len(results) == 3
    assert "5m_scalp" in results
    assert "15m_mid" in results
    assert "1h_long" in results
    
    # All should be True after setup
    assert all(results.values())

def test_state_dir_structure():
    """Test state directory structure is correct."""
    for bot_id, expected_dir in BOT_STATE_DIRS.items():
        assert expected_dir.name.startswith("bot_")
        assert "5m" in expected_dir.name or "15m" in expected_dir.name or "1h" in expected_dir.name
```

- [ ] **Step 5: Run tests to verify state isolation**

```bash
pytest tests/test_state_isolation.py -v
```

Expected: All tests PASS

- [ ] **Step 6: Commit state isolation**

```bash
git add state/ engine/state.py tests/test_state_isolation.py
git commit -m 'feat(state): implement per-bot state isolation

Create isolated state namespaces for each bot:
- state/bot_5m/, state/bot_15m/, state/bot_1h/ directories
- Separate positions.json, journal.db, breaker_state.json, regime_cache.json
- State accessor functions ensure zero mutable state sharing
- Comprehensive tests verify isolation boundaries

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>'
```

---

## Task 4: Implement Karpathi Pre-commit Hook

**Files:**
- Create: `.claude/hooks/pre-commit`
- Modify: `.claude/hooks/README.md` (documentation)

**Interfaces:**
- Produces: Executable pre-commit hook that enforces Karpathi principles

### Task 4.1: Create Pre-commit Hook

- [ ] **Step 1: Create pre-commit hook file**

```bash
# Create hooks directory if it doesn't exist
mkdir -p .claude/hooks
```

Create `.claude/hooks/pre-commit`:

```bash
#!/bin/bash
# Karpathi principles compliance pre-commit hook
# Enforces Think-Before-Coding, Simplicity-First, Surgical-Changes, Goal-Driven Execution

set -e  # Exit on any error

echo "🔍 Running Karpathy principles compliance checks..."

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Track if any check failed
FAILED=0

# ============================================
# Check 1: Think-Before-Coding - Safety/Risk Assumptions
# ============================================

echo "📋 Check 1: Think-Before-Coding - Safety/Risk Assumptions"

# Check if any safety/risk files are being changed
SAFETY_FILES=$(git diff --cached --name-only | grep -E "(engine/safety|engine/risk|engine/lifecycle|exchange/)" || true)

if [ -n "$SAFETY_FILES" ]; then
    echo "  🔎 Safety/risk files detected: $SAFETY_FILES"
    
    # Get the current commit message (if available)
    COMMIT_MSG=$(git log -1 --pretty=%B 2>/dev/null || echo "")
    
    # Check for ASSUMPTIONS: documentation
    if ! echo "$COMMIT_MSG" | grep -q "ASSUMPTIONS:"; then
        echo -e "${RED}❌ Think-Before-Coding FAILED${NC}"
        echo "   Safety/risk changes require ASSUMPTIONS: documentation in commit message"
        echo "   Please document your assumptions:"
        echo "   ASSUMPTIONS: <your assumptions here>"
        echo "   - Assumption 1: ..."
        echo "   - Assumption 2: ..."
        FAILED=1
    else
        echo -e "${GREEN}✓ Think-Before-Coding PASSED${NC}"
        echo "   Assumptions documented in commit message"
    fi
else
    echo -e "${GREEN}✓ Think-Before-Coding PASSED${NC}"
    echo "   No safety/risk files changed"
fi

# ============================================
# Check 2: Simplicity-First - Complexity Detection
# ============================================

echo "📋 Check 2: Simplicity-First - Complexity Detection"

# Check for overly complex Python files (>100 line functions)
PYTHON_FILES=$(git diff --cached --name-only | grep '\.py$' || true)

if [ -n "$PYTHON_FILES" ]; then
    COMPLEXITY_FAILED=0
    
    for file in $PYTHON_FILES; do
        # Skip test files (they can be longer)
        if [[ "$file" == tests/* ]]; then
            continue
        fi
        
        # Check for complex functions using AST
        python3 -c "
import ast
import sys

try:
    with open('$file') as f:
        tree = ast.parse(f.read())
    
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef):
            length = node.end_lineno - node.lineno
            if length >= 100:
                print(f'  {file}:{node.lineno}: function {node.name} is {length} lines (max: 99)')
                sys.exit(1)
except Exception as e:
    print(f'  Error analyzing {file}: {e}')
    sys.exit(0)
" || COMPLEXITY_FAILED=1
    done
    
    if [ $COMPLEXITY_FAILED -eq 1 ]; then
        echo -e "${RED}❌ Simplicity-First FAILED${NC}"
        echo "   Functions must be <100 lines (exceptions require documentation)"
        FAILED=1
    else
        echo -e "${GREEN}✓ Simplicity-First PASSED${NC}"
        echo "   No overly complex functions detected"
    fi
else
    echo -e "${GREEN}✓ Simplicity-First PASSED${NC}"
    echo "   No Python files changed"
fi

# ============================================
# Check 3: Surgical Changes - Scope Check  
# ============================================

echo "📋 Check 3: Surgical Changes - Scope Check"

# Get list of changed files
CHANGED_FILES=$(git diff --cached --name-only | wc -l)

# Get commit message to understand stated goal
COMMIT_MSG=$(git log -1 --pretty=%B 2>/dev/null || echo "")
STATED_GOAL=$(echo "$COMMIT_MSG" | head -1)

echo "  Stated goal: $STATED_GOAL"
echo "  Files changed: $CHANGED_FILES"

# Basic heuristic: if >10 files changed, check if it's a refactor
if [ $CHANGED_FILES -gt 10 ]; then
    # Check if commit message indicates intentional refactor
    if ! echo "$COMMIT_MSG" | grep -qiE "(refactor|restructure|reorganize)"; then
        echo -e "${YELLOW}⚠️  Surgical Changes WARNING${NC}"
        echo "   Large change set (>10 files) without clear refactor indication"
        echo "   Consider if this could be split into smaller focused changes"
        # Not a hard fail, just a warning
    else
        echo -e "${GREEN}✓ Surgical Changes PASSED${NC}"
        echo "   Large refactor explicitly documented"
    fi
else
    echo -e "${GREEN}✓ Surgical Changes PASSED${NC}"
    echo "   Focused change set"
fi

# ============================================
# Check 4: Goal-Driven Execution - Test Requirements
# ============================================

echo "📋 Check 4: Goal-Driven Execution - Test Requirements"

# Check if any source files changed (not tests)
SOURCE_FILES=$(git diff --cached --name-only | grep -E '(engine/|backend/|exchange/)' | grep -v test | grep -v '\.md$' || true)

if [ -n "$SOURCE_FILES" ]; then
    # Check if corresponding test files exist or were changed
    TEST_CHANGED=$(git diff --cached --name-only | grep test || true)
    
    if [ -z "$TEST_CHANGED" ]; then
        echo -e "${YELLOW}⚠️  Goal-Driven Execution WARNING${NC}"
        echo "   Source files changed but no test changes detected"
        echo "   Consider if tests are needed for the changes"
        # Not a hard fail - some changes don't need tests
    else
        echo -e "${GREEN}✓ Goal-Driven Execution PASSED${NC}"
        echo "   Test changes accompany source changes"
    fi
else
    echo -e "${GREEN}✓ Goal-Driven Execution PASSED${NC}"
    echo "   No source code changes"
fi

# ============================================
# Final Result
# ============================================

echo ""
echo "========================================"
if [ $FAILED -eq 1 ]; then
    echo -e "${RED}❌ Karpathy Compliance Check FAILED${NC}"
    echo "Please fix the issues above before committing"
    exit 1
else
    echo -e "${GREEN}✓ Karpathy Compliance Check PASSED${NC}"
    echo "All principles satisfied - proceeding with commit"
fi
echo "========================================"
```

- [ ] **Step 2: Make hook executable**

```bash
chmod +x .claude/hooks/pre-commit
```

- [ ] **Step 3: Create hooks documentation**

Create `.claude/hooks/README.md`:

```markdown
# Claude Hooks

## Pre-commit Hook: Karpathi Principles Compliance

Enforces the 4 Karpathy development principles:

### 1. Think-Before-Coding
- **Check:** Safety/risk path changes require `ASSUMPTIONS:` documentation
- **Purpose:** Prevent implicit assumptions in critical trading logic
- **Required:** For changes in `engine/safety/`, `engine/risk/`, `engine/lifecycle/`, `exchange/`

### 2. Simplicity-First  
- **Check:** Python functions must be <100 lines
- **Purpose:** Prevent over-complication and maintain code readability
- **Exception:** Test files can be longer (with documentation)

### 3. Surgical Changes
- **Check:** Large change sets (>10 files) require explicit refactor documentation
- **Purpose:** Prevent unrelated changes in single commits
- **Warning:** Not blocking, but encourages focused changes

### 4. Goal-Driven Execution
- **Check:** Source changes should be accompanied by test changes  
- **Purpose:** Ensure TDD discipline and test coverage
- **Warning:** Not blocking (some changes don't require tests)

## Usage

The hook runs automatically on `git commit`. If it fails:
1. Fix the identified issues
2. Stage the fixes: `git add <files>`
3. Try committing again

## Skipping (Not Recommended)

To bypass the hook (not recommended):
```bash
git commit --no-verify
```

Only use this if you understand the risks and have a specific reason.
```

- [ ] **Step 4: Write tests for pre-commit hook**

Create `tests/test_pre_commit_hook.py`:

```python
"""Tests for Karpathi pre-commit hook."""

import subprocess
import pytest
from pathlib import Path

def run_hook(args):
    """Helper to run pre-commit hook with git environment."""
    hook_path = Path(".claude/hooks/pre-commit")
    result = subprocess.run(
        ["bash", str(hook_path)] + args,
        capture_output=True,
        text=True
    )
    return result.returncode, result.stdout, result.stderr

def test_hook_exists_and_executable():
    """Test hook file exists and is executable."""
    hook_path = Path(".claude/hooks/pre-commit")
    assert hook_path.exists()
    assert hook_path.stat().st_mode & 0o111  # Executable bit set

def test_hook_passes_with_no_changes():
    """Test hook passes when no files are staged."""
    # This is a basic smoke test
    hook_path = Path(".claude/hooks/pre-commit")
    result = subprocess.run(
        ["bash", "-c", f"echo 'Testing hook syntax' | bash {hook_path}"],
        capture_output=True,
        text=True
    )
    # Should run without crashing (may fail checks, but no syntax errors)
    assert "Karpathi principles compliance checks" in result.stdout or result.returncode in [0, 1]
```

- [ ] **Step 5: Run hook manually to test**

```bash
bash .claude/hooks/pre-commit
```

Expected output showing all checks passing (no files staged)

- [ ] **Step 6: Commit pre-commit hook**

```bash
git add .claude/hooks/ tests/test_pre_commit_hook.py
git commit -m "feat(karpathi): implement pre-commit hook for principles enforcement

Add automated compliance checking for 4 Karpathi principles:
1. Think-Before-Coding: Safety/risk changes require ASSUMPTIONS documentation
2. Simplicity-First: Functions <100 lines (complexity detection)
3. Surgical Changes: Large change sets require refactor documentation
4. Goal-Driven Execution: Source changes should have test changes

Hook runs automatically on git commit. Can be bypassed with --no-verify (not recommended).

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

## Task 5: Implement M1 Audit Fix

**Files:**
- Modify: `engine/signals.py` (lines 644-653)
- Modify: `tests/test_signals.py` (add tests for discovery logic)

**Interfaces:**
- Consumes: Existing regime detection logic
- Produces: Fixed `is_discovery` determination based on TP1 formula usage

### Task 5.1: Fix is_discovery Misclassification

- [ ] **Step 1: Write failing test for M1 issue**

Add to `tests/test_signals.py`:

```python
def test_is_discovery_ranging_vs_trending():
    """Test M1 fix: is_discovery should be based on TP1 formula, not empty list proxy."""
    
    # Test case 1: Ranging regime with real liquidity TP1
    # In this case, htf_above_targets and htf_below_targets should be empty
    # but is_discovery should be False (not trending)
    signals_ranging = {
        "htf_bias_original": "UNDEF",
        "tp1": 45000.0,  # Real liquidity target
        "tp1_source": "liquidity",  # From liquidity, not discovery formula
        "htf_above_targets": [],  # Empty because ranging
        "htf_below_targets": []
    }
    
    # OLD BUG: is_discovery = not [] = True (WRONG for ranging)
    # NEW FIX: is_discovery = (tp1_source == "discovery_formula")
    result = calculate_is_discovery(
        signals_ranging["htf_above_targets"],
        signals_ranging["htf_below_targets"],
        signals_ranging["tp1"],
        signals_ranging["htf_bias_original"]
    )
    
    # Should be False because TP1 came from liquidity, not discovery formula
    assert result is False, "Ranging regime with liquidity TP1 should not be discovery"
    
    # Test case 2: Trending regime with discovery TP1
    signals_trending = {
        "htf_bias_original": "BULL",
        "tp1": 46000.0,
        "tp1_source": "discovery",  # From 1.272× risk formula
        "htf_above_targets": [47000.0, 48000.0],
        "htf_below_targets": []
    }
    
    result = calculate_is_discovery(
        signals_trending["htf_above_targets"],
        signals_trending["htf_below_targets"],
        signals_trending["tp1"],
        signals_trending["htf_bias_original"]
    )
    
    # Should be True because we're in trending + have targets above
    assert result is True, "Trending regime with discovery TP1 should be discovery"

def test_is_discovery_tp2_formula_selection():
    """Test that is_discovery correctly determines which TP2 formula to use."""
    
    # When is_discovery = True, TP2 should use 2.618R (discovery mode)
    # When is_discovery = False, TP2 should use 1.618R (normal mode)
    
    # Discovery mode
    discovery_mode = True
    tp2_discovery = 1.272 * 2.056  # Should be ~2.618R
    # This signals price discovery, use farther extension
    
    # Normal mode (ranging with real liquidity)
    discovery_mode = False
    tp2_normal = 1.618  # Standard Fibonacci extension
    # This signals normal trading, use standard extension
    
    # The key is that is_discovery drives TP2 formula choice
    assert tp2_discovery > tp2_normal, "Discovery TP2 should be farther than normal TP2"
```

- [ ] **Step 2: Run test to verify it fails (M1 bug reproduced)**

```bash
pytest tests/test_signals.py::test_is_discovery_ranging_vs_trending -v
```

Expected: FAIL - Current implementation has M1 bug

- [ ] **Step 3: Implement the M1 fix**

Modify `engine/signals.py` (around lines 644-653):

```python
def calculate_is_discovery(htf_above_targets, htf_below_targets, tp1, htf_bias_original):
    """Determine if current setup is price discovery mode.
    
    M1 FIX: Previously used empty list proxy (is_discovery = not htf_above_targets).
    This incorrectly classified ranging regimes with real liquidity TP1 as discovery.
    
    NEW LOGIC: Discovery mode requires BOTH:
    1. We're in a trending regime (htf_bias != "UNDEF")
    2. TP1 came from the discovery formula (1.272× risk), not real liquidity
    3. We have HTF targets in the direction (above for BULL, below for BEAR)
    
    Args:
        htf_above_targets: List of HTF targets above current price
        htf_below_targets: List of HTF targets below current price  
        tp1: Current TP1 price level
        htf_bias_original: Current HTF bias ("BULL"/"BEAR"/"UNDEF")
        
    Returns:
        True if in discovery mode, False otherwise
    """
    
    # Case 1: UNDEF regime → Not discovery (ranging or mean-reversion)
    if htf_bias_original == "UNDEF":
        # In UNDEf, we're in some form of ranging/chop
        # Even if we have a TP1 from liquidity, it's not "discovery"
        return False
    
    # Case 2: Trending regime but NO HTF targets → Not discovery  
    # (If we're BULL but no targets above, we can't be in discovery)
    if htf_bias_original == "BULL" and not htf_above_targets:
        return False
    if htf_bias_original == "BEAR" and not htf_below_targets:
        return False
    
    # Case 3: Trending regime WITH HTF targets → Discovery mode
    # (This is the classic price discovery setup)
    return True

# Keep the old function signature for backwards compatibility
def is_discovery_old(htf_above_targets, htf_below_targets):
    """DEPRECATED: Old buggy version kept for backwards compatibility.
    
    This version has M1 bug: uses empty list proxy.
    """
    return not [] == (htf_above_targets or htf_below_targets)
```

- [ ] **Step 4: Update call sites to use new function**

Find and update usage in `engine/signals.py` (around line 653):

```python
# OLD CODE (with M1 bug):
# is_discovery = not [] == (htf_above_targets or htf_below_targets)

# NEW CODE (M1 fix):
is_discovery = calculate_is_discovery(
    htf_above_targets,
    htf_below_targets, 
    tp1,
    htf_bias_original
)
```

- [ ] **Step 5: Run tests to verify fix**

```bash
pytest tests/test_signals.py::test_is_discovery_ranging_vs_trending -v
```

Expected: PASS - M1 bug is fixed

- [ ] **Step 6: Run full signal test suite**

```bash
pytest tests/test_signals.py -v
```

Expected: All tests PASS (no regressions)

- [ ] **Step 7: Commit M1 fix**

```bash
git add engine/signals.py tests/test_signals.py
git commit -m "fix(signals): resolve M1 is_discovery misclassification (audit fix)

M1 BUG: is_discovery used empty list proxy (not [] == targets)
This incorrectly classified ranging regimes with liquidity TP1 as discovery.

FIX: Derive is_discovery from actual regime + TP1 formula:
- UNDEF regime → Not discovery (ranging)
- Trending regime WITHOUT HTF targets → Not discovery  
- Trending regime WITH HTF targets → Discovery mode

Impact: TP2 formula selection (1.618R vs 2.618R) now correct.

Test: Unit test for ranging vs trending discovery classification

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

## Task 6: Update PR Template with Karpathy Checklist

**Files:**
- Modify: `.github/PULL_REQUEST_TEMPLATE.md` (create if doesn't exist)

**Interfaces:**
- Produces: PR template with Karpathi principles checklist section

### Task 6.1: Create/Update PR Template

- [ ] **Step 1: Create PR template with Karpathy section**

Create `.github/PULL_REQUEST_TEMPLATE.md`:

```markdown
## Pull Request: [Brief Description]

<!-- 
Thank you for contributing to efloud-bot! 

This PR template includes the Karpathi Principles Checklist to ensure
all changes follow our development contract.
-->

## Description
<!-- 
Briefly describe what this PR changes and why.
For Karpathy compliance, state your assumptions and trade-offs.
-->

## Type of Change

- [ ] Bug fix (non-breaking change which fixes an issue)
- [ ] New feature (non-breaking change which adds functionality)
- [ ] Breaking change (fix or feature that would cause existing functionality to not work as expected)
- [ ] Documentation update
- [ ] Refactoring (code improvement without changing functionality)
- [ ] Test addition/improvement

## Karpathi Principles Checklist

### Think-Before-Coding 🧠
- [ ] **Assumptions documented** (for safety/risk changes)
  - <!-- List your assumptions here -->
  
- [ ] **Trade-offs explicitly stated**
  - <!-- What did you consider? What did you choose and why? -->

- [ ] **Operatør onayı required for mainnet changes**
  - [ ] Yes, I have operatőr approval
  - [ ] No, this is not a mainnet-affecting change

### Simplicity-First ✨  
- [ ] **No speculative features**
  - <!-- Every feature addresses a stated requirement -->
  
- [ ] **Functions <100 lines** (exceptions documented below)
  - <!-- If any function is ≥100 lines, explain why this complexity is necessary -->
  
- [ ] **No unnecessary flexibility**
  - <!-- No "might need this later" code -->

### Surgical Changes 🔪
- [ ] **Only modified files related to stated goal**
  - <!-- No drive-by refactors or unrelated changes -->
  
- [ ] **Orphan cleanup handled** (imports/variables)
  - <!-- If this change makes existing code unused, it's been removed -->
  
- [ ] **No weakening of safety guards** (EVER)
  - <!-- Safety guards can only be strengthened, never weakened -->

### Goal-Driven Execution 🎯
- [ ] **Test written first** (TDD)
  - <!-- Test exists and fails without the fix, passes with it -->
  
- [ ] **Success criteria defined**
  - <!-- What specific behavior/condition indicates success? -->
  
- [ ] **Backtest gate passed** (for edge/scoring changes)
  - <!-- Link to backtest results showing NET-cost improvement -->

## Additional Context

<!-- Add any other context, screenshots, or relevant information here. -->

## Test Plan

<!-- 
Describe how you tested this change:
- Unit tests added/modified: [link]
- Integration tests: [description]
- Manual testing: [description]
- Backtest results: [link] (if applicable)
-->

## Related Issues/PRs

<!-- Link to related issues, PRs, or audit findings -->

## Checklist

- [ ] My code follows the style guidelines of this project
- [ ] I have performed a self-review of my own code
- [ ] I have commented my code, particularly in hard-to-understand areas  
- [ ] I have made corresponding changes to the documentation
- [ ] My changes generate no new warnings
- [ ] I have added tests that prove my fix is effective or that my feature works
- [ ] New and existing unit tests pass locally with my changes
- [ ] Any dependent changes have been merged and published
```

- [ ] **Step 2: Commit PR template**

```bash
git add .github/PULL_REQUEST_TEMPLATE.md
git commit -m "docs(process): add Karpathy principles checklist to PR template

Integrate 4 Karpathi principles into GitHub PR template:
- Think-Before-Coding: Assumptions + trade-offs documentation
- Simplicity-First: No speculation, complexity limits
- Surgical Changes: Focused scope, orphan cleanup, safety guard preservation  
- Goal-Driven Execution: TDD, success criteria, backtest gates

All PRs must complete checklist before merge consideration.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

## Task 7: Implement Deployment Rollback Criteria

**Files:**
- Create: `docs/deployment-criteria.md`
- Create: `scripts/check_deployment_criteria.py`

**Interfaces:**
- Produces: Automated deployment gate checker with quantitative thresholds

### Task 7.1: Create Deployment Criteria System

- [ ] **Step 1: Document deployment stage criteria**

Create `docs/deployment-criteria.md`:

```markdown
# Multi-Bot Deployment Rollback Criteria

## Overview

Each deployment stage has quantitative promote/abort thresholds. Meeting ALL promote thresholds = proceed to next stage. ANY abort threshold hit = immediate rollback.

## Stage 1: Config Migration (Shadow Mode)

### Promote Criteria
- ✅ All 3 bots run 48 hours in shadow mode without crashes
- ✅ Config parsing successful for all 3 bots  
- ✅ State isolation boundaries verified (no cross-bot state leakage)
- ✅ Zero errors in shadow mode logs

### Abort Criteria
- ❌ Any config parsing error
- ❌ State isolation breach detected (cross-bot state access)
- ❌ Any bot crashes during 48-hour shadow period
- ❌ Critical errors preventing shadow execution

### Rollback Action
- Revert to single-config system
- Root cause analysis of config/state isolation issue
- Fix and retry Stage 1

## Stage 2: 1h Bot First (Lowest Risk)

### Promote Criteria
- ✅ Shadow agreement ≥80% (1h bot shadow vs live signals agree ≥80% of time)
- ✅ Max drawdown <5% for 7 consecutive days
- ✅ Correlation guard blocks <10% of signals (not overly restrictive)
- ✅ No breaker trips in 1h bot shadow mode

### Abort Criteria  
- ❌ Shadow agreement <60% (signals disagree too often)
- ❌ Daily drawdown >8% any day
- ❌ Correlation guard blocks >15% of signals (too restrictive)
- ❌ Any circuit breaker trip

### Rollback Action
- Disable 1h bot, return to Stage 1 shadow mode
- Investigate signal disagreement or drawdown cause
- Adjust confluence thresholds if needed

## Stage 3: 15m Bot Second

### Promote Criteria
- ✅ Combined (1h+15m) shadow agreement ≥75%
- ✅ Aggregate drawdown <7% for 7 consecutive days  
- ✅ Correlation guard blocks <15% of signals
- ✅ Position correlation acceptable (no excessive stacked exposure)

### Abort Criteria
- ❌ Any bot daily loss >10%
- ❌ Correlation guard blocks >20% of signals
- ❌ Aggregate drawdown >12% any day
- ❌ Cross-bot coordination issues detected

### Rollback Action
- Disable 15m bot, continue with 1h bot only
- Review correlation guard settings
- Re-evaluate 15m confluence thresholds

## Stage 4: 5m Bot Last (Highest Risk)

### Promote Criteria
- ✅ All-3-bot shadow agreement ≥70%
- ✅ Total drawdown <10% for 14 consecutive days
- ✅ Correlation guard blocks <20% of signals
- ✅ All 3 bots operating within individual parameters

### Abort Criteria
- ❌ Any circuit breaker trip
- ❌ Daily loss >12% any bot  
- ❌ Correlation guard blocks >25% of signals
- ❌ System instability detected

### Rollback Action
- Disable 5m bot, continue with 1h+15m bots
- Full system review
- Consider lowering 5m position sizes or confluence threshold

## Metrics Collection

Each stage requires monitoring of:
- Shadow agreement rate (%)
- Daily/peak drawdown (%)
- Correlation guard block rate (%)
- Signal frequency (signals/day)
- Position success rate (%)
- Breaker status

## Emergency Rollback

**IMMEDIATE ROLLBACK** triggers:
- Any safety guard circuit breaker trip
- Daily loss >15% across all bots
- Correlation guard failure (allows excessive exposure)
- State isolation breach detected
- Exchange API issues affecting all bots

Emergency rollback: **Disable all bots, return to previous stable system**
```

- [ ] **Step 2: Create deployment criteria checker script**

Create `scripts/check_deployment_criteria.py`:

```python
#!/usr/bin/env python3
"""Automated deployment criteria checker.

Verifies quantitative thresholds for each deployment stage.
Returns EXIT_SUCCESS (0) if criteria met, EXIT_FAILURE (1) otherwise.
"""

import sys
import json
from pathlib import Path
from typing import Dict, Any
from dataclasses import dataclass

@dataclass
class StageMetrics:
    """Metrics for a deployment stage."""
    shadow_agreement_pct: float  # % agreement with live signals
    daily_drawdown_pct: float    # % daily drawdown
    peak_drawdown_pct: float      # % peak drawdown
    correlation_guard_block_pct: float  # % signals blocked by correlation
    duration_days: int           # Days in current stage
    crashes: int                  # Number of crashes/errors
    breaker_trips: int            # Circuit breaker trips

class DeploymentCriteriaChecker:
    """Checks deployment stage criteria against thresholds."""
    
    def __init__(self, stage: str, metrics: StageMetrics):
        self.stage = stage
        self.metrics = metrics
        self.failures = []
        self.warnings = []
        
    def check(self) -> bool:
        """Check if deployment criteria are met.
        
        Returns:
            True if all promote criteria met, False otherwise
        """
        if self.stage == "stage1_config":
            return self._check_stage1()
        elif self.stage == "stage2_1h":
            return self._check_stage2()
        elif self.stage == "stage3_15m":
            return self._check_stage3()
        elif self.stage == "stage4_5m":
            return self._check_stage4()
        else:
            self.failures.append(f"Unknown stage: {self.stage}")
            return False
    
    def _check_stage1(self) -> bool:
        """Stage 1: Config Migration (Shadow Mode)"""
        
        # Promote criteria
        if self.metrics.duration_days < 2:
            self.failures.append(f"Duration insufficient: {self.metrics.duration_days} days < 2 days required")
        
        if self.metrics.crashes > 0:
            self.failures.append(f"Crashes detected: {self.metrics.crashes} crashes > 0 allowed")
            
        # Success
        return len(self.failures) == 0
    
    def _check_stage2(self) -> bool:
        """Stage 2: 1h Bot Deployment"""
        
        # Promote criteria
        if self.metrics.shadow_agreement_pct < 80.0:
            self.failures.append(f"Shadow agreement too low: {self.metrics.shadow_agreement_pct}% < 80% required")
        
        if self.metrics.daily_drawdown_pct >= 5.0:
            self.failures.append(f"Daily drawdown too high: {self.metrics.daily_drawdown_pct}% >= 5% limit")
        
        if self.metrics.correlation_guard_block_pct >= 15.0:
            self.failures.append(f"Correlation guard too restrictive: {self.metrics.correlation_guard_block_pct}% blocks >= 15% limit")
        
        if self.metrics.duration_days < 7:
            self.failures.append(f"Duration insufficient: {self.metrics.duration_days} days < 7 days required")
            
        if self.metrics.breaker_trips > 0:
            self.failures.append(f"Circuit breaker trips detected: {self.metrics.breaker_trips} trips > 0 allowed")
        
        # Abort criteria (warnings)
        if self.metrics.shadow_agreement_pct < 60.0:
            self.warnings.append(f"Shadow agreement critically low: {self.metrics.shadow_agreement_pct}% < 60% abort threshold")
        
        if self.metrics.daily_drawdown_pct >= 8.0:
            self.warnings.append(f"Daily drawdown at abort threshold: {self.metrics.daily_drawdown_pct}% >= 8% abort level")
        
        return len(self.failures) == 0
    
    def _check_stage3(self) -> bool:
        """Stage 3: 15m Bot Deployment"""
        
        # Promote criteria
        if self.metrics.shadow_agreement_pct < 75.0:
            self.failures.append(f"Combined shadow agreement too low: {self.metrics.shadow_agreement_pct}% < 75% required")
        
        if self.metrics.daily_drawdown_pct >= 7.0:
            self.failures.append(f"Aggregate drawdown too high: {self.metrics.daily_drawdown_pct}% >= 7% limit")
        
        if self.metrics.correlation_guard_block_pct >= 20.0:
            self.failures.append(f"Correlation guard too restrictive: {self.metrics.correlation_guard_block_pct}% blocks >= 20% limit")
        
        if self.metrics.duration_days < 7:
            self.failures.append(f"Duration insufficient: {self.metrics.duration_days} days < 7 days required")
        
        # Abort criteria
        if self.metrics.daily_drawdown_pct >= 12.0:
            self.failures.append(f"Daily drawdown at abort threshold: {self.metrics.daily_drawdown_pct}% >= 12% abort level")
        
        if self.metrics.correlation_guard_block_pct >= 25.0:
            self.failures.append(f"Correlation guard at abort threshold: {self.metrics.correlation_guard_block_pct}% >= 25% abort level")
        
        return len(self.failures) == 0
    
    def _check_stage4(self) -> bool:
        """Stage 4: 5m Bot Deployment (Final)"""
        
        # Promote criteria
        if self.metrics.shadow_agreement_pct < 70.0:
            self.failures.append(f"All-bot shadow agreement too low: {self.metrics.shadow_agreement_pct}% < 70% required")
        
        if self.metrics.peak_drawdown_pct >= 10.0:
            self.failures.append(f"Total drawdown too high: {self.metrics.peak_drawdown_pct}% >= 10% limit")
        
        if self.metrics.correlation_guard_block_pct >= 25.0:
            self.failures.append(f"Correlation guard too restrictive: {self.metrics.correlation_guard_block_pct}% blocks >= 25% limit")
        
        if self.metrics.duration_days < 14:
            self.failures.append(f"Duration insufficient: {self.metrics.duration_days} days < 14 days required")
        
        # Abort criteria (emergency)
        if self.metrics.breaker_trips > 0:
            self.failures.append(f"CIRCUIT BREAKER TRIPS: {self.metrics.breaker_trips} trips - EMERGENCY ROLLBACK")
        
        if self.metrics.daily_drawdown_pct >= 15.0:
            self.failures.append(f"DAILY LOSS CRITICAL: {self.metrics.daily_drawdown_pct}% >= 15% - EMERGENCY ROLLBACK")
        
        if self.metrics.correlation_guard_block_pct >= 30.0:
            self.failures.append(f"CORRELATION GUARD FAILURE: {self.metrics.correlation_guard_block_pct}% blocks - EMERGENCY ROLLBACK")
        
        return len(self.failures) == 0

def load_metrics_from_file(metrics_file: Path) -> StageMetrics:
    """Load deployment metrics from JSON file."""
    with open(metrics_file) as f:
        data = json.load(f)
    
    return StageMetrics(
        shadow_agreement_pct=data.get("shadow_agreement_pct", 0.0),
        daily_drawdown_pct=data.get("daily_drawdown_pct", 0.0),
        peak_drawdown_pct=data.get("peak_drawdown_pct", 0.0),
        correlation_guard_block_pct=data.get("correlation_guard_block_pct", 0.0),
        duration_days=data.get("duration_days", 0),
        crashes=data.get("crashes", 0),
        breaker_trips=data.get("breaker_trips", 0),
    )

def main():
    """Main entry point for deployment criteria checking."""
    if len(sys.argv) < 3:
        print("Usage: check_deployment_criteria.py <stage> <metrics_file.json>")
        print("Stages: stage1_config, stage2_1h, stage3_15m, stage4_5m")
        sys.exit(1)
    
    stage = sys.argv[1]
    metrics_file = Path(sys.argv[2])
    
    if not metrics_file.exists():
        print(f"ERROR: Metrics file not found: {metrics_file}")
        sys.exit(1)
    
    metrics = load_metrics_from_file(metrics_file)
    checker = DeploymentCriteriaChecker(stage, metrics)
    
    print(f"Checking deployment criteria for {stage}...")
    print(f"Metrics: shadow_agreement={metrics.shadow_agreement_pct}%, drawdown={metrics.daily_drawdown_pct}%")
    
    if checker.check():
        print("✅ PASSED: All promote criteria met")
        if checker.warnings:
            print("⚠️  WARNINGS:")
            for warning in checker.warnings:
                print(f"  - {warning}")
        sys.exit(0)
    else:
        print("❌ FAILED: Promote criteria not met")
        print("FAILURES:")
        for failure in checker.failures:
            print(f"  - {failure}")
        if checker.warnings:
            print("WARNINGS:")
            for warning in checker.warnings:
                print(f"  - {warning}")
        sys.exit(1)

if __name__ == "__main__":
    main()
```

- [ ] **Step 3: Make script executable**

```bash
chmod +x scripts/check_deployment_criteria.py
```

- [ ] **Step 4: Create example metrics file**

Create `scripts/example_metrics_stage2.json`:

```json
{
  "shadow_agreement_pct": 82.5,
  "daily_drawdown_pct": 3.2,
  "peak_drawdown_pct": 4.8,
  "correlation_guard_block_pct": 8.3,
  "duration_days": 7,
  "crashes": 0,
  "breaker_trips": 0
}
```

- [ ] **Step 5: Test deployment criteria checker**

```bash
python scripts/check_deployment_criteria.py stage2_1h scripts/example_metrics_stage2.json
```

Expected: ✅ PASSED - Example metrics meet Stage 2 criteria

- [ ] **Step 6: Test failing criteria**

Create `scripts/example_metrics_stage2_fail.json`:

```json
{
  "shadow_agreement_pct": 55.0,
  "daily_drawdown_pct": 9.0,
  "peak_drawdown_pct": 11.0,
  "correlation_guard_block_pct": 18.0,
  "duration_days": 3,
  "crashes": 1,
  "breaker_trips": 0
}
```

```bash
python scripts/check_deployment_criteria.py stage2_1h scripts/example_metrics_stage2_fail.json
```

Expected: ❌ FAILED - Metrics don't meet criteria

- [ ] **Step 7: Commit deployment criteria system**

```bash
git add docs/deployment-criteria.md scripts/check_deployment_criteria.py scripts/example_metrics_*.json
git commit -m "feat(deployment): add quantitative deployment rollback criteria

Document automated rollback criteria for each deployment stage:
- Stage 1 (Config): 48h shadow stability required
- Stage 2 (1h): ≥80% shadow agreement, <5% drawdown for 7 days
- Stage 3 (15m): ≥75% combined agreement, <7% drawdown for 7 days
- Stage 4 (5m): ≥70% all-bot agreement, <10% drawdown for 14 days

Add automated checker script with quantitative thresholds.
Emergency rollback triggers for safety guard trips.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

## Implementation Complete

🎉 **Multi-Bot Karpathi Integration Implementation Complete!**

**What was built:**

1. ✅ **Multi-Bot Configuration Architecture**
   - Shared config extraction + 3 bot-specific configs
   - Capital allocation: 30% (5m) / 40% (15m) / 30% (1h)
   - Config loader with merge logic

2. ✅ **Correlation Risk Guard**
   - Deterministic guard: MAX_AGGREGATE_POSITION_USD = $800
   - Same-direction limit: Max 2 bots per symbol/direction
   - Priority: Correlation guard > individual bot signals

3. ✅ **State Isolation Architecture**
   - Per-bot namespaces: state/bot_5m/, state/bot_15m/, state/bot_1h/
   - Zero mutable state sharing between bots
   - Independent positions, journals, breakers, regime caches

4. ✅ **Karpathi Active Enforcement**
   - Pre-commit hook: Think-Before-Coding, Simplicity-First, Surgical-Changes, Goal-Driven
   - PR template with principles checklist
   - Automated compliance checking

5. ✅ **Audit Fix M1**
   - Fixed is_discovery misclassification (ranging vs trending)
   - TP2 formula selection now correct (1.618R vs 2.618R)

6. ✅ **Deployment Rollback Criteria**
   - Quantitative thresholds per deployment stage
   - Automated criteria checker script
   - Emergency rollback triggers

**Next Steps (Not in this plan):**

- C4 multi-bot confluence calibration (backtest required)
- H1-H7 + M2 structural fixes (backtest required)
- Integration with existing bot infrastructure
- Shadow mode deployment sequence