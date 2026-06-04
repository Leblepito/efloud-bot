# Lane B — Screenshot + Visual Interpretation Spec

> **Lane B spec'i (2026-06-04)**
> Producer (efloud-bot) tarafından üretilen `content_job.created` event'lerini
> okuyup TradingView chart screenshot alır ve Gemini'ye yorumlatır.
>
> **Out of scope (bu spec)**: Lane C (copy), Lane D (görsel), Lane E (publish).
> Lane B bunlara input üretir.

## 0. Varsayımlar (yazarken netleştirildi)

| # | Varsayım | Doğrulandı mı? |
|---|---|---|
| B1 | Lane B = **Manus task** olarak çalışır, Hermes Python kodu **yazmaz** | ✅ Handoff §4 "Owner: Hermes + Manus task, gated" |
| B2 | Lane B input: `content_job.created` event + symbol+timeframe | ✅ Handoff §4 "Tasks: 1. Open TradingView chart for symbol/timeframe" |
| B3 | Lane B output: chart PNG + yorum JSON | ✅ Handoff §4 "4. Return structured output only" |
| B4 | Lane B connectors: Playwright + My Browser + Gemini | ✅ Handoff §4 "Recommended connectors" |
| B5 | Lane B **draft-only** (publish YOK) | ✅ Handoff §4 "no posting" + Phase 1 E |
| B6 | Lane B spec = **Manus task prompt template** + JSON input/output contract | ✅ Bu spec |
| B7 | Lane B **depolama**: Drive'a chart PNG, yorum JSON Drive veya local fallback | ⚠️ Drive auth expired (memory), Phase 1 = local |

## 1. Bağlam ve bağlantı

