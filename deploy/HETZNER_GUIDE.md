# Hetzner Cloud Deployment Guide — efloud-bot

Hedef: Avrupa lokasyonlu bir Hetzner Cloud sunucusunda bot'u 7/24 mainnet'te çalıştırmak. Toplam süre: ~30-45 dk.

## Maliyet
- **CX22** (2 vCPU, 4 GB RAM, 40 GB SSD) — €4.51/ay (~$5)
- IPv4 dahil (Binance API IP whitelist için kritik)
- Lokasyon: Falkenstein/Nürnberg (Almanya) veya Helsinki (Finlandiya) — hepsi Binance'e uygun

---

## 1. Hetzner Hesap Açılışı

1. https://accounts.hetzner.com/signUp — email, ad, soyad, adres ile kayıt
2. Email doğrula
3. Ödeme yöntemi ekle (kredi kartı veya PayPal — Hetzner küçük bir doğrulama tutarı çekip iade edebilir)
4. **Hetzner Cloud Console** aç: https://console.hetzner.cloud

> ℹ️ İlk kez kullanıcılar için Hetzner kimlik doğrulama isteyebilir (pasaport/kimlik fotoğrafı). 1-2 saat sürer.

---

## 2. SSH Anahtarı Oluştur (Windows local)

PowerShell'de:

```powershell
# Eğer ~/.ssh/id_ed25519 yoksa oluştur
ssh-keygen -t ed25519 -C "efloud-bot-hetzner" -f $env:USERPROFILE\.ssh\id_ed25519
# Passphrase iste — boş bırakabilirsin (otomatik script için pratik) veya güçlü passphrase gir

# Public key'i panoya kopyala
Get-Content $env:USERPROFILE\.ssh\id_ed25519.pub | Set-Clipboard
```

Hetzner Console → **Security** → **SSH Keys** → **Add SSH Key** → Yapıştır → İsim: `utkuc-windows`

---

## 3. Server Oluştur

Hetzner Console → **Servers** → **Add Server**

| Ayar | Değer |
|---|---|
| Location | **Falkenstein** (Almanya) — ya da Nürnberg/Helsinki, fark etmez |
| Image | **Ubuntu 24.04** |
| Type | **Standard → CX22** (€4.51/ay) |
| Networking | IPv4 ve IPv6 ikisi de açık (default) |
| SSH Keys | Az önce eklediğin `utkuc-windows` seç |
| Volumes | Yok |
| Firewalls | Yok (UFW'yi sunucuda kuracağız) |
| Backups | İsteğe bağlı (€0.90/ay — önerilir ama atlayabilirsin) |
| Placement Group | Yok |
| Labels | İsteğe bağlı |
| Cloud Config | Boş bırak |
| Name | `efloud-bot-prod` |

**Create & Buy now** → 30 saniye içinde sunucu hazır.

Server detail sayfasında **Public IPv4** adresini not et. Örnek: `123.45.67.89`

---

## 4. Sunucuya Bağlan + Bootstrap

PowerShell'de:

```powershell
# IPv4 adresini değiştir
ssh root@123.45.67.89
# İlk bağlantıda fingerprint sorar → "yes"
```

Sunucu içinde, repo'daki bootstrap script'i çalıştır:

```bash
# setup-server.sh dosyasını kopyala (3 yöntemden biri):

# Yöntem A — GitHub'dan (repo public ise):
curl -fsSL https://raw.githubusercontent.com/Leblepito/efloud-bot/feature/web-platform/deploy/setup-server.sh -o setup.sh
bash setup.sh

# Yöntem B — Lokalden scp ile (PowerShell, ÖNCE local'den):
# scp c:/Users/utkuc/Downloads/efloud-bot/deploy/setup-server.sh root@123.45.67.89:/root/setup.sh
# Sonra sunucuda: bash /root/setup.sh

# Yöntem C — Repo'yu önce klonla, sonra script'i çalıştır:
apt-get update -y && apt-get install -y git
git clone https://github.com/Leblepito/efloud-bot.git -b feature/web-platform /opt/efloud-bot
bash /opt/efloud-bot/deploy/setup-server.sh
```

Script otomatik yapacaklar:
- System update
- Docker + Compose plugin install
- UFW firewall (sadece 22 SSH + 8080 dashboard açık)
- fail2ban (SSH brute-force koruması)
- `efloud` kullanıcısı oluştur, docker grubuna ekle
- `/opt/efloud-bot` dizini hazırla

Script biterken sunucunun **public IPv4'ünü** ekrana basar — bunu **Binance API key whitelist'ine eklemen gerekiyor** (Adım 6).

---

## 5. Repo'yu Klonla + Env Doldur

Sunucuda hâlâ root iken:

```bash
# efloud kullanıcısına geç
su - efloud
cd /opt

# Eğer setup.sh "Yöntem C" ile zaten klonlamadıysa:
git clone https://github.com/Leblepito/efloud-bot.git efloud-bot
cd efloud-bot
git checkout feature/web-platform

# Env dosyasını hazırla
cp deploy/.env.production.example .env.production
nano .env.production
```

`.env.production` içinde doldurulacaklar:
- `BINANCE_API_KEY`, `BINANCE_API_SECRET` — Mainnet key (mevcut)
- `DASHBOARD_PASSWORD` — güçlü password (lokal'de kullandığın `efloud-test-12345`'ten farklı, en az 16 karakter)
- `SESSION_SECRET` — `openssl rand -hex 32` ile üret, kopyala
- `ALLOWED_ORIGINS=https://<hyphenated_ip>.nip.io` — IP'nin noktalarını tireyle değiştir (örn `178.104.122.91` → `178-104-122-91.nip.io`). Caddy bu hostname için Let's Encrypt cert otomatik alır.

Kaydet: `Ctrl+O`, `Enter`, `Ctrl+X`

---

## 6. Binance API Key Whitelist Güncelle

⚠️ **Bu adım kritik — atlama**, Binance -2015 hatası alırsın.

1. Binance → Profile → API Management → Mevcut mainnet key → **Edit restrictions**
2. **Restrict access to trusted IPs only** kısmına git
3. Sunucunun yeni IPv4'ünü ekle (örn: `123.45.67.89`)
4. Eski IP'lerini (lokal makinen) silebilirsin veya bırakabilirsin (lokal test için bırakman önerilir)
5. Save

Binance "5 dk içinde aktif olur" der ama genelde anında.

---

## 7. Deploy

Sunucuda:

```bash
cd /opt/efloud-bot
bash deploy/deploy.sh
```

Script şunları yapar:
1. `git pull` (zaten son halse no-op)
2. `docker compose build` — frontend Next.js build + Python image (3-5 dk ilk kez)
3. `docker compose up -d` — container'ı başlat
4. `/healthz` endpoint'ini bekle (60 sn)

Başarılı çıktı:
```
✅ Bot is up and healthy
{"status":"ok","bot_running":false,"subscribers":0}
```

> `bot_running:false` doğrudur — `EFLOUD_AUTOSTART=0` olduğu için bot stopped başlar, dashboard'dan başlatacağız.

---

## 8. Dashboard'a Bağlan + İlk Cycle

Caddy reverse-proxy compose'da hazır geldiği için ilk `deploy.sh` çalıştığında HTTPS otomatik kurulur (Let's Encrypt cert ~30s içinde alınır).

