# Telegram topluluk kanalı → Instagram + X paylaşım akışı

Görev: `collab/tasks/open/T-20261106-02-social-from-community-channel.md`
Durum: dry-run doğrulandı, canlı paylaşım kapalı (varsayılan).

Topluluk kanalına düşen işlemleri Instagram (1080×1350) ve X için görsel +
caption taslağına çeviren, operatör onayından sonra paylaşan akış. Mevcut
sosyal hat (Lane A→G) olduğu gibi kullanılır; Lane B–G arayüzleri değişmedi.

## 1. Kaynak seçimi

**Seçilen: 2 — Telegram kanal mesajları (+ toplayıcı).**

Gerekçe:

- Kanal tek bir yerde **iki** mesaj tipini birden taşıyor: bot işlem postları
  (`engine/notifications/telegram_notifier.py`, `EFLOUD_CUSTOMER_TG_TRADES`) ve
  `u2algo Price Action` indikatör sinyalleri (TradingView webhook). Bot journal
  (seçenek 1) yalnız bot işlemlerini kapsar; indikatör sinyalleri journal'a
  hiç düşmez. Görev tanımı ikisini de istiyor.
- Kanal postu operatörün **zaten yayınladığı** sinyaldir; sosyal taslak için
  ayrı bir "yayınlanabilir mi" kararı gerekmez.
- Bot API kanal geçmişini okuyamaz: `getUpdates` yalnız bot kanal admini iken
  gelen **yeni** `channel_post`'ları verir. Bu yüzden
  `scripts/telegram_channel_collector.py` yeni postları günlük JSONL'ye
  biriktirir; Lane B'nin beklediği `{jobs}/{YYYY-MM-DD}.jsonl` düzenini üretir.

Seçenek 1'in (bot journal) tek üstünlüğü confluence skorunun gerçek olması;
kanal postunda bu alan yok (bkz. §6).

## 2. Akış

```
Telegram topluluk kanalı
        │  getUpdates (allowed_updates=["channel_post"], bot admin)
        ▼
scripts/telegram_channel_collector.py
        │  parse → Lane A şemalı event, event_id = uuid5(chat_id:message_id)
        ▼
{jobs}/{date}.jsonl
        │
        ▼
scripts/social_from_telegram.py  ──►  scripts/daily_social_run.run_all
        │                                   Lane B  analysis (offline processor)
        │                                   Lane C  caption + compliance gate
        │                                   Lane D  chart PNG 1080×1350
        │                                   Lane G  per-platform bundle
        ▼
{work}/bundles/{date}/bundles/{event}.{platform}.json   state=pending_review
        │
        ├─ approve  → state=approved
        ▼
scripts/lane_g_publish.run  →  Lane E  →  backend/social (X / Instagram)
                                          dry-run varsayılan, --live operatör
```

Tek komutluk özet: `collect` → `draft` → `approve` → `publish`.

## 3. Komutlar

Hepsi repo kökünden, `python -m` ile. `--date` UTC günüdür.

### 3.1 Topla

```bash
export EFLOUD_CUSTOMER_TG_CHANNEL_ID=-1002000000001
export EFLOUD_CUSTOMER_TG_TOKEN=<bot-token>          # asla commit edilmez

python -m scripts.social_from_telegram collect \
  --channel-id "$EFLOUD_CUSTOMER_TG_CHANNEL_ID" \
  --out /app/data/content_jobs \
  --state state/tg_collector/state.json
```

Token yoksa / ağ yoksa fixture ile çevrimdışı çalıştırma:

```bash
python -m scripts.social_from_telegram collect \
  --channel-id -1002000000001 \
  --out /tmp/efloud-jobs --state /tmp/efloud-state/tg.json \
  --from-file tests/fixtures/telegram_channel_posts_2026-11-06.json
```

### 3.2 Taslak üret (dry-run, varsayılan)

```bash
python -m scripts.social_from_telegram draft \
  --date 2026-11-06 \
  --jobs /app/data/content_jobs \
  --work /tmp/efloud-social \
  --cache-dir cache/ohlcv \
  --platforms x,instagram \
  --export-dir collab/outputs/abacus/T-20261106-02
```

`--allow-fetch` yalnız mum cache'i boşken Binance public REST'e çıkar; cron/CI
bu bayrağı kullanmaz. `--auto-approve` **verilmez** — bundle'lar
`pending_review` kalır.

### 3.3 Onayla

```bash
# günün tüm pending bundle'ları
python -m scripts.social_from_telegram approve --date 2026-11-06 --work /tmp/efloud-social

# tek bir (event, platform)
python -m scripts.social_from_telegram approve --date 2026-11-06 \
  --work /tmp/efloud-social --event-id <event_id> --platform instagram
```

### 3.4 Paylaş

