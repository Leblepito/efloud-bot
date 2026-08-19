#!/bin/bash
# Efloud-bot VPS Setup Script
# Run on fresh Hetzner VPS (Ubuntu 22.04) as root
# Usage: curl -sSL <url> | bash  OR  copy-paste this script

set -euo pipefail

echo "🚀 Efloud-bot VPS Setup Starting..."

# 1. System update & Docker install
apt-get update && apt-get upgrade -y
apt-get install -y ca-certificates curl gnupg lsb-release git

# Docker official repo
install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | gpg --dearmor -o /etc/apt/keyrings/docker.gpg
chmod a+r /etc/apt/keyrings/docker.gpg
echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu $(lsb_release -cs) stable" | tee /etc/apt/sources.list.d/docker.list > /dev/null
apt-get update
apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin

# 2. Clone repo
cd /opt
git clone https://github.com/Leblepito/efloud-bot.git
cd efloud-bot

# 3. Create .env.production files (you'll edit these with real secrets)
cat > .env.production << 'EOF'
# Efloud Bot — Production Environment (MAINNET)
# ⚠️ BU DOSYA GERÇEK PARA İÇİN KULLANILIR - COMMIT ETMEYİN

# ── Binance Mainnet API ──
BINANCE_API_KEY=HmlBkphS59Y9yk5JVvfr8qtAeuXPYNiFrItqzzvHw3b9zxaDF
BINANCE_API_SECRET=aMQTHV9EhbGWFsD
EFLOUD_ALLOW_MAINNET=1

# ── Config ──
EFLOUD_CONFIG_PATH=configs/config.phase2_1k.yaml

# ── Bot Lifecycle ──
EFLOUD_AUTOSTART=0
EFLOUD_AUTO_MIGRATE=1

# ── Web Platform ──
DASHBOARD_PASSWORD=<DASHBOARD_PASSWORD_GIRIN>
SESSION_SECRET=<SESSION_SECRET_32_CHARS_GIRIN>

# ── Supabase Postgres (Connection Pooler - port 6543) ──
DATABASE_URL=postgresql://postgres:<SUPABASE_DB_PASSWORD>@<SUPABASE_POOLER_HOST>:6543/postgres

# ── CORS ──
ALLOWED_ORIGINS=https://bot.ualgotrade.com,https://bot.u2algo.com,https://scalp.u2algo.com

# ── Environment ──
ENV=production
LOG_LEVEL=INFO

# ── Social Publishing (disabled by default) ──
SOCIAL_CONTENT_ENABLED=0
SOCIAL_AUTOPILOT=0
SOCIAL_LANGS=en,ru
SOCIAL_PLATFORMS=x

# ── Peer bots (for routines container) ──
EFLOUD_PEER_BOTS=mid=http://efloud-bot:8080,long=http://efloud-bot-long:8080,scalp=http://efloud-bot-scalp:8080

# ── Kronos (disabled) ──
KRONOS_SYMBOLS=BTC,ETH,SOL
KRONOS_RUNS_PER_LAYER=3
KRONOS_OUTPUT_PATH=data/market/kronos_cascade.json

# ── X/Twitter (disabled) ──
X_API_ENABLED=false

# ── Instagram (disabled) ──
INSTAGRAM_ENABLED=false
EOF

cat > .env.production.long << 'EOF'
# Efloud Bot V2 Long — Production Environment (MAINNET)
# ⚠️ BU DOSYA GERÇEK PARA İÇİN KULLANILIR - COMMIT ETMEYİN

# ── Binance Mainnet API (V2 Long sub-account) ──
BINANCE_API_KEY=HmlBkphS59Y9yk5JVvfr8qtAeuXPYNiFrItqzzvHw3b9zxaDF
BINANCE_API_SECRET=aMQTHV9EhbGWFsD
EFLOUD_ALLOW_MAINNET=1

# ── Config ──
EFLOUD_CONFIG_PATH=configs/config.phase2_long_1k.yaml

# ── Bot Identity ──
EFLOUD_BOT_ID=v2-long

# ── Bot Lifecycle ──
EFLOUD_AUTOSTART=0
EFLOUD_AUTO_MIGRATE=1

# ── Web Platform ──
DASHBOARD_PASSWORD=<DASHBOARD_PASSWORD_GIRIN>
SESSION_SECRET=<SESSION_SECRET_32_CHARS_GIRIN>

# ── Supabase Postgres ──
DATABASE_URL=postgresql://postgres:<SUPABASE_DB_PASSWORD>@<SUPABASE_POOLER_HOST>:6543/postgres

# ── CORS ──
ALLOWED_ORIGINS=https://bot.ualgotrade.com,https://bot.u2algo.com,https://scalp.u2algo.com

# ── Environment ──
ENV=production
LOG_LEVEL=INFO
EOF

cat > .env.production.scalp << 'EOF'
# Efloud Bot V3 Scalp — Production Environment (MAINNET)
# ⚠️ BU DOSYA GERÇEK PARA İÇİN KULLANILIR - COMMIT ETMEYİN

# ── Binance Mainnet API (V3 Scalp sub-account) ──
BINANCE_API_KEY=HmlBkphS59Y9yk5JVvfr8qtAeuXPYNiFrItqzzvHw3b9zxaDF
BINANCE_API_SECRET=aMQTHV9EhbGWFsD
EFLOUD_ALLOW_MAINNET=1

# ── Config ──
EFLOUD_CONFIG_PATH=configs/config.phase2_scalp_1k.yaml

# ── Bot Identity ──
EFLOUD_BOT_ID=v3-scalp

# ── Bot Lifecycle ──
EFLOUD_AUTOSTART=0
EFLOUD_AUTO_MIGRATE=1

# ── Web Platform ──
DASHBOARD_PASSWORD=<DASHBOARD_PASSWORD_GIRIN>
SESSION_SECRET=<SESSION_SECRET_32_CHARS_GIRIN>

# ── Supabase Postgres ──
DATABASE_URL=postgresql://postgres:<SUPABASE_DB_PASSWORD>@<SUPABASE_POOLER_HOST>:6543/postgres

# ── CORS ──
ALLOWED_ORIGINS=https://bot.ualgotrade.com,https://bot.u2algo.com,https://scalp.u2algo.com

# ── Environment ──
ENV=production
LOG_LEVEL=INFO
EOF

echo "✅ .env files created. Now building Docker image..."

# 4. Build & start
docker compose -f docker-compose.prod.yml build efloud-bot
docker compose -f docker-compose.prod.yml up -d

echo "✅ VPS Setup Complete!"
echo ""
echo "📋 NEXT STEPS:"
echo "1. Check containers: docker compose -f docker-compose.prod.yml ps"
echo "2. Check logs: docker compose -f docker-compose.prod.yml logs -f efloud-bot"
echo "3. Open dashboard: http://<VPS_IP>  (Caddy serves on port 80/443)"
echo "4. Login with the DASHBOARD_PASSWORD you set in .env.production"
echo "5. Press 'Start' button (within 10 min) to begin trading"
echo ""
echo "⚠️  IMPORTANT: Verify NO open positions before pressing Start if leverage changed!"