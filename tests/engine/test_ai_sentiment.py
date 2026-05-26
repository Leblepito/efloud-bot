import pytest
from unittest.mock import AsyncMock, patch
from pathlib import Path

# We import the sentiment module which does not exist yet (this will trigger the failing test)
from engine.ai import sentiment

@pytest.mark.asyncio
async def test_fetch_sentiment_from_gemini():
    # Mock Gemini response
    mock_response = AsyncMock()
    mock_response.text = '{"macro_sentiment": "RISK_ON", "confidence_score": 0.85, "fear_and_greed": 65, "bitcoin_trend": "BULLISH", "reasoning": "BTC bullish structure"}'
    
    with patch("google.generativeai.GenerativeModel") as mock_model:
        mock_model.return_value.generate_content_async = AsyncMock(return_value=mock_response)
        
        # Call fetch with a fake api key
        res = await sentiment.fetch_and_save_sentiment(api_key="fake_key", db_url=None)
        
        assert res["macro_sentiment"] == "RISK_ON"
        assert res["bitcoin_trend"] == "BULLISH"
        assert res["confidence_score"] == 0.85
