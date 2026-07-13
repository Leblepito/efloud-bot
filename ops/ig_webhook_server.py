"""
u2Algo Instagram/X Webhook Server
──────────────────────────────────
VPS publisher'dan gelen POST isteklerini alır:
- X (Twitter)'a tweet atar (tweepy OAuth1 ile)
- Instagram kuyruğuna JSON yazar (~/ig_pending/ veya /tmp/ig_pending/)

Kalıcı dosyalar ~/ig_pending/ ve ~/ig_done/ klasörlerine yazılır.
Token bilgileri ~/x_tokens.json veya ortam değişkenlerinden okunur.

Çalıştırma:
    python3 ops/ig_webhook_server.py
    # veya arka planda:
    nohup python3 ops/ig_webhook_server.py > ~/ig_webhook.log 2>&1 &
"""
from __future__ import annotations
import json
import logging
import os
import time
from pathlib import Path
from typing import Optional

import tweepy
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
import uvicorn

# ─── Yapılandırma ─────────────────────────────────────────────────────────────
HOME = Path.home()

# Kalıcı dizinler (sandbox sıfırlanınca /tmp/ kaybolur, ~ kalmaz)
PENDING_DIR = HOME / "ig_pending"
DONE_DIR    = HOME / "ig_done"
LOG_FILE    = HOME / "ig_webhook.log"
X_TOKENS_FILE = HOME / "x_tokens.json"
X_TWEET_COUNT_FILE = HOME / "x_tweet_count.json"

X_MONTHLY_TWEET_LIMIT = 1000
DEDUP_TTL = 3600  # 1 saat
_dedup_cache: dict[str, float] = {}

PORT = int(os.environ.get("WEBHOOK_PORT", 8765))

SPK_DISCLAIMER = (
    "⚠️ Bu içerik yatırım tavsiyesi değildir. "
    "SPK Tebliğ III-37.1 kapsamında bilgilendirme amaçlıdır."
)

# ─── Logging ──────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(str(LOG_FILE)),
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger("ig_webhook")

app = FastAPI(title="u2Algo Webhook Server", version="2.0.0")
stats = {"received": 0, "dedup_skip": 0, "x_ok": 0, "ig_queued": 0, "errors": 0}


# ─── Token Yönetimi ───────────────────────────────────────────────────────────

def load_x_tokens() -> Optional[dict]:
    """Token bilgilerini önce ortam değişkenlerinden, sonra dosyadan yükle."""
    # Ortam değişkenleri öncelikli
    env_tokens = {
        "consumer_key":    os.environ.get("X_API_KEY") or os.environ.get("X_CONSUMER_KEY"),
        "consumer_secret": os.environ.get("X_API_SECRET") or os.environ.get("X_CONSUMER_SECRET"),
        "access_token":    os.environ.get("X_ACCESS_TOKEN"),
        "access_token_secret": os.environ.get("X_ACCESS_TOKEN_SECRET"),
    }
    if all(env_tokens.values()):
        return env_tokens

    # Dosyadan yükle
    try:
        if X_TOKENS_FILE.exists():
            with open(X_TOKENS_FILE) as f:
                data = json.load(f)
            # Tüm alanlar dolu mu?
            required = ["consumer_key", "consumer_secret", "access_token", "access_token_secret"]
            if all(data.get(k) for k in required):
                return data
    except Exception as e:
        logger.error(f"X token dosyası okunamadı: {e}")

    logger.warning("X token bilgileri eksik — tweet atılamayacak")
    return None


# ─── Tweet Sayacı ─────────────────────────────────────────────────────────────

def get_tweet_count() -> dict:
    try:
        if X_TWEET_COUNT_FILE.exists():
            with open(X_TWEET_COUNT_FILE) as f:
                data = json.load(f)
            current_month = time.strftime("%Y-%m")
            if data.get("month") != current_month:
                return {"month": current_month, "count": 0}
            return data
    except Exception:
        pass
    return {"month": time.strftime("%Y-%m"), "count": 0}


def save_tweet_count(data: dict):
    try:
        with open(X_TWEET_COUNT_FILE, "w") as f:
            json.dump(data, f)
    except Exception as e:
        logger.error(f"Tweet sayacı kaydedilemedi: {e}")


# ─── Dedup ────────────────────────────────────────────────────────────────────

def is_dedup(bot_id: str, symbol: str, direction: str) -> bool:
    key = f"{bot_id}|{symbol}|{direction}"
    now = time.time()
    if key in _dedup_cache and now - _dedup_cache[key] < DEDUP_TTL:
        return True
    _dedup_cache[key] = now
    logger.info(f"Dedup: {key} işaretlendi (TTL: {DEDUP_TTL}s)")
    return False


# ─── X (Twitter) ──────────────────────────────────────────────────────────────

def post_tweet(text: str) -> Optional[str]:
    tokens = load_x_tokens()
    if not tokens:
        return None

    tweet_data = get_tweet_count()
    if tweet_data["count"] >= X_MONTHLY_TWEET_LIMIT:
        logger.warning(f"Aylık tweet limiti doldu ({X_MONTHLY_TWEET_LIMIT})")
        return None

    try:
        client = tweepy.Client(
            consumer_key=tokens["consumer_key"],
            consumer_secret=tokens["consumer_secret"],
            access_token=tokens["access_token"],
            access_token_secret=tokens["access_token_secret"],
        )
        response = client.create_tweet(text=text)
        tweet_id = response.data["id"]
        url = f"https://x.com/u2Algo/status/{tweet_id}"
        tweet_data["count"] += 1
        save_tweet_count(tweet_data)
        stats["x_ok"] += 1
        return url
    except Exception as e:
        logger.error(f"X tweet hatası: {e}")
        stats["errors"] += 1
        return None


