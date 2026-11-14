# Operatör Runbook'u — efloud-bot

> **Rol: runbook** (komut + doğrulama adımı). Anlık durum burada yazmaz → `collab/STATUS.md`.
> Canlı giriş akışı ve etkili/inert config anahtarları → `CONTEXT.md`.
> Hermes ajanının rolü (salt-okuma ops-watch + review; canlıya yazmaz) → `collab/models/hermes.md` (tek tanım).
> Tarihçe (2026-10-02 anlık görüntüsü, eski orkestrasyon, sosyal pipeline duyurusu) → `docs/history/hermes-2026.md`.
> Kaynak: 2026-11-14'te `HERMES.md` operatör bölümleri + `docs/OPERATOR_GUIDE.md` birleştirildi ve bayat olgular düzeltildi.
>
> **Kural:** aşağıdaki değiştirici (deploy / restart / config / env / breaker reset / stop) komutları
> yalnız insan operatör çalıştırır. Hermes ve diğer ajanlar yalnız "Doğrulama" satırlarındaki
> salt-okuma komutlarını kullanabilir.

---

## 1. Bot nedir?

Binance USDT-M futures üzerinde SMC doktriniyle otonom trade botu; Hetzner VPS'te 7/24,
FastAPI dashboard + Telegram alert. Aynı VPS'te aynı `efloud-bot:latest` image'ından üç
**mainnet** bot container'ı çalışır (`docker-compose.prod.yml`): `efloud-bot` (V1, mid profil,
state `/app/state_1k`), `efloud-bot-long` (V2), `efloud-bot-scalp` (V3). Hangilerinin "canlı"
sayıldığı → `collab/STATUS.md`.

**Algoritma (V1):** SMC v2 pullback + teyit, **LuxAlgo modu** (`configs/config.phase2_1k.yaml:187-188`,
`engine/smc_v2/luxalgo.py`): HTF lux swing bias → CHoCH/BOS kırılımı → kırılımın OB'sine geri
çekilme → entry-TF engulfing teyidi (`require_confirmation` default `true`,
`engine/safe_orchestrator.py:2114`) → **MARKET** emir (`exchange/__init__.py:1151-1153`);
SL = OB ucu + `calc_sl` ATR bandı. Ayrıntı: `CONTEXT.md`.

- **v1 sinyal yolu susturulur:** v2'nin sahiplendiği sembollerde (`smc_v2_symbols`,
  `configs/config.phase2_1k.yaml:93`) v1 girişleri `_v2_entry_active()` ile kesilir
  (`engine/safe_orchestrator.py:1486-1493`, log: `v1 signal suppressed`).
- **K1 (2026-11-14):** V1 yeni girişleri `EFLOUD_PAUSE_NEW_ENTRIES=true` ile durduruldu → §6.

**Hedef:** Forex (MT5/OANDA) pluggable exchange adapter.

### Mimari hızlı tur

```
main.py                              ← entry point
  └── SafeOrchestrator               ← analiz + safety katmanı
        ├── BinanceClient            ← CCXT futures wrapper
        ├── OrderManager             ← entry + SL + TP1 + TP2 yerleştirme
        ├── SMC engine               ← FVG, OB, swings, equal levels (+ LuxAlgo modu)
        ├── Regime detector          ← TRENDING/RANGING/VOLATILE (v2 emir yolunda kapı değil)
        ├── Confluence scoring       ← multi-TF + daily filter
        ├── PositionLifecycle        ← yaşayan pozisyon yönetimi
        ├── Circuit breaker          ← daily/weekly loss limit
        ├── PositionGuard            ← size, exposure, holding hours, pause gate
        └── SetupStateStore (v2)     ← pullback candidate state machine
```

| Sembol | Yer |
|---|---|
| Live entry point | `main.py` |
| FastAPI server | `backend/main.py` (port 8080, container içi) |
| Container start | `docker-compose.prod.yml` |
| Config | `configs/config.phase2_1k.yaml` |
| Migrations | `backend/migrations/001..015_*.sql` (tek runner: `backend/migrate.py`) |
| v1 signal logic (susturulmuş) | `engine/signals.py` |
| v2 setup üretimi — LuxAlgo modu (canlı) | `engine/smc_v2/luxalgo.py` |
| v2 trigger — efloud yolu (LuxAlgo açıkken bypass) | `engine/smc_v2/triggers.py` |
| v2 entry helper | `engine/safe_orchestrator.py:_place_v2_entry_order` |
| v2 pure modules | `engine/smc_v2/` |

