import pytest
from unittest.mock import patch
from pathlib import Path

from engine.ai import sentiment


@pytest.mark.asyncio
async def test_fetch_sentiment_from_llm():
    """fetch_and_save_sentiment delegates to the shared LLM provider factory
    (default Claude). We patch the default client's ``complete_json`` to return
    a fixed payload; the rest of the function is unchanged from the original
    (Fear & Greed fetch, registry persistence, fallback).
    """
    fake_payload = {
        "macro_sentiment": "RISK_ON",
        "confidence_score": 0.85,
        "fear_and_greed": 65,
        "bitcoin_trend": "BULLISH",
        "reasoning": "BTC bullish structure",
    }

    # Default provider is Claude — patch ClaudeClient.complete_json. (The HTTP
    # is bypassed, so no real API key is needed.) Bypass the sentiment cache so
    # the prompt is actually routed to the (patched) client.
    from engine.agents import claude_client as cc
    with patch.object(cc.ClaudeClient, "complete_json", return_value=fake_payload), \
         patch.object(sentiment._cache, "get", return_value=None):
        res = await sentiment.fetch_and_save_sentiment(llm_config=None, db_url=None)

    assert res["macro_sentiment"] == "RISK_ON"
    assert res["bitcoin_trend"] == "BULLISH"
    assert res["confidence_score"] == 0.85


@pytest.mark.asyncio
async def test_fetch_sentiment_gemini_fallback_still_works():
    """LLM_PROVIDER=gemini routes the same pipeline through GeminiClient."""
    fake_payload = {
        "macro_sentiment": "RISK_OFF",
        "confidence_score": 0.7,
        "fear_and_greed": 30,
        "bitcoin_trend": "BEARISH",
        "reasoning": "fallback path",
    }
    from engine.agents import gemini_client as gc
    with patch.object(gc.GeminiClient, "complete_json", return_value=fake_payload), \
         patch.object(sentiment._cache, "get", return_value=None):
        res = await sentiment.fetch_and_save_sentiment(
            llm_config={"provider": "gemini"}, db_url=None)

    assert res["macro_sentiment"] == "RISK_OFF"
    assert res["bitcoin_trend"] == "BEARISH"