# ─── Instagram Kuyruğu ────────────────────────────────────────────────────────

def queue_instagram(payload: dict, filename: str):
    PENDING_DIR.mkdir(parents=True, exist_ok=True)
    filepath = PENDING_DIR / filename
    with open(filepath, "w") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    stats["ig_queued"] += 1
    logger.info(f"Instagram kuyruğuna eklendi: {filename}")


# ─── İçerik Oluşturma ─────────────────────────────────────────────────────────

def build_tweet_text(data: dict) -> str:
    bot_id    = data.get("bot_id", "BOT")
    symbol    = data.get("symbol", "???")
    direction = data.get("direction", "").upper()
    entry     = data.get("entry_price", 0)
    sl        = data.get("sl_price", 0)
    tp        = data.get("tp_price", 0)
    pnl       = data.get("pnl_pct", None)

    dir_emoji = "🟢 LONG" if direction == "LONG" else "🔴 SHORT"
    lines = [
        f"#{bot_id} Bot | {symbol} {dir_emoji}",
        f"📍 Giriş: {entry}",
        f"🛑 SL: {sl}",
        f"🎯 TP: {tp}",
    ]
    if pnl is not None:
        pnl_emoji = "✅" if float(pnl) >= 0 else "❌"
        lines.append(f"{pnl_emoji} PnL: %{pnl}")
    lines += ["", SPK_DISCLAIMER, "#u2Algo #crypto #trading"]
    return "\n".join(lines)


def build_ig_caption(data: dict) -> str:
    bot_id    = data.get("bot_id", "BOT")
    symbol    = data.get("symbol", "???")
    direction = data.get("direction", "").upper()
    entry     = data.get("entry_price", 0)
    sl        = data.get("sl_price", 0)
    tp        = data.get("tp_price", 0)
    pnl       = data.get("pnl_pct", None)

    dir_emoji = "🟢 LONG" if direction == "LONG" else "🔴 SHORT"
    lines = [
        f"🤖 {bot_id} Bot — {symbol} {dir_emoji}",
        "",
        f"📍 Giriş: {entry}",
        f"🛑 Stop Loss: {sl}",
        f"🎯 Take Profit: {tp}",
    ]
    if pnl is not None:
        pnl_emoji = "✅" if float(pnl) >= 0 else "❌"
        lines.append(f"{pnl_emoji} PnL: %{pnl}")
    lines += ["", SPK_DISCLAIMER, "", "#u2Algo #crypto #trading #bitcoin #ethereum #binance"]
    return "\n".join(lines)


# ─── Endpoint'ler ─────────────────────────────────────────────────────────────

@app.post("/webhook")
async def webhook(request: Request):
    try:
        data = await request.json()
    except Exception:
        return JSONResponse({"error": "invalid json"}, status_code=400)

    stats["received"] += 1
    bot_id    = data.get("bot_id", "UNKNOWN")
    symbol    = data.get("symbol", "???")
    direction = data.get("direction", "")

    logger.info(f"Yeni istek: {bot_id} | {symbol} {direction}")

    if is_dedup(bot_id, symbol, direction):
        logger.warning(f"DEDUP: {bot_id} {symbol} {direction} son 1 saat içinde zaten yayınlandı.")
        stats["dedup_skip"] += 1
        return JSONResponse({"status": "dedup_skip"})

    results = {}

    # X tweet
    tweet_url = post_tweet(build_tweet_text(data))
    if tweet_url:
        results["x"] = tweet_url
        logger.info(f"✅ X: {tweet_url}")
    else:
        results["x"] = "error_or_skipped"

    # Instagram kuyruğu
    ts = int(time.time())
    safe_symbol = symbol.replace("/", "_")
    filename = f"{bot_id}_{safe_symbol}_{direction}_{ts}.json"
    queue_instagram({
        "caption":   build_ig_caption(data),
        "image_url": data.get("chart_url", ""),
        "bot_id":    bot_id,
        "symbol":    symbol,
        "direction": direction,
        "timestamp": ts,
        "raw":       data,
    }, filename)
    results["instagram"] = f"queued:{filename}"

    return JSONResponse({"status": "ok", "results": results})


@app.get("/health")
async def health():
    tweet_data = get_tweet_count()
    return {
        "status": "ok",
        "stats": stats,
        "tweet_count_this_month": tweet_data.get("count", 0),
        "tweet_limit": X_MONTHLY_TWEET_LIMIT,
        "pending_dir": str(PENDING_DIR),
        "done_dir":    str(DONE_DIR),
        "x_tokens_ok": load_x_tokens() is not None,
    }


@app.get("/stats")
async def get_stats():
    return stats


if __name__ == "__main__":
    PENDING_DIR.mkdir(parents=True, exist_ok=True)
    DONE_DIR.mkdir(parents=True, exist_ok=True)
    logger.info(f"Webhook server başlatılıyor — port {PORT}")
    logger.info(f"Pending dir: {PENDING_DIR}")
    logger.info(f"Done dir:    {DONE_DIR}")
    uvicorn.run(app, host="0.0.0.0", port=PORT, log_level="info")
