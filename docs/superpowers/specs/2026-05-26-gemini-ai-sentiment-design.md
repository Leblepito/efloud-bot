# Design Spec: Gemini AI Makro Duygu Analizi & Sıfır Gecikmeli Karar Destek Layer'ı
# ═══════════════════════════════════════════════════════════════════════════
# Tarih: 2026-05-26 | Mimari: Registry & Asenkron State Sentezi
# Modül: engine/ai/sentiment.py & state/ai_sentiment_registry.json
# ───────────────────────────────────────────────────────────────────────────

## 1. Misyonal Hedef (Goal)
Efloud-bot'un 15 dakikalık giriş (Entry TF) tetiklenme anındaki milisaniyelik emir iletim hızını (ultra-low latency) bozmadan, Gemini 3.5 Flash ile asenkron olarak güncellenen makro duygu analizi (`RISK-ON` / `RISK-OFF` / `NEUTRAL`) ve rejim filtrelerini bir **RAM/State Registry** üzerinden 0ms gecikmeyle entegre etmek.

---

## 2. Mimari Yapı & Veri Akışı (Architecture & Data Flow)

Sistem, canlı ticaret motorunun çalışma hızını ağ gecikmelerinden korumak için iki katmanlı asenkron bir mimari kullanır:

```mermaid
graph TD
    subgraph Asenkron AI Güncelleme Layer'ı (Her 4 Saatte Bir)
        Scheduler[cron / 4h Scheduler] -->|1. Veri Topla| Collector[scripts/prefetch_data.py & Alternative.me API]
        Collector -->|2. Daily OHLCV + Fear & Greed| Gemini[Google AI Studio: Gemini 3.5 Flash]
        Gemini -->|3. JSON Sentiment Raporu| Writer[engine/ai/sentiment.py]
        Writer -->|4. Güncelle / Yaz| Registry[state/ai_sentiment_registry.json]
    end

    subgraph Canlı Emir Tetikleme Layer'ı (Entry TF - 15m - Sıfır Gecikme)
        Market[WebSocket Price Stream] -->|1. Yapı Tetiklendi BOS/CHoCH| SafeOrchestrator[engine/safe_orchestrator.py]
        SafeOrchestrator -->|2. Lokal RAM Sorgusu 0ms| Registry
        Registry -->|3. Sentiment: RISK-ON | SafeOrchestrator
        SafeOrchestrator -->|4. Confluence Bonusu +5 Puan| OrderGuard[engine/safety/position_guard.py]
        OrderGuard -->|5. Instant API Order| Binance[Binance Futures API]
    end
```

---

## 3. Bileşen Ayrıntıları (Component Details)

### A. RAM Registry (`state/ai_sentiment_registry.json`)
Otonom olarak yazılan duygu durumunun lokal JSON önbelleğidir. RAM'e yüklendiği için sorgu gecikmesi 0ms'dir:
```json
{
  "last_updated": "2026-05-26T13:15:00.000Z",
  "macro_sentiment": "RISK_ON",
  "confidence_score": 0.85,
  "fear_and_greed": 64.0,
  "bitcoin_trend": "BULLISH",
  "reasoning": "Bitcoin 30 günlük ortalamanin uzerinde konsolide oluyor. Fear & Greed 64 ile acgozluluk bolgesinde. Altcoinlerde hacim artisi var."
}
```

### B. AI Engine Service (`engine/ai/sentiment.py`)
Gemini API (Google AI Studio) çağrılarını ve veri derlemesini yürüten bağımsız servis:
- **Veri Derleyici (Collector):** CCXT üzerinden BTC/USDT Daily grafik mumlarını ve `Alternative.me` Fear & Greed API'sini asenkron çağırır.
- **LLM Prompting (Gemini 3.5 Flash):** Prompt, sistem prompt sızıntılarından (`system_prompts_leaks`) alınan en iyi few-shot ve structured JSON output kurallarına göre yapılandırılır.
- **Hata Yönetimi (Graceful Degradation):** Gemini API çöker veya internet bağlantısı koparsa, Registry otomatik olarak default `NEUTRAL` moduna düşer (`graceful degrade`). Ticaret akışı asla kesilmez.

### C. SafeOrchestrator Entegrasyonu (`engine/safe_orchestrator.py`)
- `SafeOrchestrator` her başlarken Registry'yi RAM belleğe yükler (`self.sentiment_state`).
- `confluence.py` puanlaması sırasında:
  - Eğer `macro_sentiment == "RISK_ON"` ise, **LONG** yönlü sinyallere `+5` confluence puanı bonusu eklenir, **SHORT** yönlü sinyaller filtrelenir veya ceza puanı alır.
  - Eğer `macro_sentiment == "RISK_OFF"` ise, **SHORT** yönlü sinyallere `+5` confluence puanı bonusu eklenir, **LONG** yönlü sinyaller filtrelenir veya ceza puanı alır.
  - Eğer `NEUTRAL` ise, bot standart SMC v1/v2 confluence kurallarını aynen uygular.

---

## 4. Test & QA Doğrulama Planı (Verification Plan)

### A. Mock Tabanlı Unit Testleri
*   `tests/engine/test_ai_sentiment.py` yazılacaktır.
*   Gemini HTTP çağrıları `unittest.mock` ile taklit edilecek; API timeout, rate limit ve JSON parsing hataları altındaki davranışlar test edilecektir (Zero-risk).

### B. Dry-run Entegrasyon Testi
*   Registry simüle edilerek canlı trade akışında confluence puanlarının dinamik güncellendiği doğrulanacaktır.
