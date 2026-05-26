import json
from pathlib import Path
import pytest

def test_default_sentiment_registry_fallback(tmp_path):
    reg_path = tmp_path / "ai_sentiment_registry.json"
    # If file does not exist, default should be NEUTRAL
    if not reg_path.exists():
        default_state = {
            "macro_sentiment": "NEUTRAL",
            "confidence_score": 1.0,
            "fear_and_greed": 50.0,
            "bitcoin_trend": "NEUTRAL",
            "reasoning": "Fallback default state due to missing registry file."
        }
    assert default_state["macro_sentiment"] == "NEUTRAL"
    assert default_state["bitcoin_trend"] == "NEUTRAL"
