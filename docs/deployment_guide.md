# 🌐 Efloud-bot Cloud Migration & Otonom Deployment Kılavuzu
# ══════════════════════════════════════════════════════════════════
# Son Güncelleme: 2026-05-26 | Model: Gemini 3.5 Flash (SMR Orkestratör)
# Platformlar: Hetzner VPS, Supabase, Railway, NousResearch/hermes-agent
# ──────────────────────────────────────────────────────────────────

Bu kılavuz, Efloud-bot'un Hetzner VPS ve Supabase üzerindeki entegrasyonunu tamamlamak ve `NousResearch/hermes-agent` ile Railway üzerinden tüm projeyi otonom şekilde yönetmek için gerekli mimari kurulum adımlarını sunar.

---

## 🏛️ 1. Supabase Entegrasyonu & Postgres Hata Çözümü

### 🔍 Hata Analizi: "Tenant or user not found" (Supavisor)
`.env` dosyasındaki default connection URL'de Supavisor pooler (port 6543) üzerinden bağlanırken bu hatanın alınması, Supabase'in yeni router katmanında proje referansının (Project Ref) connection string parametrelerinde açıkça belirtilmemesinden kaynaklanır.

### 🛠️ Kesin Çözüm: `.env` Dosyası Güncellemesi
Supavisor (Transaction Pooler) için bağlantı parametresine proje referansı (`options=project%3D<project-ref>`) parametresini ekleyiniz:

```properties
# Eski (Hatalı) Bağlantı:
# DATABASE_URL=postgresql://postgres.okimvywmhcwbtwtegyjm:Leblepito_2026!@aws-0-eu-central-1.pooler.supabase.com:6543/postgres

# Yeni (Çözülmüş) Bağlantı:
DATABASE_URL=postgresql://postgres.okimvywmhcwbtwtegyjm:Leblepito_2026!@aws-0-eu-central-1.pooler.supabase.com:6543/postgres?options=project%3Dokimvywmhcwbtwtegyjm
```

> [!TIP]
> **Direct Connection Alternatifi:** Eğer pooler yerine doğrudan PostgreSQL sunucusuna bağlanmak isterseniz (port 5432) şu URL'i kullanabilirsiniz:
> `DATABASE_URL=postgresql://postgres:Leblepito_2026!@db.okimvywmhcwbtwtegyjm.supabase.co:5432/postgres`

### 📊 Otonom Sonuç Senkronizasyonu (`sync_optimization_to_supabase.py`)
Yazılan otonom senkronizasyon betiği, yereldeki TSV dosyasını (`reports/optimization/results.tsv`) okuyarak tüm parametre optimizasyonu sonuçlarını Supabase üzerindeki `strategy_optimization_results` tablosuna otomatik olarak yazar. Tablo şeması otomatik olarak oluşturulur ve duplicate kayıtları önlemek için UNIQUE kısıtı (`unique_strategy_opt`) kullanılır.

---

## 🔧 2. Hetzner VPS Otonom Docker Yönetimi (SSH & CLI)

Efloud-bot production ortamında Hetzner VPS üzerinde Docker Compose ile çalışmaktadır. `hermes-agent`'ın bu sunucuyu uzaktan güvenli ve otonom bir şekilde yönetebilmesi için SSH anahtarlarının kurulması ve `.env` üzerinden entegrasyonu gerekir.

### 🔑 SSH Entegrasyonu (.env)
Ajanın sunucuya şifresiz bağlanabilmesi için Railway üzerinde çalışacak `hermes-agent` environment değişkenlerine Hetzner SSH özel anahtarını (Private Key) Base64 veya doğrudan string olarak besleyebilirsiniz:

```properties
# Hetzner VPS Erişim Bilgileri
HETZNER_VPS_IP=95.217.xx.xx
HETZNER_SSH_USER=root
HETZNER_SSH_KEY="-----BEGIN OPENSSH PRIVATE KEY-----\nMIIEogIBAAKCAQE...\n-----END OPENSSH PRIVATE KEY-----"
```

