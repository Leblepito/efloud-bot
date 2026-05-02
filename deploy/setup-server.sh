#!/usr/bin/env bash
# Hetzner Cloud — Fresh Ubuntu 24.04 server bootstrap for efloud-bot
# Usage (as root, on freshly-provisioned server):
#   curl -fsSL https://raw.githubusercontent.com/<USER>/<REPO>/master/deploy/setup-server.sh | bash
# Or: scp this file to server, then `bash setup-server.sh`

set -euo pipefail

echo "==> [1/6] System update"
apt-get update -y
apt-get upgrade -y

echo "==> [2/6] Install base tools (git, curl, ufw, fail2ban)"
apt-get install -y git curl ca-certificates ufw fail2ban

echo "==> [3/6] Install Docker Engine + Compose plugin"
if ! command -v docker >/dev/null 2>&1; then
  install -m 0755 -d /etc/apt/keyrings
  curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
  chmod a+r /etc/apt/keyrings/docker.asc
  echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu $(. /etc/os-release && echo $VERSION_CODENAME) stable" \
    > /etc/apt/sources.list.d/docker.list
  apt-get update -y
  apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
  systemctl enable --now docker
fi
docker --version
docker compose version

echo "==> [4/6] Configure UFW firewall (22 SSH, 80/443 for Caddy)"
ufw default deny incoming
ufw default allow outgoing
ufw allow 22/tcp
ufw allow 80/tcp     # ACME HTTP challenge + redirect
ufw allow 443/tcp    # Caddy HTTPS
ufw allow 443/udp    # Caddy HTTP/3 (QUIC)
ufw --force enable
ufw status

echo "==> [5/6] Enable fail2ban for SSH brute-force protection"
systemctl enable --now fail2ban

echo "==> [6/6] Create app user & directory"
if ! id -u efloud >/dev/null 2>&1; then
  useradd -m -s /bin/bash efloud
  usermod -aG docker efloud
fi
mkdir -p /opt/efloud-bot
chown -R efloud:efloud /opt/efloud-bot

echo ""
echo "✅ Server bootstrap complete."
echo ""
echo "Next steps:"
echo "  1. Switch to efloud user:   su - efloud"
echo "  2. Clone repo:              git clone <REPO_URL> /opt/efloud-bot && cd /opt/efloud-bot"
echo "  3. Configure env:           cp deploy/.env.production.example .env.production && nano .env.production"
echo "  4. Deploy:                  bash deploy/deploy.sh"
echo ""
echo "Server public IPv4 (whitelist this in Binance API key):"
curl -s -4 ifconfig.me || echo "(could not auto-detect — check Hetzner panel)"
echo ""
