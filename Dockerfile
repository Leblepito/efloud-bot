# ─────────────────────────────────────────────────────────────────
# Stage 1 — Build Next.js frontend (static export → frontend/out)
# Monorepo-aware (PR #0): the dashboard is an npm workspace depending on the
# shared @efloud/tokens package, so install + build from the repo root.
# ─────────────────────────────────────────────────────────────────
FROM node:20-alpine AS frontend-builder
WORKDIR /app

# Cache deps: root workspace manifests + lockfile + shared packages first.
COPY package.json package-lock.json ./
COPY packages ./packages
COPY frontend/package.json ./frontend/package.json
RUN npm ci --legacy-peer-deps

# Copy frontend source + build the workspace (next.config.ts output: 'export' → frontend/out).
COPY frontend/ ./frontend/
RUN npm run build --workspace efloud-frontend

# Verify build output exists
RUN test -f /app/frontend/out/index.html || (echo "BUILD FAILED: out/index.html missing" && exit 1)

# ─────────────────────────────────────────────────────────────────
# Stage 2 — Python backend + bot + static frontend
# ─────────────────────────────────────────────────────────────────
FROM python:3.11-slim
WORKDIR /app

ENV PYTHONUNBUFFERED=1 \
    PYTHONIOENCODING=utf-8 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# System deps for asyncpg / pandas / numpy / ccxt
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libffi-dev \
    && rm -rf /var/lib/apt/lists/*

# Cache Python deps
# Drift-pinleme (2026-07-17): '-c constraints.txt' — requirements '>=' aralıkları
# her rebuild'de o günün sürümlerini çekiyordu; ccxt≥4.5 + pandas-3 drift'i canlı
# bug üretti (bkz. docs/reviews/2026-07-17-full-repo-review-findings.md).
# constraints.txt tam suite'in yeşil doğrulandığı kapanışı sabitler.
COPY requirements.txt constraints.txt ./
RUN pip install --no-cache-dir -r requirements.txt -c constraints.txt

# App source (excludes dev artifacts via .dockerignore)
COPY . ./

# Pre-built static frontend from stage 1
COPY --from=frontend-builder /app/frontend/out ./frontend/out

# Required directories (state, logs, reports — bot writes here)
RUN mkdir -p ./state ./state_micro ./state_1k ./logs ./reports

EXPOSE 8080
# B-5 fix (2026-07-17): --proxy-headers + --forwarded-allow-ips — Caddy arkasında
# uvicorn X-Forwarded-For okumuyordu → request.client.host hep proxy IP'si →
# /api/login per-IP rate limiti TEK global kovaya çöküyordu: internetten herhangi
# biri 5 yanlış şifreyle 15 dk boyunca OPERATÖRÜN dashboard girişini de
# kilitleyebiliyordu (kill-switch erişimi dahil). Trusted proxy = compose-içi
# Caddy; container ağı dışından doğrudan erişim yok, bu yüzden '*' güvenli.
CMD ["sh", "-c", "uvicorn backend.main:app --host 0.0.0.0 --port ${PORT:-8080} --proxy-headers --forwarded-allow-ips '*'"]
