# Content Jobs Consumer Contract — 2026-06-04

> **Lane A — Producer tarafı spec'i (D adımı tamamlandı).**
> Emitter (efloud-bot) -> consumer (Lane B/C/D/E/F) şeması. Schema contract.
>
> Sıradaki: A adımı (kod).

## 1. Bağlam

efloud-bot bir sinyal ürettiğinde, bu sinyali marketing pipeline'ına
aktaracak JSON event yayınlar. Pipeline 5 lane'den oluşur (2026-05-31
`manus-connectors-task-distribution.md` §95-229). Lane A (bu doküman) producer,
diğer lane'ler consumer.

**Karar kuralı**: producer (bot) trade execution'dan farklı bir kod yolundan
asla geçmemeli. Sinyal event'i, `NotificationManager.signal_readonly` ve
`position_opened` çağrılarının **yan etkisi** olarak emit edilir. Lane A
kapatılırsa hiçbir şey olmaz (inert).

## 2. Transport kararları

| Karar | Seçim | Gerekçe |
|---|---|---|
| Push / pull | Push (file append) | Container her zaman ayakta, polling overhead'i gereksiz |
| Storage | Local JSONL | Hetzner'da `state_1k/` volume zaten var, ek infra yok |
| Format | JSON Lines (one event per line) | Append-only, atomic, streaming parse |
| Schema dili | JSON Schema draft 2020-12 | Validator mevcut, Lane B/C tipli dille parse edebilir |
| Retention | 90 gün (eski gzip) | Backtest referans + regulatory |
| Multi-instance | Tek (Hetzner tek container) | Distributed lock gereksiz |
| Ordering | Per-symbol FIFO | Cross-symbol ordering gerekmiyor |
| Failure | At-least-once, dup'a dayanıklı | Lane B idempotent, `event_id` ile |
| Backpressure | Yok | Volume düşük: 5-50 sinyal/gün |

## 3. Storage yolu

Container bind-mount: `/app/data/content_jobs/` (production Hetzner
`docker-compose.prod.yml`'de `state_1k/` mount var, yanına eklenir).

Dosya isimlendirme: `YYYY-MM-DD.jsonl` (UTC günlük rotation). Lock ve atomic
write implementasyon detayı, `engine/content_jobs.py` içinde.

## 4. Schema

Schema ayrı dosyada: `docs/schemas/content_job-1.0.0.json`. Spec bunu referans
verir; şema değişirse major version bump.

İki event_type:
- `content_job.created` — bot sinyali oluşturdu (read-only dahil)
- `content_job.position_opened` — gerçek emir, fill aldı (TP/SL/quantity ile)

Zorunlu alanlar: `event_id`, `event_type`, `schema_version`, `occurred_at`,
`source`, `signal`, `compliance`. Compliance disclaimer Türkçe + İngilizce
zorunlu sabit string.

## 5. Consumer contract (Lane B/C/D/E/F)

Pull-based read (cron veya Manus task):
```python
import json, datetime as dt
path = f"/data/content_jobs/{dt.date.today().isoformat()}.jsonl"
with open(path) as f:
    for line in f:
        line = line.strip()
        if not line: continue
        event = json.loads(line)
        # idempotent: event_id set ile skip
```

**Schema validation**: consumer tarafı `jsonschema` paketiyle doğrular. Şema
URL `https://u2algo.com/schemas/content_job-1.0.0.json` (ileride host edilecek,
URL'ye pinned).

## 6. Lane tüketim matrisi

| Lane | Dinler | Çıktısı |
|---|---|---|
| **B** screenshot | `created` | chart PNG + yorum JSON |
| **C** copy | `created`, `position_opened` | X/IG/TG/YT/blog metin |
| **D** görsel | C çıktısı | branded PNG/video |
| **E** publish | D çıktısı | draft post (manual approval) |
| **F** CRM | her ikisi | metrics dashboard |

Minimum viable zincir: A -> C -> E (B+D atlanır, opsiyonel).

## 7. Failure / edge cases

1. Container crash mid-write: tmp dosyası kalır, atomic rename garantisi.
2. Disk full (`ENOSPC`): log ERROR, event drop, bot trade devam eder (emit non-critical).
3. Permission denied: log warning, `enabled=false` fallback. Bot devam eder.
4. Schema validation fail (consumer): event drop, Lane F metrics'e `schema_violations++`.
5. Duplicate `event_id`: consumer set'e alıp filter eder (idempotent).
6. Clock skew: ISO 8601 UTC, `occurred_at` ile sırala, `event_id` tiebreaker.

## 8. Test stratejisi (Lane A emitter testleri)

1. `test_emit_creates_file` — ilk emit dosyayı oluşturur
2. `test_atomic_write_no_partial_files` — crash simülasyonu, tmp kalmaz
3. `test_daily_rotation_creates_new_file` — gece yarısı yeni dosya
4. `test_concurrent_emit_no_corruption` — 100 paralel emit, hepsi valid JSON
5. `test_event_id_unique` — UUID v4, collision (100k emit)
6. `test_schema_validation_passes` — `jsonschema` ile her emit validate
7. `test_disabled_emitter_is_noop` — flag OFF ise dosya oluşmaz
8. `test_disk_full_fallback` — ENOSPC simülasyonu, bot crash etmez

## 9. Out of scope (bu PR)

- Lane B/C/D/E/F implementasyonu (Manus task'ları ayrı iş)
- Cloud storage mirror (Supabase / S3) — ayrı PR
- Real-time push (websocket / SSE) — Lane B cron-based yeterli
- Cross-instance locking — tek instance varsayım
- Schema hosting (`u2algo.com/schemas/...`) — local path referansı yeterli

## 10. D adımı Definition of done

- [x] Schema tanımlı (JSON Schema 2020-12, ayrı dosya)
- [x] Storage yolu kararı (local JSONL, Hetzner bind-mount)
- [x] Transport kararı (push, file append)
- [x] Consumer contract yazıldı
- [x] Failure mode'lar listelendi
- [x] Test stratejisi belirlendi
- [x] Out of scope net

## 11. A adımı (kod) planı

```
1. engine/content_jobs.py -> ContentJobEmitter sınıfı
   verify: import edilebilir, 8 unit test geçer

2. engine/notifications/__init__.py -> signal_readonly / position_opened'a
   emit() inject (Seçenek A: timeframe/regime/horizon/trace_id parametreleri
   mevcut çağrılara eklenir, geriye dönük None default)
   verify: emit() çağrıldığında JSON dosyaya yazılır, schema validate geçer

3. main.py + backend/bot_runner.py -> ikisine de ContentJobEmitter wire
   verify: aynı param signature, EFLOUD_CONTENT_EMITTER_ENABLED env okunur

4. tests/test_content_jobs.py -> 8 test
   verify: pytest 8 passed, 0 fail

5. config.yaml -> content_emit.enabled=false default
   verify: emit=False iken test, dosya oluşmaz
```
