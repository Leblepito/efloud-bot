#!/usr/bin/env bash
# efloud advisory research cycle — host-side runner (systemd timer çağırır).
#
# Ne yapar: izole `efloud-research` konteynerini TEK SEFERLİK çalıştırır
# (`docker run --rm`), 5 saatlik döngüde 15m/1h/4h LuxAlgo yapısı + TradingAgents
# brief'i üretir. ADVISORY ONLY — asla emir, sizing, SL/TP veya config girdisi değil.
#
# Güvenlik sınırları (bilinçli, değiştirme):
#   * Repo READ-ONLY mount edilir; yalnız `desk/` yazılabilir (brief'ler oraya gider).
#   * LLM anahtarı SADECE `.env.research` dosyasından gelir — `.env.production`
#     ASLA verilmez (Binance API anahtarları orada; TradingAgents güvenilmeyen
#     haber/sosyal metni LLM'e veriyor).
#   * Anahtar değeri hiçbir zaman stdout'a/loga basılmaz (yalnız "boş mu" kontrolü).
#
# Elle kullanım:
#   deploy/research-cycle.sh --no-tradingagents          # ücretsiz duman testi
#   deploy/research-cycle.sh --symbols BTC/USDT          # tek sembol, tam koşu
#
# Env ile ezilebilir: EFLOUD_REPO, RESEARCH_IMAGE, RESEARCH_ENV_FILE, RESEARCH_SYMBOLS.

set -euo pipefail

REPO="${EFLOUD_REPO:-/opt/efloud-bot}"
IMAGE="${RESEARCH_IMAGE:-efloud-research:latest}"
ENV_FILE="${RESEARCH_ENV_FILE:-$REPO/.env.research}"
SYMBOLS="${RESEARCH_SYMBOLS:-BTC/USDT,ETH/USDT}"
STAMP="$REPO/desk/.research_image.stamp"

cd "$REPO"
mkdir -p "$REPO/desk/briefs" "$REPO/logs"

# ── 0) env kapısı ─────────────────────────────────────────────────────────────
if [ ! -f "$ENV_FILE" ]; then
    echo "[research] FATAL: $ENV_FILE yok (şablon: deploy/.env.research.example)" >&2
    exit 2
fi
case "$ENV_FILE" in
    *production*)
        echo "[research] FATAL: production env dosyası bu runner'a verilemez" >&2
        exit 2
        ;;
esac
if ! grep -q '^OPENROUTER_API_KEY=.' "$ENV_FILE"; then
    echo "[research] FATAL: OPENROUTER_API_KEY boş görünüyor ($ENV_FILE) — değer basılmadı" >&2
    exit 2
fi

# ── 1) imaj: requirements hash'i değiştiyse yeniden build ─────────────────────
if command -v sha256sum >/dev/null 2>&1; then
    WANT="$(sha256sum requirements-research.txt | cut -d' ' -f1)"
else
    WANT="$(md5sum requirements-research.txt | cut -d' ' -f1)"
fi
HAVE="$(cat "$STAMP" 2>/dev/null || true)"

if [ "$WANT" != "$HAVE" ] || ! docker image inspect "$IMAGE" >/dev/null 2>&1; then
    echo "[research] building $IMAGE (requirements-research.txt changed or image absent)..."
    docker build -f deploy/Dockerfile.research -t "$IMAGE" .
    printf '%s\n' "$WANT" > "$STAMP"
fi

# ── 2) tek seferlik koşu ──────────────────────────────────────────────────────
# Argüman verilmediyse varsayılan semboller; verildiyse aynen iletilir.
if [ "$#" -eq 0 ]; then
    set -- --symbols "$SYMBOLS" --out desk/briefs
fi

echo "[research] run start $(date -u +%FT%TZ) args=$*"
exec docker run --rm \
    --name efloud-research-run \
    --env-file "$ENV_FILE" \
    --mount "type=bind,src=$REPO,dst=/app,readonly" \
    --mount "type=bind,src=$REPO/desk,dst=/app/desk" \
    --tmpfs "/tmp:rw,size=512m" \
    "$IMAGE" "$@"