Lane A emitter (PR #155) `/app/data/content_jobs/YYYY-MM-DD.jsonl` dosyalarına
JSON event yazar. Lane B bu dosyaları okuyup her event için:
1. TradingView chart screenshot alır
2. Chart'ı Gemini'ye gönderir, yapısal yorum ister
3. Output'u (chart PNG + yorum JSON) Drive'a yazar
4. Lane F'e metric bildirir (opsiyonel, default OFF)

**Owner**: Manus task (Hermes orchestrate eder, kod yazmaz).

**Trigger modeli**:
- **Pull-based**: Hermes (veya cron) günlük dosyayı okur, işlenmemiş event_id'leri toplar
- **Idempotent**: event_id set ile zaten işlenmiş event'ler skip edilir
- **Frequency**: 4-6 saatte bir cron tetikler (günde 2-3 kez)

**Gating**: Spec, plan, sonuçlar Telegram ile operatöre bildirilir. **Draft-only**,
publish YOK (handoff §4 madde 5, "no posting"). Sonuçlar Drive'da review için
hazır durur, operatör manuel publish kararı verir.

## 2. Input contract

Lane B, Lane A'nın `content_job.created` event'lerini okur:

```json
{
  "event_id": "uuid",
  "event_type": "content_job.created",
  "schema_version": "1.0.0",
  "occurred_at": "ISO 8601 UTC",
  "source": { "service": "efloud-bot", "env": "mainnet", "commit": "...", "loop_id": "..." },
  "signal": {
    "symbol": "BTC/USDT",
    "direction": "LONG",
    "entry": 50000, "sl": 49000, "tp1": 52000, "tp2": 53000,
    "confluence": 85, "timeframe": "15m",
    "horizon": null, "regime": "TRENDING",
    "reasons": ["FVG", "OB"], "reasons_detail": {"trace_id": "..."}
  },
  "compliance": { "...": "..." }
}
```

**Zorunlu alanlar** (Lane B'nin ihtiyacı): `event_id`, `signal.symbol`,
`signal.direction`, `signal.entry`, `signal.sl`, `signal.tp1`, `signal.timeframe`,
`signal.confluence`, `signal.reasons`.

**Opsiyonel alanlar**: `tp2`, `horizon`, `regime`, `chart_url` (varsa öncelikli),
`chart_local`.

**Validation**: Lane A schema `content_job-1.0.0.json` ile zaten validate
edilmiş. Lane B ek schema kontrolü yapmaz (consumer-side defansif kod minimal).

## 3. Output contract

Lane B her event için iki artifact üretir:

### 3.1. Chart PNG

- **Konum**: Google Drive, klasör `u2algo/lane-b/charts/YYYY-MM-DD/`
- **Format**: PNG, 1920x1080, ~500KB
- **İçerik**: TradingView chart, sembol + timeframe + entry/SL/TP yatay çizgiler
- **File name**: `{event_id}.png` (UUID, içerik izlenebilirliği için)

### 3.2. Yorum JSON

- **Konum**: Google Drive, klasör `u2algo/lane-b/analysis/YYYY-MM-DD/`
- **Format**: JSON
- **File name**: `{event_id}.json`
- **Schema** (Lane B kendi tanımlar):

```json
{
  "event_id": "uuid",
  "symbol": "BTC/USDT",
  "timeframe": "15m",
  "direction": "LONG",
  "entry": 50000, "sl": 49000, "tp1": 52000, "tp2": 53000,
  "confluence": 85,
  "chart_png_drive_id": "drive_file_id",
  "chart_png_url": "https://drive.google.com/...",
  "model": "gemini-2.5-pro",
  "model_version": "...",
  "analysis": {
    "structure": "TRENDING | RANGING | VOLATILE | CHOPPY",
    "smc_zones": [
      {"type": "FVG", "price_range": [49900, 50100], "freshness": "fresh|tested|broken"},
      {"type": "OB",  "price_range": [49500, 49800], "freshness": "fresh"}
    ],
    "invalidation": "if close below 48800 on 15m",
    "risk_note": "Stop distance 2%, R:R 1:1 to TP1, 1:3 to TP2",
    "summary": "LONG setup with 15m FVG retest + bullish OB confluence.",
    "confidence": "high | medium | low"
  },
  "latency_ms": 12500,
  "cost_usd": 0.012,
  "draft_at": "ISO 8601 UTC",
  "model_raw_response_ref": "drive_id_or_null"
}
```

**`confidence`**: Gemini'nin self-reported güven skoru, **sinyal olarak kullanılır**
(Lane C confidence < medium olursa copy üretmez).

## 4. Akış (her event için)

```
Hermes (cron tick)
  ↓ (4-6 saatte bir)
Read /app/data/content_jobs/YYYY-MM-DD.jsonl (push from Hetzner to local,
                                               veya SSH rsync)
  ↓
Filter: event_id not in processed_set
  ↓ (unprocessed events)
For each event:
  ↓
  Build Manus task prompt (template + event JSON)
  ↓
  Manus task POST (api.manus.ai/v2/tasks)
    ├─ Connector 1: Playwright
    │   - Open TradingView chart URL:
    │     https://www.tradingview.com/chart/?symbol=BINANCE:{symbol_no_slash}.P
    │     &interval={timeframe}
    │   - Annotate entry/SL/TP yatay lines via Playwright eval
    │   - Screenshot 1920x1080
    │   - Upload to Drive: u2algo/lane-b/charts/YYYY-MM-DD/{event_id}.png
    │
    ├─ Connector 2: Gemini
    │   - Image input: chart PNG
    │   - Prompt: structured analysis JSON (schema: §3.2)
    │   - Parse response, validate
    │   - Upload to Drive: u2algo/lane-b/analysis/YYYY-MM-DD/{event_id}.json
    │
    └─ Return: task_id, drive_ids, cost, latency
  ↓
Update processed_set (local + optional Supabase mirror)
  ↓
Telegram: "[Lane B] processed N events, X succeeded, Y failed, $Z total"
```

## 5. Connector envanteri (handoff §4 + §25)

- **Playwright** (`356d5bc1-fb9f-4fa1-babb-05039dc09d63`): browser otomasyon
- **My Browser** (`be268223-40b2-4f3c-a907-c12eb1699283`): yedek browser
- **Gemini** (`4157dedf-1326-4be8-9295-51416c7dba62`): multimodal vision
- **Google Drive** (`f8900a57-4bd7-46cc-83a3-5ebd2420a817`): artifact storage

**Connector auth durumu** (handoff §3 + memory):
- Drive re-authorize gerekli (eski auth expire)
- Gemini + Playwright + My Browser: temiz (12 verified listede var)
- **Blokaj**: Drive bağlanana kadar Lane B **drafts to local**, Drive'a yazamaz
  → Lane B Phase 1: local artifacts (Hetzner bind-mount veya local disk)
  → Phase 2: Drive'a yaz (auth tamamlanınca)

## 6. Failure / edge cases

1. **Drive offline**: Manus task Drive yazamaz → local fallback
   (`/tmp/lane-b/{event_id}.{png,json}`), Lane F metrics'e `drive_offline=1`.
2. **Gemini rate limit**: 429 → exponential backoff 5s, 30s, 2dk, max 3 retry.
3. **Gemini response invalid JSON**: parse fail → log, Lane F metrics,
   event'i `failed_set`'e ekle, **sonraki cron'da tekrar dene** (manual review).
4. **Playwright chart load fail (timeout)**: 3 retry, sonra `failed_set`.
5. **TradingView chart unavailable for symbol**: skip event, log warning.
6. **Manus task stuck (5dk+ running, 0 progress)**: stop + alert (skill:
   `telegram-manus-approval-loop`).
7. **event_id duplicate** (consumer-side): idempotent set ile skip.
8. **Timeframe parse error**: skip event, log error.

## 7. Cost / rate budget

- **Gemini input**: 1 chart image + prompt ~1k token
- **Gemini output**: ~500 token analysis
- **Per event cost**: ~$0.01-0.02 (Gemini 2.5 Pro pricing)
- **Daily budget cap**: $5.00 (~250-500 events/gün)
- **Cron frequency**: 4-6 saat/günde 2-3 batch

**Budget guard**: Manus task başına max 100 event, günde max 3 task = 300
event cap (aşılırsa alert).

## 8. Out of scope (bu spec)

- ❌ Lane C (copywriting) — bu spec'in output'unu okur, ayrı iş
- ❌ Lane D (görsel/video) — Lane C çıktısını alır
- ❌ Lane E (publish) — Lane D çıktısını alır
- ❌ Lane F (CRM) — opsiyonel metric mirror
- ❌ Real-time push (websocket) — cron batch yeterli
- ❌ Backfill (>7 gün) — ileri iş

## 9. Definition of done (spec)

- [x] Input contract (Lane A event JSON)
- [x] Output contract (chart PNG + yorum JSON schema)
- [x] Akış tanımı (her event için 4-6 adım)
- [x] Connector envanteri + auth durumu
- [x] Failure mode'lar (8 senaryo)
- [x] Cost / rate budget
- [x] Out of scope net

## 10. Spec sonrası adımlar (PR-ready)

```
1. Implementer prompt template yaz:
   docs/superpowers/specs/2026-06-04-lane-b-implementer-prompt.md
   verify: Manus task POST payload çalışıyor, event_id ile idempotent

2. Hermes helper script yaz:
   scripts/lane_b_consumer.py (cron tick'te çalışır, batch POST)
   verify: 1 event test, dosyaya yazar, processed_set günceller

3. PR aç (feat/lane-b-consumer)
   verify: pytest 5/5, Manuel dry-run 1 event, Telegram onay alındı
```

**Blocker**: Drive auth tamamlanmadan **production deploy** yapılamaz
(local fallback ile test edilebilir).
