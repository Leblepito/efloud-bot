# P-Kronos-Social — 4 Saatlik X/Instagram İçerik Döngüsü Kurulum Runbook'u

> Durum: 2026-07-19 — kod merge edildi, tüm şalterler **default OFF** (fail-closed).
> Bu runbook'taki adımlar tamamlanmadan hiçbir şey yayınlanmaz.

## Mimari (60 saniyede)

```
[cron 4h] → kronos-runner container ──→ data/market/kronos_cascade.json
                                              │ (efloud_data volume)
[routines-watcher] → social_content rutini ───┤
   · 3 bot healthz (mid/long/scalp)           │
   · V1 pozisyon sayısı + signal_ledger       ▼
   · generators (EN+RU, deterministik) → compliance gate → content_drafts (DB)
                                              │ PENDING_REVIEW
[operatör] dashboard /api/social/pending → approve
                                              │ APPROVED
[publishing_worker (60s poll)] ──→ X (xurl) + Instagram (Graph API)
```

- Post tipleri rotasyonu (günde 6 slot): `market_update` (Kronos cascade) →
  `performance_recap` (filo durumu, **yüzdesiz/dolarsız**) → `educational`
  (SMC havuzu) → tekrar.
- Kronos verisi yok/bayat veya bir bot down ise slot **educational'a düşer** —
  döngü asla boş geçmez, asla down-bot duyurmaz.
- Her draft `scripts/content_compliance.find_violations` gate'inden geçer;
  ihlalli draft kuyruğa **girmez**, Telegram'a warning düşer.

## 1) VPS deploy

```bash
cd /opt/efloud-bot && git pull
# Kronos runner image'ı (torch CPU ~1.8GB — tek seferlik build)
docker compose -f docker-compose.prod.yml build kronos-runner
# routines-watcher'ı yeni rutinle yeniden başlat
docker compose -f docker-compose.prod.yml up -d --no-deps routines-watcher
```

`.env.production`'a ekle (başlangıç değerleri):

```bash
SOCIAL_CONTENT_ENABLED=1
SOCIAL_AUTOPILOT=0            # ilk hafta onaylı
SOCIAL_LANGS=en,ru
SOCIAL_PLATFORMS=x            # IG hazır olunca: x,instagram
KRONOS_SYMBOLS=BTC,ETH,SOL
```

Cron (host, `crontab -e`):

```cron
# Kronos cascade — 4 saatte bir, slot başından 20dk önce ısınsın
40 3,7,11,15,19,23 * * * cd /opt/efloud-bot && docker compose -f docker-compose.prod.yml run --rm kronos-runner >> /var/log/kronos-runner.log 2>&1
```

İlk koşu HuggingFace'ten ~500MB model indirir (`kronos_hf_cache` volume'unda
kalıcı). Doğrulama:

```bash
docker compose -f docker-compose.prod.yml run --rm kronos-runner
docker run --rm -v efloud-bot_efloud_data:/d alpine cat /d/market/kronos_cascade.json | head -30
docker logs efloud-routines --since 10m | grep social_content
```

## 2) X (Twitter) API kurulumu

1. https://developer.x.com → hesap aç, **Free tier** yeterli (yazma: 500
   post/ay — 4h döngü × EN+RU ≈ 360 post/ay, sınıra yakın; Basic tier
   düşünülebilir).
2. App oluştur → **User authentication settings**: Read and write, type: Web
   App. API Key/Secret + Access Token/Secret üret.
3. VPS'te `xurl` binary'si gerekir (bkz. `docs/runbooks/xurl-setup.md`):
   OAuth PIN akışı browser istediği için auth **lokalde** yapılır, token
   dosyası VPS'e taşınır.
4. `.env.production`:

```bash
X_API_ENABLED=true
X_API_KEY=...
X_API_SECRET=...
X_ACCESS_TOKEN=...
X_ACCESS_SECRET=...
```

5. Backend'i yeniden başlat; test: dashboard'dan bir draft'ı approve et,
   60 sn içinde `docker logs efloud-bot | grep "Published to x"`.

## 3) Instagram API kurulumu

1. Instagram hesabını **Professional (Business)** yap, bir Facebook Page'e
   bağla.
2. https://developers.facebook.com → App oluştur (Business tipi) →
   `instagram_basic`, `instagram_content_publish`, `pages_read_engagement`
   izinleri.
3. Graph API Explorer'dan **long-lived** (60 gün) token üret;
   `GET /me/accounts` → Page üzerinden `instagram_business_account.id` al.
4. `.env.production`:

```bash
INSTAGRAM_ENABLED=true
INSTAGRAM_BUSINESS_ACCOUNT_ID=1784...
FACEBOOK_ACCESS_TOKEN=EAAG...
SOCIAL_PLATFORMS=x,instagram
```

> **Not (Faz 2):** IG Graph API `image_url` olarak **public URL** ister.
> Şu an draft'lar metin-öncelikli; IG'yi açmadan önce görsel kartı üretimi +
> hosting (örn. `u2algo.com/social/<id>.png`) eklenmeli. O güne kadar
> `SOCIAL_PLATFORMS=x` bırak — IG hedefli draft'lar client inactive diye
> retry döngüsüne girer.
> **Token yenileme:** long-lived token 60 günde bir yenilenmeli (cron +
> `GET /oauth/access_token?grant_type=fb_exchange_token`).

## 4) Onaylı hafta → Autopilot

- İlk hafta: her 4 saatte Telegram'a "N draft hazır (onay bekliyor)" düşer.
  Dashboard → Social → pending listesi → approve/reject.
- İçerik kalitesine güvenince: `.env.production` → `SOCIAL_AUTOPILOT=1` +
  backend restart. Artık compliance'ı geçen draft'lar onaysız yayınlanır.
  (Compliance gate autopilot'ta da **her zaman** açık.)

## 5) Sorun giderme

| Belirti | Kontrol |
|---|---|
| Hiç draft üretilmiyor | `SOCIAL_CONTENT_ENABLED=1` mi? `docker logs efloud-routines \| grep social_content` |
| Hep educational post | Kronos JSON bayat (cron çalışıyor mu?) veya bir bot down (healthz) |
| Draft var, yayın yok | `X_API_ENABLED` + xurl auth; worker logları: `grep publishing_worker` |
| Aynı slot iki post | `state/social_content_state.json` silinmiş olabilir (slot-dedup anahtarı) |
| compliance warning'leri | Şablon değişikliği yapıldıysa `tests/social/test_generators.py` koş |
| DB yazılamıyor | Rutin `data/social_outbox.jsonl`'a düşer (içerik kaybolmaz), Telegram'a warning gelir |

## Dosya haritası

| Dosya | Rol |
|---|---|
| `scripts/kronos_service.py` | PLAYBOOK cascade'inin sunucu otomasyonu (3-koşu konsensüs) |
| `Dockerfile.kronos` + compose `kronos-runner` | Torch'lu izole runner image |
| `scripts/routines/social_content.py` | 4h rutin: topla → üret → gate → kuyruk |
| `backend/social/generators.py` | Deterministik EN/RU şablonlar (compliance-safe) |
| `backend/social/publishing_worker.py` | (mevcut) APPROVED → X/IG yayını |
| `.claude/skills/kronos/` | (mevcut) Kronos skill — Claude'dan manuel `/kronos` |