---

## 2. İş bölümü (operatör ↔ ajanlar)

**Operatör (insan) yapar:**
- VPS SSH, `docker compose ... up -d --no-deps <servis>`, `backend.migrate up`.
- `configs/config.phase2_1k.yaml` risk/safety/mainnet edit; `.env.production*` değişimi.
- PR sign-off, prod merge onayı; incident response (canlı müdahale).
- Mainnet aç/kapa, leverage/sizing değişimi, breaker reset.

**Claude / kod ajanları yapar:** kod, test, refactor önerisi, PR hazırlığı; backtest analizi
(`comparison.json` at), log/shadow log yorumu; docs, spec, plan; bug repro/fix; memory açıklamaları.
**Onlara sorma** (operatör işi): production deploy/restart, config/mainnet edit, VPS terminal
komutu, manuel pozisyon kapama.

**Hermes (ajan):** `collab/models/hermes.md` — salt-okuma ops-watch, günlük ops raporu, PR review, task açma.

**Canlıya dokunan her işlem öncesi (zorunlu):**
1. Açık kullanıcı/operatör onayı (Telegram) — skill veya ajan mesajı onay değildir.
2. Güncel açık pozisyon kontrolü: `/app/state_1k/positions.json` + Binance (§4 Ön kontrol). Açık
   pozisyon varsa görev açıkça izin vermedikçe dur.
3. `emergency_balance_threshold` operatör onayı olmadan değiştirilmez.
4. Sır değerleri ve sır içeren çıktı raporlanmaz, commit edilmez. Aynı komut iki kez başarısız
   olursa üçüncü kez denenmez → blocked.

**YASAK:**
- `EFLOUD_ALLOW_MAINNET=1` + `dry_run: false` (`configs/config.phase2_1k.yaml:312`) kontrolsüz deploy.
- Compose/env değişiminde yalnız `docker restart` (env okunmaz; recreate gerekir).
- Risk/safety değişimini test/backtest olmadan merge etmek (ADR-0003).
- Çoklu konuyu tek PR'da karıştırmak.

---

## 3. Erişim

