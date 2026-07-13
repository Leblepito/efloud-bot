#!/bin/bash
# Cloudflare Tunnel Setup — Kalıcı Webhook URL
# ──────────────────────────────────────────────
# Bu script Cloudflare Tunnel ile sabit bir webhook URL oluşturur.
# Sandbox URL'i oturum değişiminde geçersiz olur; Cloudflare Tunnel kalıcıdır.
#
# Ön koşullar:
#   - Cloudflare hesabı (ücretsiz)
#   - cloudflared binary kurulu
#
# Kullanım:
#   bash /home/ubuntu/efloud-bot/ops/cloudflare_tunnel_setup.sh

set -e

echo "=== Cloudflare Tunnel Kurulum ==="
echo ""

# cloudflared kurulu mu?
if ! command -v cloudflared &> /dev/null; then
    echo "cloudflared kuruluyor..."
    curl -L --output /tmp/cloudflared.deb \
        https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64.deb
    sudo dpkg -i /tmp/cloudflared.deb
    echo "✅ cloudflared kuruldu"
else
    echo "✅ cloudflared zaten kurulu: $(cloudflared --version)"
fi

echo ""
echo "Webhook server çalışıyor mu kontrol ediliyor..."
if ! pgrep -f "ig_webhook_server.py" > /dev/null; then
    echo "⚠️  Webhook server çalışmıyor. Önce başlatın:"
    echo "   nohup python3 ~/efloud-bot/ops/ig_webhook_server.py > ~/ig_webhook.log 2>&1 &"
    exit 1
fi

echo "✅ Webhook server çalışıyor"
echo ""
echo "Cloudflare Quick Tunnel başlatılıyor (geçici, ücretsiz)..."
echo "Kalıcı tunnel için: cloudflared tunnel login"
echo ""

# Quick tunnel (kayıt gerektirmez, 24 saat geçerli)
cloudflared tunnel --url http://localhost:8765 &
TUNNEL_PID=$!
echo "Tunnel PID: $TUNNEL_PID"
echo ""
echo "URL birkaç saniye içinde görünecek..."
echo "Bu URL'i VPS publisher'daki WEBHOOK_URL değişkenine girin."
echo ""
echo "Kalıcı tunnel için:"
echo "  1. cloudflared tunnel login"
echo "  2. cloudflared tunnel create u2algo-webhook"
echo "  3. cloudflared tunnel route dns u2algo-webhook webhook.u2algo.com"
echo "  4. cloudflared tunnel run u2algo-webhook"
