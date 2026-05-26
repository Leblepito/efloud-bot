import pytest
import json
from pathlib import Path
from unittest.mock import patch, MagicMock

# SafeOrchestrator'ı import ediyoruz
from engine.safe_orchestrator import SafeOrchestrator

def test_orchestrator_load_ai_sentiment(tmp_path):
    registry_data = {
        "macro_sentiment": "RISK_ON",
        "confidence_score": 0.85,
        "fear_and_greed": 65.0,
        "bitcoin_trend": "BULLISH",
        "reasoning": "Test reasoning"
    }
    registry_file = tmp_path / "ai_sentiment_registry.json"
    registry_file.write_text(json.dumps(registry_data), encoding="utf-8")
    
    dummy_config = {
        "timeframes": {"htf": "4h", "mtf": "1h", "entry": "15m"},
        "structure": {"swing_lookback": 20, "ob_sequential": 2, "body_mode": "close", "eq_threshold_pct": 5.0, "range_lookback": 50},
        "fibonacci": {"ote_lower": 0.62, "ote_upper": 0.79, "ext_tp2": 1.0},
        "safety": {"adx_trend_threshold": 25, "adx_range_threshold": 20, "volatile_atr_mult": 2.5, "daily_loss_limit_pct": 3.0, "weekly_drawdown_limit_pct": 8.0, "consecutive_loss_limit": 3, "starting_balance": 1000},
        "risk": {"min_confluence": 70, "min_rr": 1.8, "max_open_positions": 3, "recency_bars": 40},
        "operation": {"watch_only": True},
        "exchange": {"leverage": 1}
    }
    
    # Pass tmp_path directly as state_dir to load the json correctly without mock side-effects
    orch = SafeOrchestrator(config=dummy_config, state_dir=str(tmp_path))
    
    # Verify it loaded the values correctly
    assert orch.sentiment_state["macro_sentiment"] == "RISK_ON"
    assert orch.sentiment_state["bitcoin_trend"] == "BULLISH"
    assert orch.sentiment_state["confidence_score"] == 0.85
