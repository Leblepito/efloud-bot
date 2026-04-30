# ─────────────────────────────────────────────────────────────────
# Stage 1 — Build Next.js frontend (static export → frontend/out)
# ─────────────────────────────────────────────────────────────────
FROM node:20-alpine AS frontend-builder
WORKDIR /app/frontend

# Cache deps (package-lock.json first for layer cache hit)
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --legacy-peer-deps

# Copy source + build (Next.js outputs to ./out due to next.config.ts: output: 'export')
COPY frontend/ ./
RUN npm run build

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
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# App source (excludes dev artifacts via .dockerignore)
COPY . ./

# Pre-built static frontend from stage 1
COPY --from=frontend-builder /app/frontend/out ./frontend/out

# Required directories (state, logs, reports — bot writes here)
RUN mkdir -p ./state ./state_micro ./state_1k ./logs ./reports

EXPOSE 8080
CMD ["sh", "-c", "uvicorn backend.main:app --host 0.0.0.0 --port ${PORT:-8080}"]