```bash
# dry-run: DryRunPublisher kaydeder, ağa çıkmaz
python -m scripts.social_from_telegram publish --date 2026-11-06 --work /tmp/efloud-social

# canlı: yalnız operatör, yalnız flag'ler açıkken
export X_API_ENABLED=1
export INSTAGRAM_ENABLED=1
python -m scripts.social_from_telegram publish --date 2026-11-06 \
  --work /tmp/efloud-social --live
```

`--live` tek başına yetmez: Lane E her platformun kendi flag'ini ve
kimlik bilgisini kontrol eder; flag kapalıysa sonuç `no_publishers` olur ve
hiçbir çağrı yapılmaz.

## 4. Caption kuralları

Her caption Lane C'de üretilir, Lane G'de platforma göre yeniden şekillenir ve
**üç kez** `scripts/content_compliance.find_violations` ile denetlenir (Lane C,
Lane D overlay, Lane G; ayrıca Lane E yayın anında). Kural seti:

- `find_violations` boş dönmeli.
- `COMPLIANCE_TR` ("Bu yatırım tavsiyesi değildir. Trade kendi riskinizdir.")
  her caption'da bulunmalı; X'te 280 karakter sınırı aşılırsa gövde kırpılır,
  disclaimer asla kırpılmaz (`lane_g_social._truncate_caption`).
- Kesin getiri vaadi, bakiye, USD kâr, pozisyon büyüklüğü yasak — caption ve
  grafik yalnız oran/risk yüzdesi taşır (`Risk ~0.6% · R:R 1:2.0 (TP1)`).
- "Bot indikatörle aynı setup ve girişleri alır" denebilir.
- "TP'ler birebir aynı" **denmez**; caption'larda parite iddiası yoktur
  (`tests/test_social_from_telegram.py::test_captions_make_no_parity_claim`).
- TradingView script açıklamasına veya grafiğine Telegram/sosyal link konmaz;
  grafik footer'ı yalnız disclaimer + `u²Algo · @u2algo` watermark'ı taşır.

## 5. Dry-run çıktısı

`collab/outputs/abacus/T-20261106-02/` — 3 örnek işlem × (IG + X):

| Dosya | İçerik |
|---|---|
| `<event>.instagram.png` / `<event>.x.png` | 1080×1350 anotasyonlu grafik (entry/SL/TP1/TP2) |
| `<event>.instagram.caption.txt` / `<event>.x.caption.txt` | platform caption'ı |
| `manifest.json` | boyut, compliance sonucu, disclaimer, bundle state |

Örnekler `tests/fixtures/telegram_channel_posts_2026-11-06.json` içindeki
**kurgusal** kanal postlarından üretildi (gerçek işlem kaydı değil). En büyük
dosya 64 KB; sınır 150 KB. Bundle'lar `pending_review`, hiçbir paylaşım
yapılmadı.

## 6. Bilinen sınırlamalar

- **Confluence:** kanal postunda skor yok. Şema `signal.confluence` için integer
  istediğinden varsayılan `60` yazılır ve
  `signal.reasons_detail.confluence_source = "channel_default"` ile işaretlenir.
  Post `Confluence: 82/100` içeriyorsa gerçek değer kullanılır
  (`confluence_source = "channel_post"`). Lane B processor bu yüzden confidence
  tabanını `medium` yapar; `>=75` ise `high`.
- **Timeframe:** bot postlarında TF yok; `15m` varsayılır ve
  `timeframe_source = "default"` olarak işaretlenir. İndikatör postlarındaki
  `· 15` alanı `15m`'e normalize edilir.
- **`source.service`:** `telegram-channel-collector`. Şema bu alanı
  `efloud-bot` const'una sabitliyor; collector çıktısını bota atfetmemek için
  bilinçli sapma. `validate_event()` şemayı bu tek alan gevşetilerek uygular.
- **Yaşam döngüsü postları:** `TP1 hit` ve `trade closed` mesajları feed'e
  yazılmaz (`skipped_kind`), çünkü grafik için entry/SL/TP1 üçlüsü yok.
- **Geçmiş:** `getUpdates` kanal geçmişini vermez. Collector ilk çalıştığı andan
  sonrasını biriktirir. Webhook kuruluysa `getUpdates` 409 döner; collector bunu
  `CollectorError` olarak yükseltir.
- **X hashtag seti:** `lane_g_social.HASHTAGS["x"]` sabit ve her sembol için
  `#BTC` içeriyor; SOL postunda da `#BTC` görünür. Lane G'ye ait ayrı bir düzeltme
  konusu — bu adaptör Lane G'yi değiştirmiyor.

## 7. Test

```bash
python -m pytest tests/test_social_from_telegram.py -q
python -m pytest --ignore=external_repos --import-mode=importlib -q --capture=no
```

`--capture=no` bu makinede pytest 9 + Windows capture teardown hatasını
(`ValueError: I/O operation on closed file`) atlatmak için gerekli; hata bu
değişiklikten bağımsız olarak temiz `origin/master`'da da görülüyor.