### 🤖 Otonom Deployment Scripti (`scripts/deploy_remote.py`)
`hermes-agent` bu scripti çalıştırarak Hetzner sunucusuna bağlanır, güncel kodları çeker, testleri koşturur ve production docker container'larını yeniden başlatır:

```python
# Ajanın remote deployment için koşturacağı otonom komut zinciri:
"""
ssh -i /tmp/hetzner_key root@$HETZNER_VPS_IP << 'EOF'
    cd /opt/efloud-bot
    git pull origin main
    docker-compose -f docker-compose.prod.yml down
    docker-compose -f docker-compose.prod.yml up -d --build
    docker ps
EOF
"""
```

---

## 🤖 3. Railway Üzerinde `NousResearch/hermes-agent` Kurulumu

`NousResearch/hermes-agent`, projenizi arka planda izlemek, Telegram'dan gelen komutları yorumlamak ve `optimize_strategy.py` gibi otonom optimize döngülerini çalıştırmak için mükemmel bir **Super Orchestrator** görevi görür.

### 📦 Dockerfile & s6-overlay Yapısı
Hermes Agent, çoklu servislerin (FastAPI, LLM Proxy ve Cron Jobs) tek bir container içinde çalışabilmesi için `s6-overlay` mimarisini kullanır. Railway üzerinde sıfır sorunla deploy edilebilmesi için şu adımları takip edin:

1. **Port Yapılandırması:**
   Hermes Agent dahili olarak `:8080` portundan yayın yapar. Railway dashboard'unda `PORT=8080` environment değişkenini tanımlayın.

2. **Environment Değişkenleri (Railway Variable Mapping):**
   Railway panelinde Efloud projesindeki `.env` değişkenlerinin aynısını tanımlayın. Özellikle şunlar zorunludur:
   * `GEMINI_API_KEY` (Hermes'in akıl yürütmesi için)
   * `DATABASE_URL` (Supabase Postgres entegrasyonu için)
   * `BINANCE_API_KEY` & `BINANCE_API_SECRET`
   * `EFLOUD_ALLOW_MAINNET=1` (Sadece Hermes insan onayından sonra bypass edilir)

3. **Remote Sunucu Yönetimi (Hetzner Kontrolü):**
   Hermes Agent içerisindeki otonom döngülere (cron jobs) `python -m scripts.optimize_strategy --iterations 5` tetikleyici komutunu ekleyerek haftalık otonom backtest aramaları gerçekleştirebilir ve en iyi aday konfigürasyonu Supabase'e yazabilirsiniz.

---

## 🎯 4. Otonom İş Akışı (Orkestrasyon Şeması)

```mermaid
graph TD
    Railway[Railway: Hermes Agent] -->|1. Otonom Tetikleme: cron/manual| Opt[scripts/optimize_strategy.py]
    Opt -->|2. Subprocess Backtest| Backtest[backtest.cli portfolio]
    Backtest -->|3. Kayıt Sonuçları| TSV[reports/optimization/results.tsv]
    Opt -->|4. Sync Tetikleyici| Sync[scripts/sync_optimization_to_supabase.py]
    Sync -->|5. Tablo Yazımı / Upsert| Supabase[Supabase Postgres]
    
    Railway -->|6. SSH & Docker-Compose CMD| Hetzner[Hetzner VPS: Live Bot]
    Hetzner -->|7. Canlı Emirler| Binance[Binance Futures API]
```

Bu otonom döngü sayesinde:
1. **Veri Güvenliği:** Backtest ve optimizasyon sonuçları asla kaybolmaz, Supabase'de tarihsel olarak arşivlenir.
2. **Sıfır Risk:** Canlı bot (`Hetzner`) kesintiye uğramadan, tüm optimizasyon ve AI akıl yürütme yükü `Railway` üzerinde izole şekilde çalışır.
3. **Maksimum Performans:** En iyi konfigürasyon adayı Supabase ve TSV üzerinde raporlandığında, Utku dashboard üzerinden tek tıkla onay vererek Hetzner'deki canlı botu güncelleyebilir.
