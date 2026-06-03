import pytest
from unittest.mock import patch, MagicMock
import pandas as pd
from engine.signals import validate_signal_with_gemini

def test_validate_signal_high_confidence():
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    # Anthropic /v1/messages response shape (default provider is now Claude).
    mock_resp.json.return_value = {
        "content": [
            {"type": "text",
             "text": '{"valid": true, "confidence": 0.85, "reasoning": "High volume institutional CHoCH"}'}
        ]
    }

    idx = pd.date_range("2026-05-26", periods=20, freq="15min")
    df = pd.DataFrame(
        {"open": [10.0]*20, "high": [11.0]*20, "low": [9.0]*20, "close": [10.5]*20, "volume": [1000]*20},
        index=idx
    )

    with patch("httpx.post", return_value=mock_resp), patch("engine.signals._struct_cache.get", return_value=None):
        res = validate_signal_with_gemini(
            symbol="BTC/USDT",
            direction="LONG",
            entry=10.5,
            sl=9.0,
            tp=12.0,
            df_htf=df,
            df_mtf=df,
            df_entry=df,
            api_key="fake_key"
        )
        assert res["valid"] is True
        assert res["confidence"] == 0.85
        assert "institutional" in res["reasoning"]

def test_validate_signal_low_confidence_filtered():
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "content": [
            {"type": "text",
             "text": '{"valid": false, "confidence": 0.35, "reasoning": "Retail liquidity trap"}'}
        ]
    }

    idx = pd.date_range("2026-05-26", periods=20, freq="15min")
    df = pd.DataFrame(
        {"open": [10.0]*20, "high": [11.0]*20, "low": [9.0]*20, "close": [10.5]*20, "volume": [1000]*20},
        index=idx
    )

    with patch("httpx.post", return_value=mock_resp), patch("engine.signals._struct_cache.get", return_value=None):
        res = validate_signal_with_gemini(
            symbol="BTC/USDT",
            direction="LONG",
            entry=10.5,
            sl=9.0,
            tp=12.0,
            df_htf=df,
            df_mtf=df,
            df_entry=df,
            api_key="fake_key"
        )
        assert res["valid"] is False
        assert res["confidence"] == 0.35

def test_validate_signal_graceful_degradation():
    idx = pd.date_range("2026-05-26", periods=20, freq="15min")
    df = pd.DataFrame(
        {"open": [10.0]*20, "high": [11.0]*20, "low": [9.0]*20, "close": [10.5]*20, "volume": [1000]*20},
        index=idx
    )

    with patch("httpx.post", side_effect=Exception("Timeout connection error")), patch("engine.signals._struct_cache.get", return_value=None):
        res = validate_signal_with_gemini(
            symbol="BTC/USDT",
            direction="LONG",
            entry=10.5,
            sl=9.0,
            tp=12.0,
            df_htf=df,
            df_mtf=df,
            df_entry=df,
            api_key="fake_key"
        )
        # Should degrade gracefully, keeping the signal
        assert res["valid"] is True
        assert res["confidence"] == 1.0
        assert "Fallback" in res["reasoning"]