1. Browser'da aç: `https://<hyphenated_ip>.nip.io` (örn `https://178-104-122-91.nip.io`)
2. Login: `.env.production`'daki `DASHBOARD_PASSWORD`
3. Top bar → **Start** butonu → Bot başlasın
4. Status grid'de `running: true`, `cycle_count` artmalı
5. Watchlist'te 10 coin görünmeli (BTC, ETH, XRP, DOGE, SOL, BNB, TRX, LINK, BCH, ADA)

> Bot container'ı `expose: 8080` ile internal-only; dış dünya sadece Caddy üzerinden 443'e bağlanır. Cookie `Secure` flag aktif (HTTPS-only).

---

## 9. (Opsiyonel) Kendi Domain'in

`nip.io` ücretsiz ve sınırsız çalışır ama `https://178-104-122-91.nip.io` gibi görünür.
Kendi domain'in (örn `bot.example.com`) varsa:

1. DNS A kaydı: `bot.example.com` → sunucu IPv4
2. `deploy/Caddyfile`'da hostname'i değiştir
3. `.env.production` → `ALLOWED_ORIGINS=https://bot.example.com`
4. `bash deploy/deploy.sh` ile yeniden başlat — Caddy yeni cert'i otomatik alır

---

## 10. Bakım Komutları

```bash
# Log tail (canlı)
docker compose -f docker-compose.prod.yml logs -f --tail=100

# Restart
docker compose -f docker-compose.prod.yml restart

# Update (yeni commit pull + rebuild + restart)
bash deploy/deploy.sh

# Stop
docker compose -f docker-compose.prod.yml down

# Container içine gir
docker compose -f docker-compose.prod.yml exec efloud-bot bash

# Disk kullanımı
df -h
docker system df
```

---

## Troubleshooting

| Sorun | Çözüm |
|---|---|
| Dashboard `:8080` açılmıyor | UFW: `sudo ufw status` — 8080 allow olduğunu doğrula. Container down ise `docker compose ps` |
| Login başarısız | `.env.production`'daki `DASHBOARD_PASSWORD`'u doğrula. 5 hatalı denemeden sonra 15 dk lock. Restart: `docker compose restart` |
| Binance -2015 Invalid API-key | IP whitelist'te sunucu IPv4 var mı? Binance UI'dan kontrol et |
| Binance -451 region | Hetzner sunucusu Avrupa'da değilse (US lokasyonu seçtiysen). Falkenstein/Nürnberg/Helsinki seç |
| Container restart loop | `docker compose logs --tail=200` — genelde env var eksikliği veya CCXT auth hatası |

---

## Maliyet Özeti
- Hetzner CX22: **€4.51/ay** (~$5)
- (Opsiyonel) Backup: €0.90/ay
- (Opsiyonel) Domain: ~$10/yıl
- **Toplam minimum: ~$5/ay**
