import tempfile
import shutil
from pathlib import Path
from utils.cache import SentimentCache

def test_sentiment_cache_lifecycle():
    tmpdir = tempfile.mkdtemp()
    try:
        cache = SentimentCache(cache_dir=tmpdir)
        text = "Bitcoin is breaking all-time highs today!"
        payload = {"sentiment": "BULLISH", "score": 0.95}
        
        # Must be empty initially
        assert cache.get(text) is None
        
        # Save payload
        cache.set(text, payload)
        
        # Read payload back
        cached = cache.get(text)
        assert cached is not None
        assert cached["sentiment"] == "BULLISH"
        assert cached["score"] == 0.95
    finally:
        shutil.rmtree(tmpdir)
