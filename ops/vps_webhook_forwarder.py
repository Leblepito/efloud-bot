"""
u2Algo VPS Webhook Forwarder
─────────────────────────────
VPS'te çalışır. Sabit bir URL sağlar (VPS IP değişmez).
Gelen webhook isteklerini Manus sandbox'a iletir.

Bu yaklaşım sandbox URL sorununu tamamen çözer:
- VPS'teki publisher → VPS forwarder (sabit URL) → Manus sandbox (değişken URL)
- Manus sandbox URL değiştiğinde sadece forwarder config güncellenir.

Kurulum (VPS'te):
    pip3 install fastapi uvicorn requests
    # Manus sandbox URL'ini ayarla:
    export MANUS_WEBHOOK_URL="https://8765-XXXX.sg1.manus.computer/webhook"
    # Başlat:
    nohup python3 vps_webhook_forwarder.py > /var/log/u2algo-forwarder.log 2>&1 &

Systemd servisi olarak:
    cp vps_webhook_forwarder.py /opt/u2algo/
    # /etc/systemd/system/u2algo-forwarder.service dosyasını oluşturun
    systemctl enable u2algo-forwarder
    systemctl start u2algo-forwarder
"""
from __future__ import annotations
import json
import logging
import os
import time
from pathlib import Path

import requests
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
import uvicorn

# ─── Yapılandırma ─────────────────────────────────────────────────────────────
PORT = int(os.environ.get("FORWARDER_PORT", 8766))

# Manus sandbox webhook URL — sandbox yenilenince güncellenir
MANUS_WEBHOOK_URL = os.environ.get(
    "MANUS_WEBHOOK_URL",
    "https://8765-PLACEHOLDER.sg1.manus.computer/webhook"
)

# URL geçmişi dosyası (VPS'te kalıcı)
URL_HISTORY_FILE = Path("/opt/u2algo/webhook_url_history.json")

FORWARD_TIMEOUT = 10  # saniye
MAX_RETRIES = 3

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler("/var/log/u2algo-forwarder.log"),
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger("vps_forwarder")

app = FastAPI(title="u2Algo VPS Webhook Forwarder", version="1.0.0")
stats = {"received": 0, "forwarded": 0, "failed": 0}


def get_target_url() -> str:
    """Güncel Manus webhook URL'ini döndür."""
    # Ortam değişkeni en güncel URL'i içerir
    return os.environ.get("MANUS_WEBHOOK_URL", MANUS_WEBHOOK_URL)


def forward_request(data: dict) -> dict:
    """İsteği Manus sandbox'a ilet."""
    target = get_target_url()
    last_error = None

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            resp = requests.post(
                target,
                json=data,
                timeout=FORWARD_TIMEOUT,
                headers={"Content-Type": "application/json"},
            )
            if resp.status_code == 200:
                logger.info(f"✅ İletildi → {target} (deneme {attempt})")
                return {"ok": True, "status_code": resp.status_code, "response": resp.json()}
            else:
                logger.warning(f"HTTP {resp.status_code} — deneme {attempt}/{MAX_RETRIES}")
                last_error = f"HTTP {resp.status_code}"
        except requests.exceptions.ConnectionError as e:
            logger.warning(f"Bağlantı hatası (deneme {attempt}/{MAX_RETRIES}): {e}")
            last_error = str(e)
        except requests.exceptions.Timeout:
            logger.warning(f"Zaman aşımı (deneme {attempt}/{MAX_RETRIES})")
            last_error = "timeout"
        except Exception as e:
            logger.error(f"Beklenmeyen hata: {e}")
            last_error = str(e)

        if attempt < MAX_RETRIES:
            time.sleep(2 ** attempt)  # Exponential backoff

    return {"ok": False, "error": last_error, "target": target}


@app.post("/webhook")
async def webhook(request: Request):
    try:
        data = await request.json()
    except Exception:
        return JSONResponse({"error": "invalid json"}, status_code=400)

    stats["received"] += 1
    logger.info(f"Alındı: {data.get('bot_id')} | {data.get('symbol')} {data.get('direction')}")

    result = forward_request(data)
    if result["ok"]:
        stats["forwarded"] += 1
        return JSONResponse({"status": "forwarded", "manus_response": result.get("response")})
    else:
        stats["failed"] += 1
        logger.error(f"İletme başarısız: {result.get('error')}")
        return JSONResponse({"status": "forward_failed", "error": result.get("error")}, status_code=502)


@app.post("/update-url")
async def update_url(request: Request):
    """Manus sandbox URL'ini güncelle (sandbox yenilenince çağrılır)."""
    try:
        data = await request.json()
        new_url = data.get("url", "").strip()
        if not new_url.startswith("https://"):
            return JSONResponse({"error": "Geçersiz URL"}, status_code=400)
        os.environ["MANUS_WEBHOOK_URL"] = new_url
        logger.info(f"Manus URL güncellendi: {new_url}")
        # Geçmişe kaydet
        URL_HISTORY_FILE.parent.mkdir(parents=True, exist_ok=True)
        history = []
        if URL_HISTORY_FILE.exists():
            try:
                history = json.loads(URL_HISTORY_FILE.read_text())
            except Exception:
                pass
        history.append({"url": new_url, "updated_at": time.strftime("%Y-%m-%d %H:%M:%S")})
        URL_HISTORY_FILE.write_text(json.dumps(history[-10:], indent=2))  # Son 10 URL
        return JSONResponse({"status": "ok", "url": new_url})
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


@app.get("/health")
async def health():
    return {
        "status": "ok",
        "stats": stats,
        "target_url": get_target_url(),
    }


if __name__ == "__main__":
    logger.info(f"VPS Forwarder başlatılıyor — port {PORT}")
    logger.info(f"Hedef: {get_target_url()}")
    uvicorn.run(app, host="0.0.0.0", port=PORT, log_level="info")
