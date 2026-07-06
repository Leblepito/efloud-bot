# Handoff — 2026-07-06: DNS fix, emergency threshold 450, chain redesign, scalp -2015, breaker reset akışı

> Kaynak oturumlar: 2026-07-05/06 operatör oturumu (VPS ops) + 2026-07-06 remote
> devam oturumu (Pine/doc senkronu, bu commit'in bulunduğu branch).
> Canlı filo: **mid** = `efloud-bot` (bot.u2algo.com) · **long** = `efloud-bot-long`
> (v2.u2algo.com) · **scalp** = `efloud-bot-scalp` (scalp.u2algo.com) — hepsi
> Hetzner VPS, docker compose, Caddy + Let's Encrypt HTTPS.

## 1. Manus DNS fix — panel↔zone senkron kopması

- Belirti: `u2algo.com` alt alan kayıtları Manus panelinde görünüyor ama zone'a
  yansımıyor (veya tersi) — panel ile gerçek DNS zone arasındaki senkron
  kopabiliyor.
- Çözüm (tekrarlanabilir): sorunlu kaydı Manus panelinde **SİL + YENİDEN EKLE**.
  Düzenleme (edit) senkronu tetiklemiyor; sil+ekle tetikliyor.
- Kalıcı not memory'de: `manus-dns-panel-quirks`.

## 2. `emergency_balance_threshold` 900/1000 → 450 (commit `73688c5`)

- Kök neden: 2026-07-05 wallet-split'ten (long+scalp cüzdanları ~$500'er) sonra
  eski eşikler ($1000 long / $900 scalp) kalıntı kaldı → scalp start anında
  "bakiye eşiğin altında" diye **HALT** ediyordu (false positive).
- Fix: her iki config'te eşik **450** (= $500 cüzdana göre ~%10 kayıp payı).
  Dosyalar: `configs/config.phase2_long_1k.yaml`, `configs/config.phase2_scalp_1k.yaml`
  (+ preflight yorum satırları senkron).
- Ders: cüzdan boyutu değişen HER operasyonda `safety:` bloğundaki mutlak-dolar
  eşikleri (`emergency_balance_threshold`, daily/weekly limit yorumları) birlikte
  gözden geçirilmeli.

## 3. Timeframe chain redesign (commit `3c96029`)

- Kök neden: scalp ~10 saat hiç sinyal üretmedi. Eski scalp chain'i 5m/1h/**12h**
  idi — 12h HTF, 5m giriş için atıl (bias nadiren hizalanır, 12h zone'lar 5m
  girişe göre devasa).
- Yeni merdiven (tek kaynak `data/timeframes.py` `PROFILES`; entry / SMC-yapı / trend):

  | Profil | Entry | MTF (SMC-yapı) | HTF (trend) |
  |---|---|---|---|
  | scalp | 5m | 1h | 4h |
  | mid | 15m | 4h | 12h |
  | long | 1h | 8h | 1d |

- Testler: `backend/tests/test_timeframe_profiles.py` (15 passed) — profil
  pinleri + weekly kline-cap (custom 1w ile korundu) + long-1d kline_limit 500.
