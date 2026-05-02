#!/usr/bin/env bash
# Efloud Bot — Hetzner deploy / update script
# Run from /opt/efloud-bot as user `efloud` (member of docker group)

set -euo pipefail

cd "$(dirname "$0")/.."

if [ ! -f .env.production ]; then
  echo "❌ .env.production not found. Run: cp deploy/.env.production.example .env.production && nano .env.production"
  exit 1
fi

echo "==> Pulling latest code"
git fetch origin
git checkout feature/web-platform
git pull --ff-only origin feature/web-platform

echo "==> Building image (this can take 3-5 min on first build)"
docker compose -f docker-compose.prod.yml build

echo "==> Restarting service"
docker compose -f docker-compose.prod.yml up -d

echo "==> Waiting for healthcheck (max 60s)"
for i in $(seq 1 30); do
  if curl -fsS http://localhost:8080/healthz >/dev/null 2>&1; then
    echo "✅ Bot is up and healthy"
    curl -s http://localhost:8080/healthz
    echo ""
    exit 0
  fi
  sleep 2
done

echo "⚠️  Healthcheck did not pass within 60s. Check logs:"
docker compose -f docker-compose.prod.yml logs --tail=80
exit 1
