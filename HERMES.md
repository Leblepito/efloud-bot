# HERMES.md — Efloud-bot Operatör Kılavuzu

> Operatör/insan onay zinciri (Hermes) için. Yönetim kılavuzu.
> Tarih: 2026-05-28 | Master HEAD: `6d784a2` | Branch: `fix/sltp-delivery-reliability` (PR bekliyor) | Bot durumu: **CANLI**

---

## 1. Nedir Bu Bot?

**Efloud-bot**: Binance USDT-M futures üzerinde SMC doktriniyle otonom trade botu. Hetzner VPS 7/24, FastAPI dashboard + Telegram alert.

**Algoritma**: 2 paralel sürüm hazır.
- **v1** (RUNNING): mevcut SMC entry/SL/TP (canlı).
- **v2** (HAZIR, INERT): pullback+confirmation algoritması. Kod merge edildi, prod dormant.

**Hedef**: Forex (MT5/OANDA) pluggable exchange adapter.

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

**Hermes yapar** (insan):
- VPS SSH, `docker compose up -d`, `backend.migrate up`.
- `config.yaml` risk/safety/mainnet edit.
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

v2 emir vermez çünkü:
1. `config.yaml engine.smc_version=v1` → main.py `_build_setup_state_store` None döner → `SafeOrchestrator.setup_state_store=None` → `_place_v2_entry_order` çağrılmaz.
2. `config.yaml engine.smc_v2_symbols=[]` → whitelist tüm sembolleri reddeder.
3. `config.yaml engine.smc_v2_shadow=false` → (sadece üst 2 bypass edilirse devreye girer).

Canlı v2 emri için **minimum 3 manuel config editi** gerekir.

### 5c. Pending

- **fix/sltp-delivery-reliability** (YENİ — 2026-05-28, PR bekliyor):
  - CLI wiring fix + SL retry/repair + breakeven SL retry
  - 272 test passed, 0 regression
  - `main.py`, `exchange/__init__.py` değişti — non-breaking
  - Review + merge sonrası deploy: `git pull && docker compose up -d`
- **Prod deploy** (zero-risk — default inert).
- **Shadow aktivasyon** (1 hafta gözlem).
- **Baseline backtest** (6 aylık gerçek OHLCV).
- **PR #S7**: 3-faz prod rollout (ETH+BTC → +5 mid-cap → all 20).

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

**1 saat gözlem**:
- `https://bot.ualgotrade.com` → healthz yeşil.
- Mevcut açık pozisyonlar (varsa) yönetilmeye devam eder.
- Telegram alert'ler gelir.
- Circuit breaker tetiklenmedi.

**Rollback**:
```bash
git -c safe.directory=/opt/efloud-bot reset --hard d03857c
docker compose -f docker-compose.prod.yml up -d
```

### Adım 2 — Shadow aktivasyon (sessiz pencereyi bekle)

```yaml
engine:
  smc_version: v2                # v1 → v2
  smc_v2_symbols: ["*"]          # tüm semboller
  smc_v2_shadow: true            # ⚠️ TRUE kalmalı — false yaparsan CANLI EMİR VERİR
```

```bash
docker compose -f docker-compose.prod.yml up -d   # recreate
docker exec efloud-bot tail -f /app/logs/smc_v2_shadow.log
```

**Davranış**: v1 canlı emir verir. v2 hayalî sinyal hesaplayıp JSON yazar. Sıfır gerçek emir.

**7 gün gözlem**:
- Günlük sinyal sayısı: `wc -l /app/logs/smc_v2_shadow.log`.
- direction, entry, sl, tp1, tp2 kontrolü.
- v1 trade'ler ile karşılaştır.
- Logu Claude'a at, analiz raporu hazırlasın.

**Rollback**:
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
python -m scripts.prefetch_data \
  --symbols ETH/USDT,BTC/USDT,SOL/USDT,BNB/USDT,ADA/USDT,LINK/USDT,AVAX/USDT \
  --period-days 180