- Bu oturumda tamamlanan follow-up: Pine profil senkronu —
  `pine/efloud_signals.pine` + `pine/efloud_strategy.pine` mapping (scalp htf
  720→240, mid mtf 60→240 / htf 240→720, long htf W→D) + dashboard `chainStr`
  + `pine/PINE_SPEC.md` §17 changelog. **Açık iş:** TradingView'de sıfır-hata
  derleme + `pine_save` (MCP remote oturumdan erişilemedi; §17'de checklist).
  DİKKAT: kullanıcının kendi `u2Algo_FVG-OTE` script'ine dokunma.

## 4. Scalp Binance `-2015` API izni çözümü

- Belirti: scalp instance start'ında Binance `-2015` ("Invalid API-key, IP, or
  permissions for action") — yeni scalp cüzdanının API key'i reddediliyordu.
- Çözüm (Binance tarafı, operatör): yeni key'de **Futures trade izni** aktif
  edildi ve **VPS IP'si key'in IP-whitelist'ine** eklendi; sonrasında preflight
  `canTrade=true` ile geçti. (Kod değişikliği yok — saf hesap-konfigürasyon işi.)
- Ders: her yeni cüzdan/key açılışında preflight'tan ÖNCE kontrol listesi:
  Futures izni ✓, IP whitelist (VPS IP) ✓, ONE-WAY position mode ✓, hesap flat ✓.

## 5. Circuit-breaker reset akışı (dashboard'da buton YOK)

- Breaker TRIPPED/HALTED durumundan operatör onayıyla dönüş **sadece API** ile:
  `POST /api/breaker/reset` (auth zorunlu; `backend/api.py:369`, disk-otoriter
  hardening'li). Dashboard'da reset butonu bilinçli olarak YOK — mainnet'te
  "tek tık" reset istemiyoruz.
- Örnek (VPS'te; PowerShell'den çağırırken dış tırnak TEK tırnak):
  `curl -X POST -H 'Authorization: Bearer <TOKEN>' https://scalp.u2algo.com/api/breaker/reset`
- Not: mid 2026-07-05'te günlük-zarar korumasıyla TRIPPED oldu; günlük breaker
  UTC gün dönümünde otomatik RESUME eder — otomatik dönmediyse yukarıdaki
  endpoint kullanılır.

## 6. Operasyon hatırlatmaları (değişmedi, teyit)

- Deploy zinciri: local push → VPS `git pull --no-edit` →
  `docker compose -f docker-compose.prod.yml build efloud-bot` (image TEK;
  long/scalp aynı image) → `up -d --force-recreate <containerlar>`.
  Config'ler image'a gömülü — **restart yetmez, build şart**.
- VPS deploy key READ-ONLY (push edemez; local commit birikmesi normal).
- `config_drift` exit-1 analizi (2026-07-06): exit 1 drift'ten GELMEZ (drift
  sadece warn alert üretir, `ok=True` döner) — tek yol `/api/config` fetch
  hatası (`config_drift.py` run(); rutinin bağlamında `EFLOUD_API_BASE_URL` /
  `DASHBOARD_PASSWORD` kontrol edilmeli). Ayrıca baseline yanlıştı: root
  `config.yaml` yerine artık `EFLOUD_CONFIG_PATH` (instance'ın gerçek config'i)
  kıyaslanıyor — bu oturumda fix'lendi (TDD, tests/routines/test_config_drift.py).
- Sandbox git kuralı: `GIT_INDEX_FILE=/tmp/...` pattern'ı (bkz.
  `2026-07-03-merge-bugfix-and-repo-hardening.md`).

## 7. Açık işler (sonraki oturum)

1. TradingView derleme + save (bkz. §3 / PINE_SPEC §17 checklist).
2. `signal_ledger` genişletme önerisi: `EFLOUD_SIGNAL_LEDGER_ENABLED=1` şu an
   sadece mid'de; scalp+long `.env.production.*` dosyalarına eklenmesi operatör
   onayı bekliyor (18 Temmuz C4/M1/M2 kalibrasyonu n≥30 sinyal istiyor — üç bot
   beslerse veri daha hızlı birikir).
3. Scalp'in yeni chain'de (5m/1h/4h) candidate/trade üretiminin teyidi
   (heartbeat: `docker logs efloud-bot-scalp` içinde "Scanning symbol universe"
   her 5 dk'da bir).
4. `www.u2algo.com` Railway custom-domain doğrulaması (200 bekleniyor; 404 ise
   Railway → u2algo-site → Settings → www satırında re-check).
5. `pine/publish/efloud_signals_v2_en.pine` (+ `PUBLISH_efloud_signals.md`) hâlâ
   ESKİ merdiveni taşıyor (scalp htf 720, long W) — TradingView'de yeniden
   yayınlanırken yeni mapping'le senkronlanmalı (bilinçli olarak bu diff'te
   dondurulmuş publish snapshot).
6. Eski-merdiven YORUM kalıntıları (kod değil): `configs/config.phase2_scalp_1k.yaml`
   başlığı, `docker-compose.prod.yml:37`, `.claude/skills/kronos/PLAYBOOK.md:60` —
   escalation-path dosyaları olduğundan ops-review'lu ayrı batch'te düzeltilecek.
