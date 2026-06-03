import asyncio
import os
import json
import datetime
from pathlib import Path
import httpx
from typing import List, Dict, Any, Optional
from utils.cache import SentimentCache

ROOT = Path(__file__).resolve().parents[2]

# Initialize global cache
_cache = SentimentCache()

async def fetch_and_save_sentiment(api_key: str = None, db_url: str = None,
                                   llm_config: dict = None) -> dict:
    """Asenkron Fear & Greed ve LLM macro sentiment analizini yurutur.

    Analiz sonuclarini local state/ai_sentiment_registry.json dosyasina yazar.

    The LLM HTTP call is delegated to the shared provider factory
    (:func:`engine.agents.llm.make_llm_client`) — default Claude, Gemini
    selectable via ``LLM_PROVIDER`` / ``llm_config["provider"]``. We run the
    sync ``complete_json`` via ``asyncio.to_thread`` so the event loop isn't
    blocked. The provider client self-resolves its own API key from env; the
    legacy ``api_key`` param is accepted for back-compat but no longer the
    provider key (a Gemini key must not reach a Claude client).
    """
    # 1. Alternative.me Fear & Greed Index API cagrisi
    fg_value = 50.0
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get("https://api.alternative.me/fng/", timeout=5)
            if resp.status_code == 200:
                data = resp.json()
                fg_value = float(data["data"][0]["value"])
    except Exception:
        pass

    # 2. LLM macro sentiment (provider factory: default Claude, gemini fallback)
    sentiment_data = None
    prompt = (
        "Analyze the cryptocurrency market sentiment. "
        f"Fear and Greed Index is currently at {fg_value}. "
        "Output ONLY a raw JSON structure matching exactly this template: "
        '{"macro_sentiment": "RISK_ON", "confidence_score": 0.85, "fear_and_greed": 65, "bitcoin_trend": "BULLISH", "reasoning": "Brief explanation"}. '
        "Do not put markdown formatting or backticks around the JSON."
    )

    cached_val = _cache.get(prompt)
    if cached_val:
        sentiment_data = cached_val
    else:
        try:
            # Imported lazily so ``engine.ai.sentiment`` still imports in
            # environments where ``engine.agents`` is unavailable.
            from engine.agents.llm import make_llm_client
            client = make_llm_client(llm_config or {})
            # complete_json is sync; offload so the event loop stays alive.
            # Returns {} on any failure (incl. no key) → NEUTRAL fallback below.
            sentiment_data = await asyncio.to_thread(
                client.complete_json, prompt
            )
        except Exception:
            sentiment_data = None

        if sentiment_data:
            # Defensive: ensure the schema downstream code expects.
            if not all(k in sentiment_data for k in (
                "macro_sentiment", "confidence_score",
                "fear_and_greed", "bitcoin_trend", "reasoning"
            )):
                sentiment_data = None
            else:
                _cache.set(prompt, sentiment_data)

    # Fallback / Default state
    if not sentiment_data:
        sentiment_data = {
            "macro_sentiment": "NEUTRAL",
            "confidence_score": 1.0,
            "fear_and_greed": fg_value,
            "bitcoin_trend": "NEUTRAL",
            "reasoning": "Fallback default state due to API timeout or failure."
        }

    # Tarih bilgisini ekle/guncelle
    sentiment_data["last_updated"] = datetime.datetime.now(datetime.timezone.utc).isoformat().replace("+00:00", "Z")

    # Registry dosyasina kaydet
    registry_path = ROOT / "state" / "ai_sentiment_registry.json"
    registry_path.parent.mkdir(parents=True, exist_ok=True)
    with open(registry_path, "w", encoding="utf-8") as f:
        json.dump(sentiment_data, f, indent=2)

    return sentiment_data


async def evaluate_single_news(news: str, use_cache: bool = True) -> Dict[str, Any]:
    """Evaluates sentiment for a single news piece with optional caching."""
    if use_cache:
        cached = _cache.get(news)
        if cached:
            return cached
            
    # Mock/Actual API Evaluation Layer
    # (Extracts macro sentiment from news using Gemini LLM call pattern)
    sentiment_result = {
        "text": news,
        "sentiment": "BULLISH" if "BTC" in news or "break" in news or "high" in news or "bull" in news else "NEUTRAL",
        "confidence": 0.85
    }
    
    if use_cache:
        _cache.set(news, sentiment_result)
        
    return sentiment_result


async def evaluate_parallel_news(news_list: List[str], use_cache: bool = True) -> List[Dict[str, Any]]:
    """Evaluates sentiment for multiple news articles concurrently (chunked)."""
    tasks = [evaluate_single_news(news, use_cache) for news in news_list]
    return await asyncio.gather(*tasks)
