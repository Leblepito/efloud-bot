import sys
import time
from pathlib import Path
import logging

# Configure logging to console
logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    stream=sys.stdout
)

# Add project root to path
ROOT = Path(__file__).resolve().parents[2]
sys.path.append(str(ROOT))

from backtest.engine import run_backtest
from scripts.autoresearch.prepare import prepare_optimization_data

# ==============================================================================
# HACKABLE STRATEGY CONFIGURATION
# Feel free to change any of these hyperparameters or structural rules!
# This block is directly optimized by the autonomous AI strategy researcher.
# ==============================================================================
CONFIG = {
    "engine": {
        "smc_version": "v2",
        "smc_v2_symbols": ["*"],
        "smc_v2_shadow": False
    },
    "exchange": {
        "name": "binance",
        "market_type": "futures",
        "testnet": True,
        "leverage": 3,
        "margin_mode": "ISOLATED"
    },
    "smc_v2": {
        "pullback_timeout_bars": 8,
        "fvg_priority": True,
        "ote_band": [0.618, 0.786],
        "require_confirmation": True,
        "max_pending_per_symbol": 3
    },
    "timeframes": {
        "htf": "4h",
        "mtf": "1h",
        "entry": "15m"
    },
    "structure": {
        "swing_lookback": 4,
        "ob_sequential": 5,
        "body_mode": True,
        "eq_threshold_pct": 0.1,
        "range_lookback": 50
    },
    "fibonacci": {
        "ote_lower": 0.618,
        "ote_upper": 0.786,
        "ext_tp2": 1.618
    },
    "risk": {
        "risk_per_trade_pct": 2.0,
        "max_open_positions": 10,
        "min_rr": 1.5,
        "min_confluence": 50,
        "recency_bars": 40,
        "sl_atr_buffer": 0.5,
        "daily_filter_strict": False,
        "position_size_calculation": "legacy",
        "max_loss_per_trade_usdt": 20,
        "target_stop_distance_pct": 5
    },
    "operation": {
        "watch_only": False
    },
    "safety": {
        "daily_loss_limit_pct": 10.0,
        "weekly_drawdown_limit_pct": 15.0,
        "consecutive_loss_limit": 3,
        "consecutive_pause_min": 120,
        "starting_balance": 2000,
        "adx_trend_threshold": 10,
        "adx_range_threshold": 0,
        "allow_volatile_entries": True,
        "volatile_atr_mult": 2.5,
        "max_position_notional_pct": 4.0,
        "max_total_exposure": 1.0,
        "max_holding_hours": 24,
        "max_pyramid_adds": 0,
        "min_sl_atr": 0.5,
        "max_sl_atr": 5.0,
        "emergency_balance_threshold": 1800,
        "reserve_balance": 0,
        "min_seconds_between_symbol_fetches": 0.5
    }
}

def execute_experiment():
    # 1. Prepare optimization dataset
    symbols = ["SOL/USDT"]
    data = prepare_optimization_data(symbols=symbols, period_days=30)
    
    start_time = time.time()
    
    # 2. Execute walk-forward SMC v2 backtest
    print("[autoresearch] Launching portfolio backtest simulation...")
    results = run_backtest(
        symbols=symbols,
        data=data,
        config=CONFIG,
        initial_balance=2000.0,
        smc_version="v2"
    )
    
    end_time = time.time()
    total_seconds = end_time - start_time
    
    # 3. Print standardized performance output for agent regex extraction
    print("\n---")
    print(f"net_profit_pct:    {results.get('total_return_pct', 0.0):.6f}")
    print(f"sharpe_ratio:      {results.get('sharpe_like', 0.0):.6f}")
    print(f"max_drawdown_pct:  {results.get('max_drawdown_pct', 0.0):.6f}")
    print(f"total_trades:      {results.get('total_trades', 0)}")
    print(f"profit_factor:     {results.get('profit_factor', 0.0):.6f}")
    print(f"total_seconds:     {total_seconds:.2f}")

if __name__ == "__main__":
    execute_experiment()
