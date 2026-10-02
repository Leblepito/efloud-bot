# Efloud-bot — Kurulum ve Kullanım Rehberi

> **Kapsam:** efloud-bot'un sıfırdan kurulumu, günlük kullanımı, güvenlik
> yapılandırması ve sosyal medya pipeline'ı. Bot algoritması hakkında detay:
> `CLAUDE.md` (mimari) + `HERMES.md` (operatör kılavuzu).
> Güncelleme: 2026-10-02 (v2 AKTİF, BOS girişleri, acil bakiye HALTI kaldırıldı).

---

## 1. Sistem Gereksinimleri

| Bileşen | Gereksinim |
|---|---|
| Sunucu | Hetzner VPS (veya eşdeğeri), 2 vCPU / 4GB RAM minimum |
| İşletim sistemi | Ubuntu 22.04+ (deploy scriptleri bash tabanlı) |
| Docker | Docker Engine + docker compose plugin |
| Python | 3.11+ (lokal geliştirme için) |
| Binance | USDT-M Futures hesabı + API key (çekim kapalı) |
| Domain | `nip.io` wildcard (dashboard için) veya gerçek domain |

---

## 2. Kurulum

### 2.1 Repo'yu çek

```bash
git clone https://github.com/Leblepito/efloud-bot.git
cd efloud-bot
```

### 2.2 Ortam değişkenleri