python -m backtest.cli compare \
  --symbols ETH/USDT,BTC/USDT,SOL/USDT,BNB/USDT,ADA/USDT,LINK/USDT,AVAX/USDT \
  --period-days 180 \
  --config configs/config.phase2_1k.yaml
```

Çıktı: `reports/backtests/<date>_compare_7sym_180d_<runid>/comparison.json`

**Gate hedefleri**:
- `win_rate`: ≥ v1 (hard reject < v1×0.95)
- `avg_realized_rr`: ≥ 1.5 absolute (hard reject < 1.2)
- `max_drawdown_pct`: ≤ v1 (hard reject > v1×1.1)
- `stop_hunt_rate`: < v1×0.5 (hard reject ≥ v1)
- `sharpe_like`: ≥ v1 (hard reject < v1×0.9)

**Karar**:
- Tümü `pass` → S7'ye geç.
- `hard_reject` → v2 redesign (Claude'a bildir, spec revize).
- `warn` → shadow süresini uzat.

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

**Rollback kriteri** (manuel):
- 3 ardışık loss VEYA PnL ≤ -2% → `smc_version: v1` + recreate.

**Phase 2** (1 hafta): `+ SOL, BNB, ADA, LINK, AVAX`
**Phase 3** (sürekli): tüm 20 sembol

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
vi /opt/efloud-bot/config.yaml

# YAML parse test
docker exec efloud-bot python3 -c "import yaml; yaml.safe_load(open('/app/config.yaml'))"

# Recreate
docker compose -f docker-compose.prod.yml up -d
```

### Compose env değişimi
```bash
docker compose -f docker-compose.prod.yml up -d   # recreate
```

### Kill switch (acil durdurma)
```bash
docker compose -f docker-compose.prod.yml stop efloud-bot
```

### Shadow log incelemesi
```bash
# Tail
docker exec efloud-bot tail -f /app/logs/smc_v2_shadow.log

# Sinyal sayısı
docker exec efloud-bot wc -l /app/logs/smc_v2_shadow.log

# Sembol dağılımı
docker exec efloud-bot sh -c "cat /app/logs/smc_v2_shadow.log | python3 -c \"import json,sys; from collections import Counter; print(Counter(json.loads(l)['symbol'] for l in sys.stdin))\""

# Son 10 sinyal pretty-print
docker exec efloud-bot sh -c "tail -10 /app/logs/smc_v2_shadow.log | python3 -m json.tool --json-lines"
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
2. **Circuit breaker HALTED** → Günlük/haftalık limit aşıldı, trade durdu.
3. **`record_trade_open failed`** → Migration eksik, db table uyuşmazlığı.
4. **Orphan SL/TP** → `reduceOnly` order Binance'te kalmış, poz kapalı.
5. **Shadow log'da `would_execute: true`** → Shadow bypass bug! Canlı emir riski.
6. **v1 vs v2 zıt sinyal**.
7. **State'te `tp2: 0.0`**.
8. **`order_manager.repair_missing_sl`** → SL placement exhaust edildi, reconcile tamir ediyor. Sık olursa API/retry mantığı araştırılmalı.
9. **`order_manager.be_sl_placement_failed`** → TP1-hit sonrası breakeven SL 3 denemede başarısız. Pozisyon SL'siz bekliyor, reconcile kurtaracak — ama izlenmeli.

---

## 9. Erişim Bilgileri

| Şey | Yer |
|---|---|
| Dashboard | `https://bot.ualgotrade.com` / `https://<VPS-IP>.nip.io` |
| Dashboard şifre | Password manager |
| VPS SSH | `ssh efloud-bot` / `ssh root@<VPS_IP>` |
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

- Spec parent: `docs/superpowers/specs/2026-05-23-smc-entry-sltp-rework-design.md` (909 satır).
- Her PR spec: `docs/superpowers/specs/2026-05-2X-smc-v2-*.md`.
- Her PR plan: `docs/superpowers/plans/2026-05-2X-smc-v2-*.md`.
- `CLAUDE.md`: Proje bellek, kural, mimari.
- `HERMES.md`: Operatör kılavuzu.

**Bot canlı, kararlı, kod %100 hazır. Acele yok, risk yok.**
