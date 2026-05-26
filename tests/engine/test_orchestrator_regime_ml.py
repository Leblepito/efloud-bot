import pandas as pd
import numpy as np
import pytest
from pathlib import Path
import os
from engine.safe_orchestrator import SafeOrchestrator

def test_orchestrator_triggers_regime_ml_training(tmp_path):
    """Verify that SafeOrchestrator triggers model training when run_cycle is executed on BTC/USDT with enough data."""
    # Build complete and valid dummy config dict
    dummy_config = {
        "timeframes": {"htf": "4h", "mtf": "1h", "entry": "15m"},
        "structure": {"swing_lookback": 4, "ob_sequential": 2, "body_mode": "close", "eq_threshold_pct": 5.0, "range_lookback": 50},
        "fibonacci": {"ote_lower": 0.62, "ote_upper": 0.79, "ext_tp2": 1.0},
        "safety": {
            "adx_trend_threshold": 25,
            "adx_range_threshold": 20,
            "volatile_atr_mult": 2.5,
            "daily_loss_limit_pct": 3.0,
            "weekly_drawdown_limit_pct": 8.0,
            "consecutive_loss_limit": 3,
            "starting_balance": 1000,
            "max_position_notional_pct": 10.0,
            "max_total_exposure": 3.0,
            "max_holding_hours": 48,
            "max_pyramid_adds": 2,
            "min_sl_atr": 0.5,
            "max_sl_atr": 5.0,
            "allow_volatile_entries": False,
        },
        "risk": {"min_confluence": 70, "min_rr": 1.8, "max_open_positions": 3, "recency_bars": 40},
        "operation": {"watch_only": True},
        "exchange": {"leverage": 1}
    }
    
    # Create sufficient mock DataFrame (at least 100 samples)
    np.random.seed(42)
    closes = np.linspace(2000, 2050, 110) + np.random.normal(0, 3, 110)
    highs = closes + np.random.uniform(1, 5, 110)
    lows = closes - np.random.uniform(1, 5, 110)
    opens = closes - np.random.normal(0, 1, 110)
    volumes = np.random.lognormal(10, 0.5, 110)
    
    df = pd.DataFrame({
        "open": opens, "high": highs, "low": lows,
        "close": closes, "volume": volumes
    })
    
    state_dir = tmp_path / "state"
    state_dir.mkdir()
    
    # Init orchestrator with freshness_check=False for mock data compatibility
    orch = SafeOrchestrator(config=dummy_config, state_dir=str(state_dir), freshness_check=False, persist=False)
    
    # Modify weights path to temp directory
    orch.regime.weights_path = state_dir / "regime_model_weights.json"
    orch.regime._load_ml_model()
    
    assert orch.last_regime_training_time is None
    
    # Run cycle on BTC/USDT
    res = orch.run_cycle(
        symbol="BTC/USDT",
        df_htf=df,
        df_mtf=df,
        df_entry=df,
        balance=1000.0
    )
    
    # Verify training completed and last_regime_training_time updated
    assert orch.last_regime_training_time is not None
    assert os.path.exists(str(orch.regime.weights_path))
    assert orch.regime.model is not None
