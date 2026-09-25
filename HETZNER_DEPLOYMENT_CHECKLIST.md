# Hetzner Deployment Checklist — efloud-bot

**Tarih:** 2026-09-25  
**Sunucu:** efloud-bot-prod (2.28.139.82)  
**Status:** ✅ Deployed & Running

---

## ✅ Tamamlanan Adımlar

- [x] Hetzner CPX21 sunucusu oluşturuldu (Ubuntu 24.04)
- [x] SSH anahtarı (efloud-bot-hetzner) eklenmiş
- [x] `deploy/setup-server.sh` çalıştırıldı (Docker, UFW, fail2ban)
- [x] Repo `/opt/efloud-bot` altına klonlandı
- [x] `.env.production*` dosyaları oluşturuldu (placeholder'lar dolduruldu)
- [x] `deploy/deploy.sh` çalıştırıldı (build + up)
- [x] 8 container başlatıldı (tümü healthy)
- [x] Caddyfile güncellendi (2-28-139-82.nip.io)
- [x] `/healthz` endpoint doğrulandı (200 OK)
- [x] Dashboard frontend erişilebilir

---

## ⏳ Yapılması Gerekenler (Kullanıcı)

### 1. Binance API Key Ekle
```bash
ssh root@2.28.139.82
nano /opt/efloud-bot/.env.production
# BINANCE_API_KEY ve BINANCE_API_SECRET'ı doldur
# Ctrl+O, Enter, Ctrl+X ile kaydet

# ÖNEMLİ: "restart" .env dosyasındaki değişiklikleri YENİDEN OKUMAZ (Docker Compose
# env_file davranışı). Container'ı yeni env ile başlatmak için "up -d --force-recreate"
# kullanılmalı:
docker compose -f docker-compose.prod.yml up -d --force-recreate efloud-bot
```

### 2. Binance API Whitelist'ine IP Ekle
- Binance → API Management → IP Whitelist
- `2.28.139.82` ekle

### 3. Dashboard'dan Bot'u Başlat
- https://2-28-139-82.nip.io
- Şifre: `/opt/efloud-bot/.env.production` içindeki `DASHBOARD_PASSWORD` değeri (sunucuda `grep DASHBOARD_PASSWORD .env.production` ile bak, buraya yazma)
- "▶ Start" butonuna bas

---

## 📊 Sunucu Bilgileri

| Bilgi | Değer |
|-------|-------|
| IP | 2.28.139.82 |
| Hostname | efloud-bot-prod |
| OS | Ubuntu 24.04 LTS |
| Docker | 29.8.1 |
| Caddy | 2-alpine |

---

## 🔐 Dashboard URLs

| Bot | URL |
|-----|-----|
| V1 (Mid) | https://2-28-139-82.nip.io |
| V2 (Long) | https://v2.2-28-139-82.nip.io |
| V3 (Scalp) | https://v3.2-28-139-82.nip.io |
| Panel | https://panel.2-28-139-82.nip.io |

**Login Password**: `.env.production` dosyasındaki `DASHBOARD_PASSWORD` (bkz. yukarıdaki not — repo'ya asla düz metin yazılmaz)

---

## 🔍 Sağlık Kontrolleri

```bash
# Container durumu
ssh root@2.28.139.82
docker compose -f docker-compose.prod.yml ps

# Bot healthz
curl -s -k https://2-28-139-82.nip.io/healthz

# Logs
docker logs efloud-bot
docker logs efloud-caddy
```

---

## 📝 Notlar

- EFLOUD_AUTOSTART=0 → Bot suspended başlar, dashboard'dan Start basılmalı
- Caddy self-signed sertifika kullanıyor (nip.io ACME validation'ı geçemez)
- UFW firewall: SSH (22), HTTP (80), HTTPS (443) açık
- fail2ban: SSH brute-force koruması aktif
- `.env.production*` içinde değişiklik yaptıktan sonra `restart` DEĞİL, `up -d --force-recreate <servis>` kullan (bkz. Adım 1)
- Binance API key/secret girildi ve gerçek imzalı istekle doğrulandı (2026-09-25) — bağlantı sağlıklı

---

**Sunucu tamamen hazır. Binance API key'lerini ekledikten sonra trading başlayabilir.**
