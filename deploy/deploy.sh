#!/usr/bin/env bash
# Efloud Bot — Hetzner deploy / update script
# Run from /opt/efloud-bot as user `efloud` (member of docker group)

set -euo pipefail

cd "$(dirname "$0")/.."

if [ ! -f .env.production ]; then
  echo "❌ .env.production not found. Run: cp deploy/.env.production.example .env.production && nano .env.production"
  exit 1
fi
chmod 600 .env.production

echo "==> Pulling latest code"
git fetch origin
git checkout master
git pull --ff-only origin master

echo "==> Building image (this can take 3-5 min on first build)"
docker compose -f docker-compose.prod.yml build

echo "==> Restarting service"
docker compose -f docker-compose.prod.yml up -d

echo "==> Waiting for healthcheck (max 60s)"
for i in $(seq 1 30); do
  # Bot port 8080 is expose-only; check via docker exec from inside the container
  if docker compose -f docker-compose.prod.yml exec -T efloud-bot \
       python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://localhost:8080/healthz', timeout=3).getcode()==200 else 1)" 2>/dev/null; then
    echo "✅ Bot is up and healthy"
    docker compose -f docker-compose.prod.yml exec -T efloud-bot \
      python -c "import urllib.request; print(urllib.request.urlopen('http://localhost:8080/healthz', timeout=3).read().decode())"
    echo ""
    exit 0
  fi
  sleep 2
done

echo "⚠️  Healthcheck did not pass within 60s. Check logs:"
docker compose -f docker-compose.prod.yml logs --tail=80
exit 1
