#!/bin/bash
# u2Algo Sandbox Setup Script
# ────────────────────────────
# Sandbox sıfırlandıktan sonra sistemi yeniden kurar.
# Manus zamanlanmış görev veya manuel çalıştırma ile kullanılır.
#
# Kullanım:
#   bash /home/ubuntu/efloud-bot/ops/sandbox_setup.sh

set -e
REPO_DIR="$HOME/efloud-bot"
LOG="$HOME/sandbox_setup.log"

echo "[$(date)] Sandbox setup başlıyor..." | tee -a "$LOG"

# 1. Repo güncel mi?
if [ ! -d "$REPO_DIR" ]; then
    echo "[$(date)] Repo klonlanıyor..." | tee -a "$LOG"
    cd "$HOME"
    gh repo clone Leblepito/efloud-bot
else
    echo "[$(date)] Repo mevcut, pull yapılıyor..." | tee -a "$LOG"
    cd "$REPO_DIR"
    git pull --ff-only 2>/dev/null || echo "Pull başarısız, devam ediliyor..."
fi

# 2. Gerekli Python paketleri
echo "[$(date)] Python paketleri kontrol ediliyor..." | tee -a "$LOG"
python3 -c "import fastapi, uvicorn, tweepy" 2>/dev/null || \
    sudo pip3 install fastapi uvicorn tweepy python-multipart 2>&1 | tail -3 | tee -a "$LOG"

# 3. Kalıcı dizinler
mkdir -p "$HOME/ig_pending" "$HOME/ig_done"
echo "[$(date)] Dizinler hazır: ~/ig_pending, ~/ig_done" | tee -a "$LOG"

# 4. Sembolik linkler (eski /tmp/ yolları için geriye dönük uyumluluk)
ln -sfn "$HOME/ig_pending" /tmp/ig_pending 2>/dev/null || true
ln -sfn "$HOME/ig_done" /tmp/ig_done 2>/dev/null || true

# 5. Webhook server çalışıyor mu?
if pgrep -f "ig_webhook_server.py" > /dev/null; then
    echo "[$(date)] Webhook server zaten çalışıyor." | tee -a "$LOG"
else
    echo "[$(date)] Webhook server başlatılıyor..." | tee -a "$LOG"
    nohup python3 "$REPO_DIR/ops/ig_webhook_server.py" > "$HOME/ig_webhook.log" 2>&1 &
    sleep 2
    if pgrep -f "ig_webhook_server.py" > /dev/null; then
        echo "[$(date)] ✅ Webhook server başlatıldı (port 8765)" | tee -a "$LOG"
    else
        echo "[$(date)] ❌ Webhook server başlatılamadı!" | tee -a "$LOG"
    fi
fi

# 6. x_tokens.json var mı?
if [ -f "$HOME/x_tokens.json" ]; then
    echo "[$(date)] ✅ x_tokens.json mevcut" | tee -a "$LOG"
else
    echo "[$(date)] ⚠️  x_tokens.json eksik — X tweet atılamayacak" | tee -a "$LOG"
    echo "[$(date)] Oluşturuluyor (boş şablon)..." | tee -a "$LOG"
    cat > "$HOME/x_tokens.json" << 'EOF'
{
  "consumer_key": "",
  "consumer_secret": "",
  "access_token": "",
  "access_token_secret": ""
}
EOF
fi

echo "[$(date)] ✅ Sandbox setup tamamlandı." | tee -a "$LOG"
echo ""
echo "Webhook URL'i VPS publisher'a ekleyin:"
echo "  Sandbox URL değişiyor — kalıcı URL için Cloudflare Tunnel kullanın."
echo "  Geçici URL almak için: manus-expose 8765"
