# HERMES.md — Efloud-bot Operatör Kılavuzu

> Operatör/insan onay zinciri (Hermes) için. Yönetim kılavuzu.
> Tarih: 2026-10-02 | Master HEAD: `c8dc5c8` | Bot durumu: **CANLI**
> Son güncelleme: v2 AKTİF + BOS girişleri + acil bakiye HALTI kaldırıldı

---

## 1. Nedir Bu Bot?

**Efloud-bot**: Binance USDT-M futures üzerinde SMC doktriniyle otonom trade botu. Hetzner VPS 7/24, FastAPI dashboard + Telegram alert.

**Algoritma**: SMC v2 pullback+confirmation algoritması **CANLI ve AKTİF**.
- **v2 (RUNNING)**: CHoCH **ve BOS** kırılımları → kırılımı yapan OB/BB bölgesine
  geri çekilme bekle → engulfing teyidi → limit emir (SL likidite çizgisinde).
- **v1 (MUTED)**: v2'nin sahiplendiği sembollerde v1 sinyal girişleri susturulur
  (çift giriş / kırılım anında market emri önlenir).

**Hedef**: Forex (MT5/OANDA) pluggable exchange adapter.

---

## 2. Şu An Ne Durumda?

| Şey | Durum |
|---|---|
| **GitHub master** | `c8dc5c8` — BOS girişleri + acil bakiye HALTI kaldırıldı |
| **VPS HEAD** | `c8dc5c8` (deploy edildi, bot sağlıklı) |
| **Bot container** | Hetzner VPS'te `Up (running)` — v2 ile trade ediyor |
| **Production dry_run** | `false` (CANLI MAINNET) |
| **Mainnet guard** | `EFLOUD_ALLOW_MAINNET=1` (env'de) |
| **AUTOSTART** | `0` — manuel Start gerektirir (incident-recovery posture) |
| **Açık pozisyonlar** | Dashboard'dan kontrol et: `https://2-28-139-82.nip.io` |
| **v2 flag durumu** | `smc_version=v2`, `smc_v2_symbols=[BTC,ETH,XRP,DOGE,SOL,...]`, `smc_v2_shadow=false` → **AKTİF (CANLI EMİR)** |
| **Acil bakiye HALTI** | `emergency_balance_threshold=0` → **KALDIRILDI** (2026-10-01 operatör kararı) |
| **Volatil rejim** | `allow_volatile_entries=true` → volatil piyasada girişler açık |

---

## 3. Hermes Rol Tanımı (CLAUDE.md §3)

**Hermes yapar** (insan):
- VPS SSH, `docker compose up -d`, `backend.migrate up`.
- `configs/config.phase2_1k.yaml` risk/safety/mainnet edit.
- PR sign-off, prod merge onayı.
- Incident response (canlı müdahale).
- Mainnet aç/kapa, leverage/sizing değişim.

**Claude yapar**:
- Kod, test, refactor öneri.
- PR hazırlığı.
- Backtest analizi, log değerlendirme.
- Docs, spec, plan.

**YASAK**:
- `EFLOUD_ALLOW_MAINNET=1` + `dry_run: false` kontrolsüz deploy.
- Compose/env değişiminde sadece `docker restart` (recreate gerekir).
- Risk/safety değişimi test/backtest olmadan mergeleme.
- Çoklu konuyu tek PR'da karıştırma.

---

## 4. Mimari Hızlı Tur

```
main.py                              ← entry point
  └── SafeOrchestrator               ← analiz + safety katmanı
        ├── BinanceClient            ← CCXT futures wrapper
        ├── OrderManager             ← entry + SL + TP1 + TP2 yerleştirme
        ├── SMC engine               ← FVG, OB, swings, equal levels
        ├── Regime detector          ← TRENDING/RANGING/VOLATILE
        ├── Confluence scoring       ← multi-TF + daily filter
        ├── PositionLifecycle        ← yaşayan pozisyon yönetimi
        ├── Circuit breaker          ← daily/weekly loss limit
        ├── PositionGuard            ← size, exposure, holding hours
        └── SetupStateStore (v2)     ← pullback candidate state machine
```

**Kritik dosyalar**:
| Sembol | Yer |
|---|---|
| Live entry point | `main.py` |
| FastAPI server | `backend/main.py` (port 8080) |
| Container start | `docker-compose.prod.yml` |
| Config | `configs/config.phase2_1k.yaml` |
| Migrations | `backend/migrations/001..008_*.sql` |
| Backtest CLI | `python -m backtest.cli {single,portfolio,grid,compare}` |
| v1 signal logic | `engine/signals.py` |
| v2 trigger (CHoCH+BOS) | `engine/smc_v2/triggers.py` |
| v2 entry helper | `engine/safe_orchestrator.py:_place_v2_entry_order` |
| v2 pure modules | `engine/smc_v2/` |

---

## 5. SMC v2 Pipeline — Durum

### 5a. Tarihçe (özet)

SMC v2 pipeline 15 PR ile merge edildi (2026-05-23 → 2026-05-24, #63-#77):
pure modules (zones/sl_calc/tp_calc), SetupStateStore, confirm_entry (LTF
engulfing), select_htf_swing_anchor, trigger phase, entry order placement,
backtest harness, config flag + shadow mode.

### 5b. Bugün canlıda (2026-10-02)

v2 **AKTİF ve CANLI EMİR veriyor**:
1. `configs/config.phase2_1k.yaml` → `engine.smc_version=v2` → SetupStateStore aktif.
2. `engine.smc_v2_symbols=[BTC/USDT, ETH/USDT, XRP/USDT, DOGE/USDT, SOL/USDT, ...]` → whitelist dolu.
3. `engine.smc_v2_shadow=false` → gerçek emir yerleştiriliyor.

**Giriş akışı (CHoCH + BOS)**:
```
LTF (15m) CHoCH/BOS kırılımı
  → HTF bias uyumu (BULL/BEAR)
  → kırılımı yapan OB/BB bölgesi (veya FVG/OTE fallback)
  → SetupCandidate(state=AWAITING_PULLBACK)
  → fiyat bölgeye geri çekilir (retest)
  → engulfing teyidi (require_confirmation=true)
  → CONFIRMED → limit emir
  → SL: likidite çizgisi (kırılım öncesi swing) ötesinde
```

**v1 susturma**: v2'nin sahiplendiği sembollerde v1 sinyal girişleri
`_v2_entry_active()` ile susturulur — kırılım anında market emri girilmez.

### 5c. Son operatör revizyonları (2026-10-01/02)

| Tarih | Değişiklik | Commit |
|---|---|---|
| 2026-10-02 | BOS kırılımları da setup üretiyor (CHoCH ile aynı pullback akışı) | `658a905` |
| 2026-10-01 | Acil bakiye HALTI kaldırıldı (emergency_balance_threshold=0) | `b2154c5` |
| 2026-10-01 | v1 MARKET girişi v2 canlı sembolde susturuldu | `b2154c5` |
| 2026-10-01 | Bölge aşım toleransı 0.5→2.0 ATR | `228382d` |
| 2026-10-01 | Volatil rejim girişleri açıldı (allow_volatile_entries=true) | `228382d` |

---

## 6. Deploy Senaryosu — Adım Adım

### Deploy (güncel akış)

```bash
ssh root@2.28.139.82
cd /opt/efloud-bot
git pull --ff-only                              # master'ı çek
bash deploy/deploy.sh                           # build + recreate + healthcheck
```

**Deploy sonrası** (AUTOSTART=0 olduğu için):
```bash
# Login + bot start (dashboard API üzerinden)
PW=$(grep DASHBOARD_PASSWORD /opt/efloud-bot/.env.production | cut -d= -f2-)
curl -sk -c /tmp/c.txt -X POST https://2-28-139-82.nip.io/api/login \
  -H "Content-Type: application/json" -d "{\"password\":\"$PW\"}"
curl -sk -b /tmp/c.txt -X POST https://2-28-139-82.nip.io/api/bot/start \
  -H "Content-Type: application/json" -d "{}"
rm -f /tmp/c.txt
```

**Breaker reset** (HALTED ise):
```bash
curl -sk -b /tmp/c.txt -X POST "https://2-28-139-82.nip.io/api/breaker/reset?reason=operator+reset"
```

**Rollback**:
```bash
git -c safe.directory=/opt/efloud-bot reset --hard <önceki-commit>
bash deploy/deploy.sh
```

**Deploy öncesi kontrol**: açık pozisyon var mı? (Binance positionRisk — deploy
sırasında bot durur, pozisyon yönetimi birkaç cycle aksar.)

---

## 7. Sık Karşılaşılan Operasyonlar

### Container kontrolü
```bash
docker ps | grep efloud-bot              # Up mu?
docker logs efloud-bot --tail 100        # son loglar
docker exec efloud-bot ls /app/state     # state
```

### Migration çalıştır
```bash
docker exec efloud-bot python3 -m backend.migrate up
```

### Config değişimi
```bash
vi /opt/efloud-bot/configs/config.phase2_1k.yaml

# YAML parse test
docker exec efloud-bot python3 -c "import yaml; yaml.safe_load(open('/app/configs/config.phase2_1k.yaml'))"

# Recreate
bash /opt/efloud-bot/deploy/deploy.sh
```

### Compose env değişimi
```bash
docker compose -f docker-compose.prod.yml up -d   # recreate
```

### Kill switch (acil durdurma)
```bash
docker compose -f docker-compose.prod.yml stop efloud-bot
```

### Shadow log incelemesi (yalnız shadow modunda — şu an v2 canlı, log boş olabilir)
```bash
# Tail
docker exec efloud-bot tail -f /app/logs/smc_v2_shadow.log

# Sinyal sayısı
docker exec efloud-bot wc -l /app/logs/smc_v2_shadow.log
```

### Veritabanı sorguları
```bash
docker exec efloud-bot python3 -c "
import asyncio, asyncpg, os, json
async def main():
    pool = await asyncpg.create_pool(os.environ['DATABASE_URL'])
    rows = await pool.fetch('SELECT symbol, direction, entry, exit, pnl_usdt, entry_setup_source, tp1_target_type FROM trades ORDER BY opened_at DESC LIMIT 10')
    for r in rows: print(dict(r))
asyncio.run(main())
"
```

---

## 8. Tehlike Sinyalleri (Olursa Hemen Bildir)

1. **`healthz` 503** → Bot internal hata, autoheal restart loop riski.
2. **Circuit breaker HALTED** → Haftalık DD veya ardışık kayıp limiti aşıldı, trade durdu. (Acil bakiye HALTI kaldırıldı — `emergency_balance_threshold=0`.)
3. **`record_trade_open failed`** → Migration eksik, db table uyuşmazlığı.
4. **Orphan SL/TP** → `reduceOnly` order Binance'te kalmış, poz kapalı.
5. **`v1 signal suppressed` logu hiç gelmiyor** → v2 sembol sahipliği bozuldu, çift giriş riski.
6. **v1 vs v2 zıt sinyal**.
7. **State'te `tp2: 0.0`**.
8. **`order_manager.repair_missing_sl`** → SL placement exhaust edildi, reconcile tamir ediyor. Sık olursa API/retry mantığı araştırılmalı.
9. **`order_manager.be_sl_placement_failed`** → TP1-hit sonrası breakeven SL 3 denemede başarısız. Pozisyon SL'siz bekliyor, reconcile kurtaracak — ama izlenmeli.

---

## 9. Erişim Bilgileri

| Şey | Yer |
|---|---|
| Dashboard | `https://2-28-139-82.nip.io` |
| Dashboard şifre | Password manager |
| VPS SSH | `ssh root@2.28.139.82` |
| SSH key | `~/.ssh/id_ed25519` (`efloud-bot-hetzner`) |
| Repo | `/opt/efloud-bot` |
| State dir | `/opt/efloud-bot/state_1k/` |
| Log dir | `/app/logs/` (container) |
| Telegram | `EFLOUD_TELEGRAM_TOKEN` + `EFLOUD_TELEGRAM_CHAT_ID` |
| Postgres | `DATABASE_URL` (Supabase pooler) |

---

## 10. Claude'a Hangi Konularda Soru Sor

**Sor**:
- Shadow log yorumlama.
- Backtest analiz (`comparison.json` at).
- Yeni feature spec/plan taslak.
- Kod/PR review.
- Bug repro/fix.
- Memory açıklamaları.

**Sorma** (operatör işi):
- Production deploy / restart.
- Config / mainnet edit.
- VPS terminal komut çalıştırma.
- Manuel pozisyon kapama.

---

## 11. Acil Durum Akışı

**Senaryo**: Bot anormal çalışıyor (hatalı emir, kontrolsüz state, limit aşımı).

```bash
# 1. Acil durdur
docker compose -f docker-compose.prod.yml stop efloud-bot

# 2. Binance UI pozisyon kontrol et (SL/TP manuel koy / kapat)

# 3. State backup al
docker exec efloud-bot tar -czf /tmp/state_backup_$(date +%s).tar.gz /app/state_1k
docker cp efloud-bot:/tmp/state_backup_*.tar.gz ./

# 4. Log dök
docker logs efloud-bot --since 4h > emergency_$(date +%s).log

# 5. Claude'a at: log + state + durum özeti
```

---

## 12. Bu Doküman + İlgili Referanslar

- `CLAUDE.md`: Proje bellek, kural, mimari.
- `HERMES.md`: Operatör kılavuzu (bu dosya).
- `docs/runbooks/`: operasyon runbook'ları (breaker-reset, on-call, disaster-recovery...).
- `skills/social-publishing/SKILL.md`: Sosyal medya pipeline'ı — tüm AI modellerinin okuyabileceği kalıcı doküman.
- `MAINNET_DEPLOY_GUIDE.md` + `HETZNER_DEPLOYMENT_CHECKLIST.md`: kurulum ve deploy.
- `RISK_MAP.md`: risk haritası.

## 13. Sosyal Medya Yayın Pipeline'ı (YENİ — 2026-07-26)

Bot sinyallerini otomatik chart + video + caption olarak X, Instagram, YouTube'da
paylaşmaya hazırlar. **Varsayılan duruş: hiçbir şey yayınlanmaz.** Üç bağımsız
güvenlik kapısı var.

### Tek komutla çalıştırma

```bash
cd /opt/efloud-bot
python -m scripts.daily_social_run --date "$(date -u +%F)"
```

### Pipeline Zinciri

```
Lane A (bot)  → ContentJobEmitter (JSONL)            engine/content_jobs.py
Lane B        → analiz artifact                       scripts/lane_b_consumer.py
Lane C        → compliance-gated caption + levels      scripts/lane_c_copywriter.py
Lane D        → markalı chart PNG (ENTRY/SL/TP)       scripts/chart_render.py
Lane G        → per-platform bundle + MP4 klip        scripts/lane_g_social.py
Lane G pub    → onaylı bundle → platform dispatch      scripts/lane_g_publish.py
```

### Üç güvenlik kapısı (hepsi default KAPALI)

1. **Onay kapısı** — `--auto-approve` verilmezse tüm bundle'lar `pending_review`
2. **Live kapısı** — `--live` verilmezse yayın dry-run
3. **Platform flag'leri** — `X_API_ENABLED`, `INSTAGRAM_ENABLED`, `YOUTUBE_ENABLED`

Üçü de açılmadan dışarıya TEK BİT veri çıkmaz.

### Medya formatları

| Platform | Medya | Geometri |
|---|---|---|
| X | Still PNG | 1080×1350 |
| Instagram | Still PNG | 1080×1350 |
| Reels | Vertical MP4 | 1080×1920 |
| YouTube Shorts | Vertical MP4 | 1080×1920 |

Video backend: **ffmpeg** (default, pixel-exact, ücretsiz). Higgsfield opt-in
ama fiyat etiketlerini bozduğu için sinyal chart'larında KULLANILMAZ.

### Cron (sadece üretim, yayın yok)

```
0 * * * * cd /opt/efloud-bot && python -m scripts.daily_social_run --date "$(date -u +%F)" >> /app/logs/social.log 2>&1
```

### Bug fix'ler (bu güncelleme ile)

- Instagram: `render_promo_card` import hatası → her paylaşım ImportError (düzeltildi)
- YouTube: `video_path=None` hardcoded → Shorts'a video yüklenemiyordu (düzeltildi)

### Detaylı doküman

`skills/social-publishing/SKILL.md` — tüm modüller, API'ler, testler, cron pattern'leri.

**Bot canlı, kararlı, kod %100 hazır. Acele yok, risk yok.**
