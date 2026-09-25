# Mainnet Deploy Guide — Efloud Bot

> **Tarih:** 2026-08-12 (genel prosedür — orijinal taslak)
> **Hazırlayan:** Hermes Agent
> **Güncel durum (2026-09-25):** VPS kuruldu ve deploy edildi — bkz. `HETZNER_DEPLOYMENT_CHECKLIST.md`
> (sunucu 2.28.139.82, 8 container healthy, Binance API bağlantısı doğrulandı). Bu dosya artık
> yeni bir VPS kurulumu gerektiğinde (örn. ikinci sunucu, felaket kurtarma) genel prosedür
> referansı olarak kullanılır; adım adım komutlar için `deploy/HETZNER_GUIDE.md`'yi izleyin.

---

## ⚠️ Ön Koşullar (Checklist)

Tümünü ✅ yapana kadar **mainnet'e geçmeyin**:

- [ ] **VPS hazır** (Hetzner CX21/CPX21, Ubuntu 22.04, Docker kurulu)
- [ ] **SSH erişimi** çalışıyor (`ssh root@<VPS_IP>`)
- [ ] **`.env.production`** VPS'te `/opt/efloud-bot/.env.production` konumunda, doğru secret'larla
- [ ] **`.env.production.long`** VPS'te `/opt/efloud-bot/.env.production.long` konumunda
- [ ] **`.env.production.scalp`** VPS'te `/opt/efloud-bot/.env.production.scalp` konumunda
- [ ] **`config.phase2_1k.yaml`** → `dry_run: false` + `testnet: false` + `smc_v2_shadow: false` + explicit whitelist
- [ ] **Binance API Key** → Futures yetkisi ✅, Çekim yetkisi ❌, IP whitelist (VPS IP eklenmiş)
- [ ] **Supabase DB** erişilebilir (pooler port 6543)
- [ ] **Risk limitleri** onaylandı (daily 10%, weekly 25%, max 10 pozisyon, $500 notional/poz)
- [ ] **Açık pozisyon YOK** (Start'a basmadan önce dashboard → Positions boş olmalı)
- [ ] **Hermes onayı** alındı (bu belgede ✅)

---

## 1️⃣ VPS OLUŞTURMA (Manuel - Hetzner Cloud Console)

Hetzner API token geçersiz (401), bu yüzden **manuel** oluşturun:

```
1. https://console.hetzner.cloud → Projects → "efloud-bot" (veya yeni project)
2. Servers → Add Server
3. Config:
   - Name: efloud-bot-vps
   - Location: Nuremberg (nbg1) / Helsinki (hel1) / Falkenstein (fsn1)
   - Image: Ubuntu 22.04
   - Type: CPX21 (3 vCPU, 4GB RAM, 80GB SSD) — ÖNERİLEN
            veya CX21 (2 vCPU, 4GB RAM, 40GB SSD)
   - SSH Key: "efloud-bot-hetzner" (önceden eklenmiş olmalı)
   - Network: Default
   - Placement Group: None
4. Create → IP adresini not alın (örn: 5.75.xxx.xxx)
```

**IP not:** `<VPS_IP>` = oluşturulan sunucunun IPv4 adresi
**Dashed IP:** `<VPS_IP_DASHED>` = IP noktaları tire ile (örn: `5-75-170-184`)

---

## 2️⃣ VPS'TE KURULUM (SSH ile)

```bash
# 1. SSH bağlan
ssh root@<VPS_IP>

# 2. Setup scriptini çalıştır (tek seferlik)
cd /opt
git clone https://github.com/Leblepito/efloud-bot.git
cd efloud-bot

# 3. .env dosyalarını DÜZENLE (nano/vim ile) - secret'ları KENDİNİZ girin
nano .env.production
nano .env.production.long
nano .env.production.scalp

# 4. Caddyfile'ı VPS IP'siyle güncelle
sed -i "s/<VPS_IP_DASHED>/$(echo <VPS_IP> | tr '.' '-')/g" deploy/Caddyfile

# 5. Build & Deploy
docker compose -f docker-compose.prod.yml build efloud-bot
docker compose -f docker-compose.prod.yml up -d

# 6. Kontrol
docker compose -f docker-compose.prod.yml ps
docker compose -f docker-compose.prod.yml logs -f efloud-bot
```

---

## 3️⃣ DNS / CADDY AYARLARI

### Otomatik (nip.io - hızlı test için)
```
Dashboard:  http://<VPS_IP_DASHED>.nip.io
V2 Long:    http://v2.<VPS_IP_DASHED>.nip.io
V3 Scalp:   http://v3.<VPS_IP_DASHED>.nip.io
Panel:      http://panel.<VPS_IP_DASHED>.nip.io
```
Caddy otomatik Let's Encrypt sertifikası çıkarır (port 80/443 açık olmalı).

### Production (gerçek domainler - Cloudflare DNS)
Cloudflare dashboard'da A record ekleyin:
```
bot.ualgotrade.com     A   <VPS_IP>   Proxied: Yes
v2.u2algo.com          A   <VPS_IP>   Proxied: Yes
scalp.u2algo.com       A   <VPS_IP>   Proxied: Yes
bot.u2algo.com         A   <VPS_IP>   Proxied: Yes
```

---

## 4️⃣ BOT BAŞLATMA (KRİTİK - MANUEL)

**AUTOSTART=0** → Container up olduktan sonra **600 saniye (10 dk) içinde** dashboard'a girip **Start** basmalısınız. Aksi takdirde autoheal container'ı restart eder.

```
1. Tarayıcıda aç: https://bot.ualgotrade.com (veya nip.io adresi)
2. Şifre: .env.production dosyanızdaki DASHBOARD_PASSWORD değeri
3. "Positions" sekmesine git → BOŞ (flat) olduğunu DOĞRULA
   ⚠️ Eğer açık pozisyon varsa: leverage değişimi (5x→10x) likidasyon fiyatını değiştirir!
4. "Overview" sekmesine dön → ▶ Start butonuna bas
5. Healthz yeşil olmalı: https://bot.ualgotrade.com/api/healthz → {"status":"healthy",...}
```

---

## 5️⃣ V2 LONG + V3 SCALP (İsteğe Bağlı, Ayrı Onay)

Her bot ayrı Binance sub-account'ta, ayrı config ile:

```bash
# V2 Long
docker compose -f docker-compose.prod.yml up -d efloud-bot-long
# Dashboard: https://v2.u2algo.com → Start

# V3 Scalp
docker compose -f docker-compose.prod.yml up -d efloud-bot-scalp
# Dashboard: https://scalp.u2algo.com → Start
```

**Her birinde ayrı Start onayı gerekir.**

---

## 6️⃣ ROLLBACK PLANİ

Sorun olursa (anormal emir, loss limit, hata):

```bash
# 1. Acil durdur
docker compose -f docker-compose.prod.yml stop efloud-bot

# 2. Binance UI'dan pozisyonları manuel kapat / SL-TP koy

# 3. State backup
docker exec efloud-bot tar -czf /tmp/state_backup_$(date +%s).tar.gz /app/state_1k
docker cp efloud-bot:/tmp/state_backup_*.tar.gz ./

# 4. Log al
docker logs efloud-bot --since 4h > emergency_$(date +%s).log

# 5. Kod rollback (son bilinen iyi commit)
git reset --hard <commit_sha>
docker compose -f docker-compose.prod.yml build efloud-bot
docker compose -f docker-compose.prod.yml up -d efloud-bot
# Tekrar Start bas
```

---

## 7️⃣ HAZIRLIK DOSYALARI (Local'de Oluşturuldu)

| Dosya | Açıklama |
|-------|----------|
| `.env.production` | V1 Mainnet env (local copy) |
| `.env.production.long` | V2 Long Mainnet env |
| `.env.production.scalp` | V3 Scalp Mainnet env |
| `deploy/Caddyfile.template` | VPS IP placeholder'lı Caddyfile |
| `deploy/setup-server.sh` + `deploy/deploy.sh` | VPS kurulum + deploy scriptleri (bkz. `deploy/HETZNER_GUIDE.md`) |

**Bu dosyalar local'de** - VPS'ye kopyalayıp secret'ları düzenleyeceksiniz.

---

## 8️⃣ EXPORTS / GITHUB SECRETS (İleride CI/CD için)

GitHub repo settings → Secrets and variables → Actions:

```
HETZNER_API_TOKEN = <HETZNER_API_TOKEN>
DOCKER_HUB_TOKEN = <docker hub token jika push edecekseniz>
SUPABASE_DB_PASSWORD = <SUPABASE_DB_PASSWORD>
```

---

## 📋 ÖZET: SİZİN YAPMANIZ GEREKENLER

1. **Hetzner Console** → Yeni CPX21 VPS oluştur → IP not et
2. **SSH** → VPS'e bağlan → `deploy/HETZNER_GUIDE.md` adımlarını takip et (`deploy/setup-server.sh` + `deploy/deploy.sh`)
3. **`.env.production`** dosyalarını VPS'te **nano ile açıp secret'ları doğrula**
4. **Caddyfile**'da `<VPS_IP_DASHED>`'yi gerçek IP ile değiştir
5. **Build & Up** → `docker compose -f docker-compose.prod.yml up -d`
6. **Dashboard** aç → **Positions boş mu?** → **Start bas**
7. **Healthz** yeşil mi? → ✅ Canlı!

---

## ❌ EKSİK / BEKLEYEN DURUMLAR (orijinal taslaktan — güncel değil)

Bu tablo dosyanın ilk yazıldığı 2026-08-12 tarihindeki açık maddeleri listeler. Güncel
durum için `HETZNER_DEPLOYMENT_CHECKLIST.md`'ye bakın (VPS kuruldu, Binance API bağlı,
IP whitelist'e eklendi).

| Konu | O tarihteki durum |
|------|-------|
| Hetzner API Token | Geçersizdi (401) — manuel VPS oluşturuldu |
| VPS | Yoktu — 2026-09-25'te CPX21 (2.28.139.82) oluşturuldu |
| Binance IP Whitelist | Sunucu IP'si eklendi |
| Supabase DB şifresi | `.env`'e girildi |
| Gerçek Binance sub-account ayrımı | V1/V2/V3 için ayrı config dosyaları mevcut |
| config.phase2_long_1k.yaml / scalp_1k.yaml | VPS'te kullanımda |
| efloud-panel container | `docker-compose.prod.yml`'de tanımlı |

---

**Son durum:** VPS canlıda, Binance mainnet API bağlantısı doğrulandı (bkz.
`HETZNER_DEPLOYMENT_CHECKLIST.md`). Kullanıcı hesaba USDT transferi sonrası dashboard'dan
Start'a basacak.