import asyncio
import os
import json
import datetime
from pathlib import Path
import httpx

try:
    import google.generativeai as genai
except ImportError:
    genai = None

ROOT = Path(__file__).resolve().parents[2]

async def fetch_and_save_sentiment(api_key: str, db_url: str = None) -> dict:
    """Asenkron Fear & Greed ve Gemini AI sentiment analizini yurutur.
    
    Analiz sonuclarini local state/ai_sentiment_registry.json dosyasina yazar.
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

    # 2. Gemini AI Studio Entegrasyonu
    sentiment_data = None
    
    if genai and api_key:
        try:
            genai.configure(api_key=api_key)
            model = genai.GenerativeModel('gemini-1.5-flash')
            
            prompt = (
                "Analyze the cryptocurrency market sentiment. "
                f"Fear and Greed Index is currently at {fg_value}. "
                "Output ONLY a raw JSON structure matching exactly this template: "
                '{"macro_sentiment": "RISK_ON", "confidence_score": 0.85, "fear_and_greed": 65, "bitcoin_trend": "BULLISH", "reasoning": "Brief explanation"}. '
                "Do not put markdown formatting or backticks around the JSON."
            )
            
            # Asenkron content generation
            response = await model.generate_content_async(prompt)
            clean_text = response.text.strip()
            # JSON block'u temizle (gerekirse ```json ... ```)
            if clean_text.startswith("```"):
                lines = clean_text.split("\n")
                clean_text = "\n".join([line for line in lines if not line.startswith("```")])
            
            sentiment_data = json.loads(clean_text)
        except Exception:
            # Hata durumunda fallback devreye girecek
            sentiment_data = None

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
