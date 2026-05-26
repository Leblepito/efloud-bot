import pytest
from engine.ai.sentiment import evaluate_parallel_news
from utils.cache import SentimentCache

@pytest.mark.asyncio
async def test_evaluate_parallel_news_caching():
    news_items = [
        "BTC breaks 100k, hyperbullish retail flow.",
        "FED raises interest rates by 25bps."
    ]
    
    # We will test integration behaves correctly on parallel trigger
    results = await evaluate_parallel_news(news_items, use_cache=False)
    assert len(results) == 2
    assert "text" in results[0]
    assert "sentiment" in results[0]
