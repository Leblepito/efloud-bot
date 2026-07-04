# HERMES.md — Efloud-bot Operatör Kılavuzu

> Bu dosya **Hermes** (operatör/insan onay zinciri) için yazılmıştır. Projeyi
> sıfırdan anlayıp güvenle yönetebilmen için tek bakışta her şeyi içerir.
> Tarih: 2026-05-24 | Master HEAD: `3fa88b8` | Bot durumu: **CANLI**

---

## 1. Nedir Bu Bot?

**Efloud-bot** = Binance USDT-M futures'ta Smart Money Concepts (SMC) doktriniyle
otonom çalışan trade bot'u. Hetzner VPS'te 7/24, FastAPI dashboard + Telegram alert.

**Bugünkü algoritma**: 2 kuşak paralel hazır.
- **v1** (RUNNING): mevcut SMC entry/SL/TP — şu an canlıda kullanılıyor
- **v2** (HAZIR, INERT): yeniden tasarlanmış pullback+confirmation algoritması — kod merge'lendi, prodüksiyonda dormant

**Yarın hedef**: forex (MT5/OANDA) için pluggable exchange adapter (henüz scope dışı).

---

## 2. Şu An Ne Durumda?

| Şey | Durum |
|---|---|
| **GitHub master** | `3fa88b8` — SMC v2 pipeline 15/15 PR merged |
| **VPS HEAD** | **Bilinmiyor — Hermes pull yapana kadar belirsiz** (muhtemelen hâlâ `d03857c`) |
| **Bot container** | Hetzner VPS'te `Up (running)` — v1 ile trade ediyor |
| **Production dry_run** | `false` (CANLI MAINNET) |
| **Mainnet guard** | `EFLOUD_ALLOW_MAINNET=1` (env'de) |
| **AUTOSTART** | `0` — manuel Start gerektirir (incident-recovery posture) |
| **Açık pozisyonlar** | Dashboard'dan kontrol et: `https://bot.ualgotrade.com` |
| **v2 flag durumu** | Default: `smc_version=v1`, `smc_v2_symbols=[]`, `smc_v2_shadow=false` → **INERT** |

---

## 3. Hermes Rol Tanımı (CLAUDE.md §3)

**Sen yaparsın** (Claude değil):
- VPS SSH + `docker compose up -d` + `backend.migrate up`
- `config.yaml` risk/safety/mainnet edit'leri
- PR sign-off + production merge onayı
- Incident response (canlıya müdahale)
- Mainnet aç/kapa, leverage/sizing değişikliği

**Claude yapar** (sen değil):
- Kod yazma, test, refactor önerisi
- PR hazırlama (push + PR open)
- Backtest analizi, log değerlendirmesi
- Docs, spec, plan

**Asla yapma**:
- `EFLOUD_ALLOW_MAINNET=1` set edip `dry_run=false` bırakıp deploy etme
- `docker-compose.prod.yml` env değişikliğinde sadece `docker restart` (recreate gerekir)
- Risk/safety değişikliğini backtest'siz + test'siz mergelama
- Birden fazla concern'i tek PR'a karıştırma

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
        └── SetupStateStore (NEW v2) ← pullback candidate state machine
```

**Kritik dosyalar**:
| Sembol | Yer |
|---|---|
| Live entry point | `main.py` |
| FastAPI server | `backend/main.py` (port 8080) |
| Container start | `docker-compose.prod.yml` |
| Config | `config.yaml` |
| Migrations | `backend/migrations/001..008_*.sql` |
| Backtest CLI | `python -m backtest.cli {single,portfolio,grid,compare}` |
| v1 signal logic | `engine/signals.py` |
| v2 entry helper | `engine/safe_orchestrator.py:_place_v2_entry_order` |
| v2 pure modules | `engine/smc_v2/` |

---

## 5. SMC v2 Pipeline — Ne Yapıldı, Ne Bekliyor

### 5a. 15 PR merge'lendi (2026-05-23 → 2026-05-24)

| PR | Numara | SHA | Ne yaptı |
|---|---|---|---|
| #C1 | #63 | `631513d` | Orphan reduceOnly SL/TP1/TP2 cleanup helper |
| #S1 | #65 | `466f98a` | Pure modules: zones/sl_calc/tp_calc/exceptions + liquidity_pools |
| #S2a | #66 | `298bf37` | SetupStateStore (atomic persistence + corruption recovery) |
| #S2b | #67 | `5094827` | Orchestrator state-tick wiring (inert opt-in via store=None) |
| #S3a | #68 | `29eadb1` | `confirm_entry` (LTF engulfing) + `select_htf_swing_anchor` |
| #S3b | #69 | `0f88588` | Real confirm_entry wiring + `df_15m` plumbing |
| #S3c-1 | #70 | `dd79a26` | Trigger phase + `_emit_setup_candidates` |
| #S3c-2 | #71 | `c7bee03` | Entry order placement + v1-parity safety gates (RISK-OPS CRITICAL) |
| #S4 | #72 | `14ce7cf` | Backtest harness `compare` (v1 vs v2 + gates) |
| #S5 | #73 | `be1d135` | Lifecycle telemetry (4 fields) + single-target partial_close branch |
| #S5.5 | #74 | `b8a1568` | `tp2: Optional[float]` widening + migration 008 + orphan SL cleanup wiring |
| #S5.6 | #75 | `7ad0c74` | State-reload coercion fix + notifications None-safe |
| #S6 | #76 | `cdd01c5` | Config flag + dry-run shadow mode |
| #S6.5 | #77 | `3fa88b8` | `tp2=None` rejection removal — single-target accepted |

### 5b. 3-katmanlı inert garanti (bugün canlıda)

v2 hiçbir gerçek emir vermez çünkü:

1. `config.yaml engine.smc_version=v1` → main.py `_build_setup_state_store` None döner → `SafeOrchestrator.setup_state_store=None` → `_place_v2_entry_order` asla çağrılmaz
2. `config.yaml engine.smc_v2_symbols=[]` → whitelist tüm sembolleri reddeder
3. `config.yaml engine.smc_v2_shadow=false` → (sadece üst 2 bypass edilirse devreye girer)

**Minimum 3 elle config edit gerektirir** v2'nin canlı emir verebilmesi için.

### 5c. Pending

- **Production deploy** (zero-risk — defaults inert)
- **Shadow aktivasyon** (1 hafta paralel gözlem)
- **Baseline backtest** (6 aylık gerçek OHLCV)
- **PR #S7**: 3-faz prod rollout (ETH+BTC → +5 mid-cap → all 20)

---

## 6. Deploy Senaryosu — Adım Adım

### Adım 1 — Zero-risk deploy (BUGÜN yapılabilir)

```bash
ssh efloud-bot
cd /opt/efloud-bot
git fetch origin
git log -1 --oneline                              # mevcut HEAD nedir?
git -c safe.directory=/opt/efloud-bot pull        # → 3fa88b8'e gelmeli
docker compose -f docker-compose.prod.yml up -d   # recreate (config değişirse zorunlu)
docker logs efloud-bot --tail 100                 # startup'ı izle
curl -s localhost:8080/api/healthz                # 200 bekle
```

**Davranış değişikliği YOK** — defaults v1 inert. Bot v1 ile trade etmeye devam eder.

**1 saat gözle**:
- `https://bot.ualgotrade.com` → healthz yeşil
- Mevcut açık pozisyonlar (varsa) yönetilmeye devam ediyor
- Telegram alert'ler geliyor
- Circuit breaker tetiklenmedi

**Eğer bir şey ters giderse**:
```bash
git -c safe.directory=/opt/efloud-bot reset --hard d03857c
docker compose -f docker-compose.prod.yml up -d
```

### Adım 2 — Shadow aktivasyon (sessiz pencereyi bekle)

```bash
# config.yaml düzenle (lokalde edit + scp, veya VPS'te vi)
# engine bloğunu güncelle:
```

```yaml
engine:
  smc_version: v2                # v1 → v2
  smc_v2_symbols: ["*"]          # tüm semboller
  smc_v2_shadow: true            # ⚠️ TRUE kalmalı — false yaparsan CANLI EMİR VERİR
```

```bash
docker compose -f docker-compose.prod.yml up -d   # config değişimi → recreate ZORUNLU
docker exec efloud-bot tail -f /app/logs/smc_v2_shadow.log
```

**Beklenen**: v1 hâlâ canlı emir veriyor, v2 paralel hayalî sinyal hesaplayıp dosyaya JSON yazıyor. Hiç gerçek emir gitmez.

**7 gün gözlem**:
- Günlük: `wc -l /app/logs/smc_v2_shadow.log` (sinyal sayısı)
- Günlük: son 10 satır oku → direction, entry, sl, tp1, tp2 mantıklı mı
- v1 trade'lerle karşılaştır
- Log dosyasını Claude'a paylaş → analiz raporu hazırlar

**Rollback** (shadow'da sorun yok aslında — log only, ama config'i geri almak istersen):
```yaml
engine:
  smc_version: v1
  smc_v2_symbols: []
  smc_v2_shadow: false
```
```bash
docker compose -f docker-compose.prod.yml up -d
```

### Adım 3 — Baseline backtest (Shadow ile paralel)

```bash
# Önce OHLCV cache'i hazırla (VPS'te veya lokalde)
python -m scripts.prefetch_data \
  --symbols ETH/USDT,BTC/USDT,SOL/USDT,BNB/USDT,ADA/USDT,LINK/USDT,AVAX/USDT \
  --period-days 180

# Comparison koştur
python -m backtest.cli compare \
  --symbols ETH/USDT,BTC/USDT,SOL/USDT,BNB/USDT,ADA/USDT,LINK/USDT,AVAX/USDT \
  --period-days 180 \
  --config configs/config.phase2_1k.yaml
```

Çıktı: `reports/backtests/<date>_compare_7sym_180d_<runid>/comparison.json`

**Gate sonuçları**:
- `win_rate`: ≥ v1 (hard reject < v1×0.95)
- `avg_realized_rr`: ≥ 1.5 absolute (hard reject < 1.2)
- `max_drawdown_pct`: ≤ v1 (hard reject > v1×1.1)
- `stop_hunt_rate`: < v1×0.5 (hard reject ≥ v1)
- `sharpe_like`: ≥ v1 (hard reject < v1×0.9)

**Karar matrisi**:
- Tümü `pass` → S7'ye geç
- Herhangi biri `hard_reject` → v2 redesign (Claude'a bildir, spec revize)
- Bazıları `warn` → shadow gözlem süresini uzat

### Adım 4 — PR #S7 (3-faz prod rollout)

**Phase 1** (1 hafta, ETH + BTC):
```yaml
engine:
  smc_version: v2
  smc_v2_symbols: ["ETH/USDT", "BTC/USDT"]
  smc_v2_shadow: false              # 🔴 CANLI EMİR
```
```bash
docker compose -f docker-compose.prod.yml up -d
```

**Per-phase rollback kriteri** (manuel, otomatik değil):
- 3 ardışık losing trade VEYA
- Cumulative phase PnL ≤ -2%
- → `smc_version: v1` flip + recreate

**Phase 2** (1 hafta): `+ SOL, BNB, ADA, LINK, AVAX`
**Phase 3** (sürekli): tüm 20 sembol

---

## 7. Sık Karşılaşılan Operasyonlar

### Container kontrolü
```bash
docker ps | grep efloud-bot              # Up mu?
docker logs efloud-bot --tail 100        # son loglar
docker logs efloud-bot --since 1h        # son 1 saat
docker exec efloud-bot ls /app/state     # state dosyaları
```

### Migration çalıştır
```bash
docker exec efloud-bot python3 -m backend.migrate up
# Çıktı: schema_migrations'a hangi dosyaları uyguladı
# 008_tp2_nullable.sql çalıştığını gör
```

### Config değişimi
```bash
# Lokalde edit
vi /opt/efloud-bot/config.yaml

# YAML parse test (yanlış indent → bot crash)
docker exec efloud-bot python3 -c "import yaml; yaml.safe_load(open('/app/config.yaml'))"

# Recreate ZORUNLU (restart yetmez)
docker compose -f docker-compose.prod.yml up -d
```

### Compose env değişimi
```bash
# .env dosyası değişti veya docker-compose.prod.yml env: bloğu
docker compose -f docker-compose.prod.yml up -d   # recreate
# docker restart YETMEZ — env değişikliği container'ı recreate gerektirir
```

### Kill switch (acil durdurma)
```bash
docker compose -f docker-compose.prod.yml stop efloud-bot
# Restart için: docker compose ... start efloud-bot
# autoheal devre dışı bırakmak için: AUTOSTART=0 .env'de
```

### Shadow log incelemesi
```bash
# Tail
docker exec efloud-bot tail -f /app/logs/smc_v2_shadow.log

# Toplam sinyal
docker exec efloud-bot wc -l /app/logs/smc_v2_shadow.log

# Sembol dağılımı
docker exec efloud-bot sh -c "cat /app/logs/smc_v2_shadow.log | python3 -c \"import json,sys; from collections import Counter; print(Counter(json.loads(l)['symbol'] for l in sys.stdin))\""

# Son 10 sinyali pretty-print
docker exec efloud-bot sh -c "tail -10 /app/logs/smc_v2_shadow.log | python3 -m json.tool --json-lines"
```

### Veritabanı sorguları
```bash
# Son 10 trade
docker exec efloud-bot python3 -c "
import asyncio, asyncpg, os, json
async def main():
    pool = await asyncpg.create_pool(os.environ['DATABASE_URL'])
    rows = await pool.fetch('SELECT symbol, direction, entry, exit, pnl_usdt, entry_setup_source, tp1_target_type FROM trades ORDER BY opened_at DESC LIMIT 10')
    for r in rows: print(dict(r))
async def main():
    pool = await asyncpg.create_pool(os.environ['DATABASE_URL'])
    rows = await pool.fetch('SELECT symbol, direction, entry, exit, pnl_usdt, entry_setup_source, tp1_target_type FROM trades ORDER BY opened_at DESC LIMIT 10')
    for r in rows: print(dict(r))
asyncio.run(main())
"
```

---

## 8. Tehlike Sinyalleri (Olursa Hemen Bildir)

1. **`healthz` 503 dönüyor** → bot internal hata, autoheal restart loop riski
2. **Circuit breaker HALTED** → kayıp eşiği aşıldı, bot trade durdurdu
3. **`record_trade_open failed: column ... does not exist`** → migration çalışmamış, deploy ordering hatası
4. **Binance'te orphan reduceOnly order var ama Position kapalı** → PR #C1 helper çalışmadı, manuel iptal gerekebilir
5. **Shadow log'da `would_execute: true` var** → KOD BUG, shadow gate atlanmış, hemen Claude'a bildir
6. **v1 ve v2 aynı sinyal için ZIT yön veriyor** → manuel inceleme gerekli
7. **State file'da `tp2: 0.0` var ama bot v2 single-target açtı** → PR #S5.6 fix çalışmamış, restart sorunlu

---

## 9. Erişim Bilgileri

| Şey | Yer |
|---|---|
| Dashboard | `https://bot.ualgotrade.com` (primary) / `https://<VPS-IP>.nip.io` (fallback) |
| Dashboard şifre | Operatörün password manager'ı |
| VPS SSH | `ssh efloud-bot` (alias) veya `ssh root@<VPS_IP>` |
| SSH key | `~/.ssh/id_ed25519` (label `efloud-bot-hetzner`) |
| Repo | `/opt/efloud-bot` |
| State dir | `/opt/efloud-bot/state_1k/` |
| Log dir | container içinde `/app/logs/` |
| Telegram alert | `EFLOUD_TELEGRAM_TOKEN` + `EFLOUD_TELEGRAM_CHAT_ID` env'de |
| Postgres | Supabase pooler — `DATABASE_URL` env'de |

---

## 10. Claude'a Hangi Konularda Soru Sor

**Sor**:
- Shadow log yorumu (bana log paste et → analiz raporu)
- Backtest sonucu yorumu (comparison.json paste et → gate analizi + öneri)
- Yeni feature spec/plan yazımı
- Kod review (PR push etmeden önce)
- Bug repro + fix önerisi
- Memory'deki herhangi bir konunun açıklaması

**Sorma** (sen yaparsın):
- "Production'a deploy et"
- "Config değiştir, mainnet aç"
- "VPS'e bağlan, log dök"
- "Açık pozisyonu manuel kapat"

---

## 11. Acil Durum Akışı

**Senaryo**: Bot beklenmedik bir şekilde davranıyor (yanlış emir, açıklanamayan kayıp, state corruption).

```bash
# 1. Acil durdur
docker compose -f docker-compose.prod.yml stop efloud-bot

# 2. Binance UI'da pozisyonları kontrol et
#    Açık pozisyon varsa: manuel SL/TP koy, sonra manuel kapat

# 3. State backup al
docker exec efloud-bot tar -czf /tmp/state_backup_$(date +%s).tar.gz /app/state_1k
docker cp efloud-bot:/tmp/state_backup_*.tar.gz ./

# 4. Log dök
docker logs efloud-bot --since 4h > emergency_$(date +%s).log

# 5. Claude'a brief: log + state + ne olduğu
```

---

## 12. Bu Doküman + İlgili Referanslar

- Spec parent: `docs/superpowers/specs/2026-05-23-smc-entry-sltp-rework-design.md` (909 satır)
- Her PR'ın kendi spec'i: `docs/superpowers/specs/2026-05-2X-smc-v2-*.md`
- Her PR'ın plan'ı: `docs/superpowers/plans/2026-05-2X-smc-v2-*.md`
- CLAUDE.md: proje memory, kurallar, mimari
- Bu dosya: `HERMES.md` — operatör perspektifi

**Bot canlı, kararlı, kod %100 hazır. Acele yok, risk yok.**