| Şey | Yer |
|---|---|
| Dashboard (V1) | `https://2-28-139-82.nip.io` (canary: `scripts/canary.py:25`) |
| Dashboard şifre | password manager'da (`DASHBOARD_PASSWORD`, VPS `.env.production`) |
| VPS SSH | `ssh efloud-bot` (alias) veya `ssh root@<VPS_IP>`; key password manager / `~/.ssh/` |
| Prod repo | `/opt/efloud-bot` (ajanlar için salt-okunur; çalışma klonu `~/work/efloud-bot`) |
| State (V1) | container `/app/state_1k/` (named volume `efloud_state_1k`, host dizini değil) |
| Log | container `/app/logs/` (volume `efloud_logs`) |
| Telegram | env `EFLOUD_TELEGRAM_TOKEN` + `EFLOUD_TELEGRAM_CHAT_ID` |
| Postgres | env `DATABASE_URL` (Supabase pooler; prod'da opsiyonel — ADR-0006) |

Bot portu (8080) host'a publish edilmez; API'ye container içinden erişilir
(`docker exec -i efloud-bot python ...`).

---

## 4. Deploy (tek servis — ADR-0001)

**Ön kontrol (salt-okuma):**
```bash
ssh efloud-bot
cd /opt/efloud-bot
git status --short                      # boş olmalı (yerel değişikliği ezme)
git fetch -q origin && git log --oneline -1 HEAD && git log --oneline -1 origin/master
docker exec efloud-bot cat /app/state_1k/positions.json | head -c 2000   # açık pozisyon? (closed_at yok = açık)
```
Doğrulama: hedef fast-forward; açık pozisyon yok veya operatör ayrıca onayladı; Binance UI'da
pozisyon + koruyucu emirler bağımsız kontrol edildi. (Deploy sırasında bot durur, pozisyon
yönetimi birkaç cycle aksar.)

**Deploy:**
```bash
git pull --ff-only
docker compose -f docker-compose.prod.yml build efloud-bot            # yalnız kod/config değiştiyse
docker compose -f docker-compose.prod.yml up -d --no-deps efloud-bot  # yalnız hedef servis
```
Doğrulama:
```bash
git rev-parse --short HEAD                                            # = hedef commit
docker inspect -f '{{.State.Health.Status}}' efloud-bot               # starting → healthy
docker exec efloud-bot python -c "import urllib.request; print(urllib.request.urlopen('http://localhost:8080/healthz', timeout=5).read().decode())"
```
`efloud-bot` `EFLOUD_AUTOSTART=0` ile gelir → healthz `{"status":"suspended","failures":["trading_not_started"]}`
beklenir; §5 ile başlat. İlk 30 sn 503 olabilir, bekle ve tekrarla.

> ⚠️ **`bash deploy/deploy.sh` kullanma** (operatör açıkça istemedikçe): servis argümanı almaz,
> tüm stack'i `build` + `up -d` yapar (`deploy/deploy.sh:21-25`) → **3 mainnet bot**
> (`efloud-bot`, `efloud-bot-long`, `efloud-bot-scalp`) ve sidecar'lar aynı anda recreate olur;
> sağlık beklemesi yalnız `efloud-bot` içindir. Tam-stack ancak üç botun pozisyon kontrolü
> (`/app/state_long`, `/app/state_scalp` dahil) yapıldıysa.
>
> ⚠️ `build efloud-bot` paylaşılan `efloud-bot:latest` image'ını değiştirir: long/scalp/alerter/
> daily-report/overseer/routines bir sonraki recreate'te yeni kodu sessizce alır
> (örn. `deploy/rotate-credentials.sh:108-116` V2/V3'ü de recreate eder). Deploy notuna yaz.

**Rollback:**
```bash
git status --short                                   # boş olmalı
git -c safe.directory=/opt/efloud-bot reset --hard <önceki-commit>
docker compose -f docker-compose.prod.yml build efloud-bot
docker compose -f docker-compose.prod.yml up -d --no-deps efloud-bot
```
Doğrulama: `git rev-parse --short HEAD` = `<önceki-commit>`; healthz (yukarıdaki komut); §5 ile start.
Deploy/rollback sonrası `collab/log/` girişine `DEPLOYED <sha>` yaz ve `collab/STATUS.md`'yi güncelle.

---

## 5. Bot start / stop (dashboard API, container içinden)

Parola yalnız container ortamından okunur; argv'ye, loga, URL'ye yazılmaz; TLS kapatılmaz.
```bash
docker exec -i efloud-bot python - <<'EOF'
import httpx, os
c = httpx.Client(base_url="http://localhost:8080", timeout=10)
r = c.post("/api/login", json={"password": os.environ["DASHBOARD_PASSWORD"]}); r.raise_for_status()
cookie = r.headers.get("set-cookie", "").split(";")[0]
r = c.post("/api/bot/start", json={}, headers={"Cookie": cookie})   # durdurmak: /api/bot/stop
print(r.status_code, r.json())
EOF
```
Doğrulama: healthz `status` = `ok` (`trading_not_started` kalktı); `docker logs efloud-bot --since 5m`
içinde döngü logu; `docker exec efloud-bot cat /app/state_1k/breaker.json` → `data.state` = `OPEN`.
Alternatif: dashboard UI Start butonu (aynı endpoint, `backend/api.py:383`).

---

## 6. K1 — V1 yeni giriş durdurma (pause) ve geri alma

Karar ve gerekçe: `docs/adr/0012-live-flow-pause-and-ramp.md`; uygulama kaydı: `collab/STATUS.md` (K1 satırı).
Öncelik: env `EFLOUD_PAUSE_NEW_ENTRIES` → `safety.pause_new_entries` (`configs/config.phase2_1k.yaml:458`)
→ `false` (`engine/safety/position_guard.py:62-117`); v2 emir yolunda da kontrol edilir. Mevcut pozisyon
yönetimi / SL-TP / reconcile etkilenmez. V2/V3 (long/scalp) trade ederken görülürse aynı env pause
kendi `.env.production.long` / `.env.production.scalp` dosyalarına uygulanır (ADR-0012 K8).

**Uygula:**
```bash
cd /opt/efloud-bot
cp .env.production .env.production.bak-$(date -u +%Y%m%d)
# .env.production içine: EFLOUD_PAUSE_NEW_ENTRIES=true  (editörle; değeri ekrana basma)
docker compose -f docker-compose.prod.yml up -d --no-deps efloud-bot   # env için recreate şart
```
Ardından §5 ile `/api/bot/start` (AUTOSTART=0).
Doğrulama:
```bash
docker logs efloud-bot --since 10m 2>&1 | grep "pause_new_entries config loaded"   # effective=True source=env
```
+ açık pozisyon sayısı, breaker `OPEN`, healthz `ok`.

**Geri al:** yedeği geri kopyala (`cp .env.production.bak-<tarih> .env.production`) → aynı
`up -d --no-deps efloud-bot` → §5 start. Doğrulama: aynı grep → `effective=False`.
Ramp (yeniden açma) kriterleri ADR-0012'dedir; kararı operatör verir.

---

## 7. Sık operasyonlar

**Container durumu**
```bash
docker ps --format '{{.Names}}\t{{.Status}}' | grep efloud     # Up (healthy)?
docker logs efloud-bot --tail 100
docker exec efloud-bot ls /app/state_1k
```

**Healthz / breaker durumu (salt-okuma)**
```bash
docker exec efloud-bot python -c "import urllib.request; print(urllib.request.urlopen('http://localhost:8080/healthz', timeout=5).read().decode())"
docker exec efloud-bot cat /app/state_1k/breaker.json
```
Sözleşme: `docs/runbooks/healthz-contract.md`.

**Migration**
```bash
docker exec efloud-bot python3 -m backend.migrate up
```
Doğrulama: komut çıktısında hata yok; `docker logs efloud-bot --since 5m | grep -i "record_trade_open failed"` boş.

**Config değişimi** (config image içine kopyalanır — `Dockerfile:48`; yalnız recreate yetmez)
```bash
vi /opt/efloud-bot/configs/config.phase2_1k.yaml        # risk/safety ise önce PR + review (ADR-0003)
docker compose -f docker-compose.prod.yml build efloud-bot
docker run --rm efloud-bot:latest python -c "import yaml; yaml.safe_load(open('/app/configs/config.phase2_1k.yaml')); print('yaml ok')"
docker compose -f docker-compose.prod.yml up -d --no-deps efloud-bot
```
Doğrulama: `yaml ok`; healthz; §5 start. Kalıcı değişiklik repo'ya PR olarak da girmeli
(VPS çalışma ağacında commit'siz değişiklik bir sonraki `git pull`'u bozar).

**Compose / env değişimi**
```bash
docker compose -f docker-compose.prod.yml up -d --no-deps <servis>   # recreate; docker restart env okumaz
```
Doğrulama: `docker inspect -f '{{.State.StartedAt}}' <container>` yeni; healthz; V1 ise §5 start.

**Kill switch (acil durdurma)**
```bash
docker compose -f docker-compose.prod.yml stop efloud-bot      # yalnız V1; long/scalp ayrı servis adıyla
```
Doğrulama: `docker ps -a --filter name=efloud-bot --format '{{.Names}} {{.Status}}'` → `Exited`.
Açık pozisyonların SL/TP'si borsada kalır; Binance UI'da kontrol et.

**Shadow log** (yalnız shadow modunda — v2 canlıyken boş olabilir)
```bash
docker exec efloud-bot tail -f /app/logs/smc_v2_shadow.log
docker exec efloud-bot wc -l /app/logs/smc_v2_shadow.log
```

**Veritabanı sorgusu** (`DATABASE_URL` tanımlıysa)
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

## 8. Breaker / HALT kurtarma

| Koşul (config `safety:`) | Durum | Geri dönüş | Kaynak |
|---|---|---|---|
| Günlük kayıp ≥ `daily_loss_limit_pct` (`config:371`) | TRIPPED | ertesi gün 00:00 UTC otomatik OPEN | `engine/safety/breaker.py:290-306` |
| Ardışık kayıp ≥ `consecutive_loss_limit` (`config:373`) | TRIPPED | `consecutive_pause_min` (`config:374`) sonra otomatik OPEN | `engine/safety/breaker.py:320-327` |
| Haftalık DD ≥ `weekly_drawdown_limit_pct` (`config:372`; tepe 7 günde yeniden tabanlanır) | HALTED | manuel reset | `engine/safety/breaker.py:308-318` |
| Bakiye < `emergency_balance_threshold` | HALTED | manuel reset | `engine/safety/breaker.py:283-288` — eşik 0 → fiilen kapalı (`config:424`) |

(`config` = `configs/config.phase2_1k.yaml`.) HALTED'da healthz `200 {"status":"suspended","failures":["breaker_halted"]}`
döner; **restart çözmez**, autoheal bilerek dokunmaz.

**Reset:** reset otomatik değildir. Kök nedeni incele (`breaker.json` → `reason`), açık pozisyonları
yeniden kontrol et, operatör onayı al; sonra `docs/runbooks/breaker-reset.md`'deki container-içi
login + `POST /api/breaker/reset?reason=...` akışını uygula (bot RUNNING olmalı; değilse önce §5).
Tekrarlayan trip'te yeniden resetleme.
Doğrulama: `breaker.json` → `data.state` = `OPEN`; healthz `failures` boş.

---

## 9. Tehlike sinyalleri (olursa hemen bildir)

1. **`healthz` 503** → bot internal hata, autoheal restart loop riski (`docs/runbooks/crash-loop-recovery.md`).
2. **Circuit breaker HALTED / TRIPPED** → §8 tablosu.
3. **`record_trade_open failed`** → migration eksik, DB tablo uyuşmazlığı (§7 Migration).
4. **Orphan SL/TP** → `reduceOnly` emir Binance'te kalmış, pozisyon kapalı.
5. **`v1 signal suppressed` logu hiç gelmiyor** → v2 sembol sahipliği bozuldu, çift giriş riski.
6. **v1 vs v2 zıt sinyal.**
7. **State'te `tp2: 0.0`.**
8. **`order_manager.repair_missing_sl`** → SL yerleştirme denemeleri tükendi, reconcile tamir ediyor. Sık olursa API/retry mantığı araştırılmalı.
9. **`order_manager.be_sl_placement_failed`** → TP1 sonrası breakeven SL 3 denemede başarısız; pozisyon SL'siz bekliyor, reconcile kurtaracak — izle.

---

## 10. Acil durum (incident)

**Senaryo:** bot anormal (hatalı emir, kontrolsüz state, limit aşımı).
```bash
# 1. Acil durdur
docker compose -f docker-compose.prod.yml stop efloud-bot
# 2. Binance UI: pozisyonları kontrol et; SL/TP'yi manuel koy veya kapat
# 3. State yedeği (docker cp durmuş container'da da çalışır; exec çalışmaz)
TS=$(date -u +%Y%m%dT%H%M%SZ)
docker cp efloud-bot:/app/state_1k ./state_backup_$TS
# 4. Log dök
docker logs efloud-bot --since 4h > emergency_$TS.log 2>&1
# 5. Claude'a ilet: log + state + durum özeti (sır içeren satırları ayıkla)
```
Doğrulama: `docker ps -a` → `efloud-bot Exited`; `ls state_backup_$TS/` içinde `positions.json`,
`breaker.json`; Binance'te her açık pozisyonun SL'si var.
Ayrıntı: `docs/runbooks/on-call-playbook.md`, `docs/runbooks/disaster-recovery.md`,
`docs/runbooks/backup-restore.md`.

---

## 11. §6 Adım 3 (eski HERMES.md) — v1↔v2 baseline backtest gate

> `scripts/evaluate_backtest_gates.py` docstring'i bu bölüme atıf yapar ("HERMES.md §6 Adım 3").
> Bu kapı **v1↔v2 göreli** karşılaştırmadır; yeni edge/scoring değişikliği için GO kriteri
> `docs/adr/0011-edge-go-criteria.md`, koşum prosedürü (sabit pencere, sembol başı koşu,
> NET maliyet) `docs/runbooks/backtest-gate.md`. Orijinal metin: `git show d137eb6^:HERMES.md`.

```bash
python -m scripts.prefetch_data --config configs/config.phase2_1k.yaml \
  --symbols ETH/USDT,BTC/USDT,SOL/USDT,BNB/USDT,ADA/USDT,LINK/USDT,AVAX/USDT --days 180
python -m backtest.cli compare \
  --symbols ETH/USDT,BTC/USDT,SOL/USDT,BNB/USDT,ADA/USDT,LINK/USDT,AVAX/USDT \
  --period-days 180 --config configs/config.phase2_1k.yaml
python scripts/evaluate_backtest_gates.py reports/backtests/<run>/comparison.json
```
Gate metrikleri: `win_rate`, `avg_realized_rr`, `max_drawdown_pct`, `stop_hunt_rate`, `sharpe_like`;
eşikler tek kaynakta: `backtest/comparison.py:26-32` (`DEFAULT_GATES`).

**Karar** (script exit kodu):
- `0` tümü `pass` → "S7'ye geç" (S7 3-faz rollout tamamlandı; bugünkü karşılığı ADR-0012 ramp adımı).
- `1` en az bir `warn` → shadow süresini uzat.
- `2` en az bir `hard_reject` → v2 redesign (Claude'a bildir, spec revize).
- `3` kullanım / IO hatası.

Doğrulama: `comparison.json` mevcut; script çıktısındaki tablo ve exit kodu kayda geçti.
Windows'ta uzun koşularda standby kapalı olmalı; grid'de çok-süreç takılabilir → sembol başı koşu.

---

## 12. Kurulum (sıfırdan)

| Bileşen | Gereksinim |
|---|---|
| Sunucu | Hetzner VPS (veya eşdeğeri), 2 vCPU / 4 GB RAM minimum |
| OS | Ubuntu 22.04+ (deploy script'leri bash) |
| Docker | Docker Engine + compose plugin |
| Python | 3.11+ (lokal geliştirme) |
| Binance | USDT-M Futures hesabı + API key (**çekim kapalı**, IP whitelist önerilir) |
| Domain | `nip.io` wildcard veya gerçek domain |

```bash
git clone https://github.com/Leblepito/efloud-bot.git && cd efloud-bot
cp .env.example .env.production && chmod 600 .env.production   # asla commit etme
# Doldur (değerler password manager'da): BINANCE_API_KEY, BINANCE_API_SECRET, DASHBOARD_PASSWORD,
#   EFLOUD_ALLOW_MAINNET (1 = canlı, 0 = dry-run), EFLOUD_AUTOSTART (V1'de 0),
#   EFLOUD_TELEGRAM_TOKEN / EFLOUD_TELEGRAM_CHAT_ID (opsiyonel)
bash deploy/setup-server.sh                                      # sunucuda: Docker + bağımlılıklar
```
V2/V3 kendi `.env.production.long` / `.env.production.scalp` dosyalarını kullanır (`docker-compose.prod.yml`).
Doğrulama: `docker compose -f docker-compose.prod.yml config --services` servisleri listeler;
ilk deploy §4. Ayrıntı: `deploy/HETZNER_GUIDE.md`.

---

## 13. Yapılandırma referansı (`configs/config.phase2_1k.yaml`)

Değerler burada kopyalanmaz — satıra bak (etkili/inert ayrımı: `CONTEXT.md`).

| Anahtar | Satır | Not |
|---|---|---|
| `engine.smc_version` | `:90` | `v2` = pullback algoritması |
| `engine.smc_v2_symbols` | `:93` | v2'nin sahiplendiği semboller |
| `engine.smc_v2_shadow` | `:95` | `true` = hayalî sinyal, canlı emir yok |
| `smc_v2.po3_gate` | `:131` | manipülasyon fazında giriş blokajı |
| `smc_v2.max_zone_overshoot_atr` | `:168` | bölge aşım toleransı |
| `smc_v2.luxalgo.enabled` | `:188` | LuxAlgo modu; `false` = efloud triggers yolu |
| `smc_v2.require_confirmation` | — | config'te yok → default `true` (`engine/safe_orchestrator.py:2114`) |
| `risk.min_confluence` | `:282` | v1 confluence eşiği (lux içi ayrı: `:205`) |
| `risk.fixed_position_usdt` / `exchange.leverage` | `:299` / `:71` | marjin × kaldıraç = notional |
| `operation.dry_run` | `:312` | `false` = gerçek emir |
| `safety.daily_loss_limit_pct` / `weekly_drawdown_limit_pct` | `:371` / `:372` | TRIP / HALT (§8) |
| `safety.allow_volatile_entries` | `:385` | yalnız v1 yolu; v2 emir yolunda rejim kapısı yok (`engine/safe_orchestrator.py:1179`) |
| `safety.emergency_balance_threshold` | `:424` | 0 = kapalı (operatör kararı) |
| `safety.pause_new_entries` | `:458` | env `EFLOUD_PAUSE_NEW_ENTRIES` önceliklidir (§6) |

---

## 14. İzleme ve güvenlik katmanları

- **Telegram alerter** (`ops/alerter`): breaker, marjin, pozisyon anomalileri (kapsam → `collab/STATUS.md`).
- **Overseer** (`ops/overseer`, `docs/runbooks/overseer-operations.md`): bot sağlığı, crash tespiti.
- **Routines** (`scripts/routines`, `docs/runbooks/routines-cron-setup.md`): breaker_watch, margin_watch, position_audit.
- **Panel** (`panel/`, `docker-compose.panel.yml`): 3-bot birleşik izleme.

| Katman | Ne yapar |
|---|---|
| Circuit breaker | günlük TRIP / haftalık HALT / ardışık kayıp cooldown (§8) |
| PositionGuard | max notional, exposure, holding hours, SL mesafesi, pause gate |
| Orphan cleanup | SL/TP'siz kalan pozisyonları tamir (`config:459-460`) |
| Reconcile | Binance ile state tutarlılığı |
| Kill switch | §7 |

**Sırlar:** tümü `.env.production*` içinde, repo'da asla (`.gitignore`: `.env*`, `*.key`, `*.pem`).
Döndürme: `bash deploy/rotate-credentials.sh` — ⚠️ V1 + V2 + V3 (+ panel) container'larını
`--force-recreate` eder (`deploy/rotate-credentials.sh:108-116`); önce üç botun pozisyon kontrolü.
`EFLOUD_ALLOW_MAINNET=1` yalnız prod VPS'te, bilinçli insan kararıyla.

---

## 15. Sık sorulan sorular

**Bot neden işleme girmiyor?** Sırayla: (0) K1 pause aktif mi? (§6 grep), (1) breaker `OPEN` mı?
(§7), (2) bot başlatıldı mı? (healthz `trading_not_started` → §5), (3) v2 setup adayı var mı?
(`docker exec efloud-bot cat /app/state_1k/setup_candidates.json`), (4) HTF bias uyumu
(kırılım bias yönünde mi?). Not: v2 emir yolunda rejim (VOLATILE) kapısı uygulanmaz
(`engine/safe_orchestrator.py:1179`).

**Bot neden tek yönde (ör. yalnız LONG) giriyor?** HTF bias filtresi — kırılım yalnız HTF bias ile
aynı yöndeyse kabul edilir. SMC doktrini; bias dönünce ters yön otomatik gelir.

**Acil bakiye HALTI kalktı, fon koruması yok mu?** Koruma günlük TRIP ve haftalık HALT limitleriyle
(§8). Mutlak bakiye eşiği kaldırıldı çünkü düşük bakiyede bot kalıcı HALTED kalıyordu (`config:424` yorumu).

**Deploy sonrası bot neden başlamıyor?** V1 `EFLOUD_AUTOSTART=0` — bilinçli (incident-recovery
posture; `docker-compose.prod.yml` healthcheck `start_period` buna göre). §5 ile başlat.

---

## 16. Test ve sosyal pipeline

```bash
python -m pytest --ignore=external_repos --import-mode=importlib -q
python scripts/regression_ledger.py check
```
Sosyal medya pipeline'ı (varsayılan: hiçbir şey yayınlanmaz; onay / live / platform flag kapıları
default KAPALI): `python -m scripts.daily_social_run --date "$(date -u +%F)"` — ayrıntı
`skills/social-publishing/SKILL.md`, `docs/runbooks/social-content-setup.md`.

---

## 17. Referanslar

| Doküman | İçerik |
|---|---|
| `collab/STATUS.md` | anlık durum (master / VPS HEAD / konteynerler / açık sorular) |
| `CONTEXT.md` | canlı giriş akışı, sözlük, etkili/inert anahtarlar |
| `collab/README.md`, `collab/models/hermes.md` | çok-model çalışma düzeni, Hermes rolü |
| `docs/adr/` | kalıcı kararlar (0001 tek-VPS compose, 0003 gate'ler, 0012 pause/ramp) |
| `docs/runbooks/` | diğer runbook'lar (breaker-reset, on-call, disaster-recovery, crash-loop, backtest-gate) |
| `docs/history/hermes-2026.md` | HERMES.md tarihsel bölümleri |
| `CLAUDE.md` | proje kuralları, Pine Script kuralları |
| `deploy/HETZNER_GUIDE.md` | sunucu kurulumu |
| `skills/efloud-deploy/SKILL.md` | ajan tarafı deploy kontrol listesi |