`.env.production` oluştur (asla repo'ya commit etme):

```bash
cp .env.example .env.production
# Düzenle:
#   BINANCE_API_KEY=...
#   BINANCE_API_SECRET=...
#   DASHBOARD_PASSWORD=<güçlü şifre>
#   EFLOUD_ALLOW_MAINNET=1        # CANLI trade için (0 = dry-run)
#   EFLOUD_TELEGRAM_TOKEN=...     # opsiyonel
#   EFLOUD_TELEGRAM_CHAT_ID=...   # opsiyonel
```

> **Güvenlik:** Binance API key'inde **çekim (withdraw) kapalı** olmalı.
> Key sızsa bile fon çekilemez. IP whitelist önerilir.

### 2.3 Sunucu kurulumu (Hetzner)

```bash
# Sunucuda:
bash deploy/setup-server.sh        # Docker + bağımlılıklar
```

Detaylı adımlar: `HETZNER_DEPLOYMENT_CHECKLIST.md` + `deploy/HETZNER_GUIDE.md`.

### 2.4 Deploy

```bash
# Lokal değişiklikleri push et, sonra sunucuda:
ssh root@<VPS_IP>
cd /opt/efloud-bot
git pull --ff-only
bash deploy/deploy.sh              # build + recreate + healthcheck
```

### 2.5 Bot'u başlat

AUTOSTART=0 olduğu için (incident-recovery posture) her deploy sonrası manuel
başlatma gerekir:

```bash
PW=$(grep DASHBOARD_PASSWORD /opt/efloud-bot/.env.production | cut -d= -f2-)
curl -sk -c /tmp/c.txt -X POST https://<VPS_IP>.nip.io/api/login \
  -H "Content-Type: application/json" -d "{\"password\":\"$PW\"}"
curl -sk -b /tmp/c.txt -X POST https://<VPS_IP>.nip.io/api/bot/start \
  -H "Content-Type: application/json" -d "{}"
rm -f /tmp/c.txt
```

---

## 3. Yapılandırma (configs/config.phase2_1k.yaml)

### 3.1 Kritik bölümler

| Bölüm | Anahtar | Değer (2026-10-02) | Açıklama |
|---|---|---|---|
| `engine` | `smc_version` | `v2` | v2 pullback algoritması AKTİF |
| `engine` | `smc_v2_symbols` | `[BTC, ETH, XRP, DOGE, SOL, ...]` | v2'nin sahiplendiği semboller |
| `engine` | `smc_v2_shadow` | `false` | `true` = hayalî sinyal (canlı emir yok) |
| `safety` | `emergency_balance_threshold` | `0` | Acil bakiye HALTI KALDIRILDI |
| `safety` | `daily_loss_limit_pct` | `10.0` | Günlük kayıp limiti (TRIP) |
| `safety` | `weekly_drawdown_limit_pct` | `25.0` | Haftalık DD limiti (HALT) |
| `safety` | `allow_volatile_entries` | `true` | Volatil rejimde giriş serbest |
| `smc_v2` | `max_zone_overshoot_atr` | `2.0` | Bölge aşım toleransı |
| `smc_v2` | `require_confirmation` | `true` | Engulfing teyidi zorunlu |
| `smc_v2` | `po3_gate` | `true` | Manipülasyon fazında giriş blokajı |
| `risk` | `min_confluence` | `50` | Minimum confluence skoru |
| `risk` | `fixed_position_usdt` | `50` | $50 marjin × 10x = $500 notional |

### 3.2 Giriş akışı (v2)

```
LTF (15m) CHoCH veya BOS kırılımı
  → HTF bias uyumu (BULL/BEAR)
  → kırılımı yapan OB/BB bölgesi (veya FVG/OTE fallback)
  → AWAITING_PULLBACK (geri çekilme beklenir)
  → fiyat bölgeye döner (retest)
  → engulfing teyidi (require_confirmation=true)
  → CONFIRMED → limit emir
  → SL: likidite çizgisi (kırılım öncesi swing) ötesinde
```

> **Not:** v1 sinyal girişleri v2'nin sahiplendiği sembollerde susturulur —
> kırılım anında market emri girilmez, her zaman geri çekilme beklenir.

---

## 4. Günlük Kullanım

### 4.1 Dashboard

- URL: `https://<VPS_IP>.nip.io`
- Login: `DASHBOARD_PASSWORD`
- Özellikler: durum, breaker, pozisyonlar, PnL, equity eğrisi, bot start/stop,
  breaker reset.

### 4.2 Sık komutlar

```bash
# Durum kontrolü
docker ps | grep efloud-bot
docker logs efloud-bot --tail 100

# Healthz
curl -s http://localhost:8080/api/healthz

# Breaker durumu
cat /opt/efloud-bot/state_1k/breaker.json

# Breaker reset (HALTED ise)
curl -sk -b /tmp/c.txt -X POST "https://<VPS_IP>.nip.io/api/breaker/reset?reason=operator+reset"

# Migration
docker exec efloud-bot python3 -m backend.migrate up
```

### 4.3 İzleme

- **Telegram alerter** (`ops/alerter`): breaker, marjin, pozisyon anomalileri.
- **Overseer** (`ops/overseer`): bot sağlığı, crash tespiti.
- **Routines** (`scripts/routines`): breaker_watch, margin_watch, position_audit.
- **Panel** (`panel/`): 3-bot birleşik izleme (V1 mid / V2 long / V3 scalp).

---

## 5. Güvenlik

### 5.1 Katmanlar

| Katman | Ne yapar |
|---|---|
| Circuit breaker | Günlük %10 TRIP / haftalık %25 HALT / ardışık kayıp cooldown |
| PositionGuard | Max notional, exposure, holding hours, SL mesafesi |
| Orphan cleanup | SL/TP'siz kalan pozisyonları tamir |
| Reconcile | Binance ile state tutarlılığı |
| Kill switch | `docker compose stop efloud-bot` (acil) |

### 5.2 Sır yönetimi

- Tüm sırlar `.env.production`'da — repo'da ASLA.
- `.gitignore` `.env*`, `*.key`, `*.pem` içerir.
- Kimlik bilgisi döndürme: `bash deploy/rotate-credentials.sh`.
- `EFLOUD_ALLOW_MAINNET=1` yalnız prod VPS'te, bilinçli insan kararıyla.

### 5.3 Acil durum

```bash
# 1. Acil durdur
docker compose -f docker-compose.prod.yml stop efloud-bot

# 2. Binance UI'dan pozisyonları kontrol et (SL/TP manuel)

# 3. State backup
docker exec efloud-bot tar -czf /tmp/state_backup_$(date +%s).tar.gz /app/state_1k

# 4. Log dök
docker logs efloud-bot --since 4h > emergency_$(date +%s).log
```

Detay: `docs/runbooks/on-call-playbook.md` + `docs/runbooks/disaster-recovery.md`.

---

## 6. Sosyal Medya Pipeline'ı

Bot sinyallerini chart PNG + MP4 + caption olarak X/IG/YT'ye hazırlar.
**Varsayılan: hiçbir şey yayınlanmaz** — 3 güvenlik kapısı (onay, live,
platform flag'leri) hepsi default KAPALI.

```bash
python -m scripts.daily_social_run --date "$(date -u +%F)"
```

Detay: `skills/social-publishing/SKILL.md`.

---

## 7. Test

```bash
python -m pytest --ignore=external_repos --import-mode=importlib -q
```

---

## 8. Sık Sorulan Sorular

**Q: Bot neden işleme girmiyor?**
A: Sırasıyla kontrol et: (1) breaker OPEN mı? (`state_1k/breaker.json`),
(2) rejim kapısı (VOLATILE blokajı — `allow_volatile_entries`), (3) v2 setup
adayları var mı? (`state_1k/setup_candidates.json`), (4) HTF bias uyumu
(CHoCH/BOS trend yönünde mi?).

**Q: Bot neden sadece LONG giriyor?**
A: HTF bias filtresi — CHoCH/BOS yalnız HTF bias ile aynı yöndeyse kabul
edilir. Piyasa BULL ise yalnız LONG üretilir. Bu bir kısıtlama değil, SMC
doktrinidir; piyasa döndüğünde SHORT'lar otomatik gelir.

**Q: Acil bakiye HALTI kalktı, fon koruması yok mu?**
A: Koruma günlük %10 (TRIP) ve haftalık %25 (HALT) kayıp limitleriyle
sağlanıyor. Mutlak bakiye eşiği kaldırıldı çünkü düşük bakiyede bot kalıcı
HALTED kalıyordu.

**Q: Deploy sonrası bot neden başlamıyor?**
A: AUTOSTART=0 — bilinçli tasarım. `POST /api/bot/start` ile başlat (bkz. §2.5).

---

## 9. Referanslar

| Doküman | İçerik |
|---|---|
| `HERMES.md` | Operatör kılavuzu (deploy, config, incident) |
| `CLAUDE.md` | Proje belleği, mimari, Pine Script kuralları |
| `RISK_MAP.md` | Risk haritası |
| `MAINNET_DEPLOY_GUIDE.md` | Mainnet deploy prosedürü |
| `HETZNER_DEPLOYMENT_CHECKLIST.md` | Hetzner deploy checklist |
| `docs/runbooks/` | Operasyon runbook'ları |
| `skills/social-publishing/SKILL.md` | Sosyal medya pipeline'ı |
