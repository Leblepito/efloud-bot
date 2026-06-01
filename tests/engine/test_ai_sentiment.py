import pytest
from unittest.mock import patch
from pathlib import Path

from engine.ai import sentiment


@pytest.mark.asyncio
async def test_fetch_sentiment_from_gemini():
    """Canonical A0: fetch_and_save_sentiment now delegates to
    ``engine.agents.gemini_client.GeminiClient`` (sync). We patch the
    client's ``complete_json`` to return a fixed payload; the rest of
    the function is unchanged from the original (Fear & Greed fetch,
    registry persistence, fallback).
    """
    fake_payload = {
        "macro_sentiment": "RISK_ON",
        "confidence_score": 0.85,
        "fear_and_greed": 65,
        "bitcoin_trend": "BULLISH",
        "reasoning": "BTC bullish structure",
    }

    # Patch the new path. The test is no longer coupled to the
    # google-generativeai SDK — the function routes through GeminiClient.
    from engine.agents import gemini_client as gc
    with patch.object(gc.GeminiClient, "complete_json",
                      return_value=fake_payload):
        res = await sentiment.fetch_and_save_sentiment(
            api_key="fake_key", db_url=None)

    assert res["macro_sentiment"] == "RISK_ON"
    assert res["bitcoin_trend"] == "BULLISH"
    assert res["confidence_score"] == 0.85
