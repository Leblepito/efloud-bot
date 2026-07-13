# u2Algo Sosyal Medya Sistemi

## Mimari

```
VPS (sabit IP)                    Manus Sandbox (değişken URL)
─────────────────                 ──────────────────────────────
u2algo_publisher.py               ig_webhook_server.py (port 8765)
        │                                   │
        │ POST /webhook                     │ tweet → X (Twitter)
        └──────────────────────────────────►│ queue → ~/ig_pending/
                                            │
                                   ig_sandbox_poller.py (zamanlanmış)
                                            │
                                            │ manus-mcp-cli
                                            └──────────────► Instagram
```

## Dosyalar

| Dosya | Konum | Açıklama |
|-------|-------|----------|
| `ig_webhook_server.py` | `ops/` | FastAPI webhook server (port 8765) |
| `ig_sandbox_poller.py` | `ops/` | Instagram kuyruk işleyici |
| `vps_webhook_forwarder.py` | `ops/` | VPS'te çalışan sabit URL proxy |
| `sandbox_setup.sh` | `ops/` | Sandbox sıfırlanınca sistemi yeniden kurar |
| `cloudflare_tunnel_setup.sh` | `ops/` | Cloudflare Tunnel kurulumu |
| `x_tokens.example.json` | `ops/` | X API token şablonu |

## Kurulum

### 1. Sandbox'ta (Manus)

```bash
# Repo klonla
gh repo clone Leblepito/efloud-bot
cd efloud-bot

# Bağımlılıkları kur
sudo pip3 install fastapi uvicorn tweepy python-multipart

# X token bilgilerini gir
cp ops/x_tokens.example.json ~/x_tokens.json
nano ~/x_tokens.json  # Gerçek değerleri gir

# Webhook server'ı başlat
nohup python3 ops/ig_webhook_server.py > ~/ig_webhook.log 2>&1 &

# Sembolik linkler (geriye dönük uyumluluk)
ln -sfn ~/ig_pending /tmp/ig_pending
ln -sfn ~/ig_done /tmp/ig_done
```

### 2. VPS'te (Kalıcı URL için)

```bash
# Forwarder'ı kur
pip3 install fastapi uvicorn requests
cp ops/vps_webhook_forwarder.py /opt/u2algo/

# Manus URL'ini ayarla
export MANUS_WEBHOOK_URL="https://8765-XXXX.sg1.manus.computer/webhook"

# Başlat
nohup python3 /opt/u2algo/vps_webhook_forwarder.py > /var/log/u2algo-forwarder.log 2>&1 &
```

**VPS publisher'daki webhook URL'ini forwarder URL'ine değiştirin:**
```
WEBHOOK_URL = "http://localhost:8766/webhook"  # veya VPS IP:8766
```

**Sandbox URL değiştiğinde forwarder'ı güncelle:**
```bash
curl -X POST http://VPS_IP:8766/update-url \
  -H "Content-Type: application/json" \
  -d '{"url": "https://YENİ-URL.sg1.manus.computer/webhook"}'
```

## Token Yönetimi

### X (Twitter) Tokens

Öncelik sırası:
1. Ortam değişkenleri: `X_API_KEY`, `X_API_SECRET`, `X_ACCESS_TOKEN`, `X_ACCESS_TOKEN_SECRET`
2. Dosya: `~/x_tokens.json`

### Instagram

Instagram paylaşımları Manus MCP üzerinden yapılır. Ek token gerekmez.

## Zamanlanmış Görev

Manus'ta saatlik zamanlanmış görev:
```
Instagram paylaşım kuyruğunu kontrol et ve bekleyen paylaşımları yayınla.
~/ig_pending/ klasöründeki JSON dosyalarını oku, her biri için Instagram MCP ile yayınla,
tamamlananları ~/ig_done/ klasörüne taşı.
Script: /home/ubuntu/efloud-bot/ops/ig_sandbox_poller.py
```

## Sandbox Sıfırlanınca

```bash
bash ~/efloud-bot/ops/sandbox_setup.sh
```

Bu script:
1. Repo'yu günceller
2. Python paketlerini kontrol eder
3. `~/ig_pending` ve `~/ig_done` dizinlerini oluşturur
4. `/tmp/ig_pending` ve `/tmp/ig_done` sembolik linklerini oluşturur
5. Webhook server'ı başlatır

## SPK Uyarısı

Tüm paylaşımlara otomatik eklenir:
> ⚠️ Bu içerik yatırım tavsiyesi değildir. SPK Tebliğ III-37.1 kapsamında bilgilendirme amaçlıdır.

## Limitler

- X (Twitter): Aylık 1000 tweet (Pay-Per-Use plan)
- Dedup: Aynı bot+sembol+yön kombinasyonu 1 saat içinde tekrar paylaşılmaz
