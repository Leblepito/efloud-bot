"""
u2Algo Instagram Sandbox Poller
────────────────────────────────
~/ig_pending/ klasörünü okur.
Her JSON için Instagram MCP ile yayınlar.
Tamamlananları ~/ig_done/ klasörüne taşır.

NOT: Bu script doğrudan Manus agent shell'inden çalıştırılmalıdır.
     manus-mcp-cli subprocess içinden çağrılamaz.

Çalıştırma (Manus zamanlanmış görev):
    python3 /home/ubuntu/efloud-bot/ops/ig_sandbox_poller.py
"""
from __future__ import annotations
import json
import logging
import os
import shutil
import time
from pathlib import Path

HOME        = Path.home()
PENDING_DIR = HOME / "ig_pending"
DONE_DIR    = HOME / "ig_done"
DEDUP_FILE  = HOME / "ig_poller_dedup.json"
DEDUP_TTL   = 3600  # 1 saat

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger("ig_poller")


def load_dedup() -> dict:
    try:
        if DEDUP_FILE.exists():
            with open(DEDUP_FILE) as f:
                return json.load(f)
    except Exception:
        pass
    return {}


def save_dedup(data: dict):
    try:
        with open(DEDUP_FILE, "w") as f:
            json.dump(data, f)
    except Exception as e:
        logger.error(f"Dedup kaydedilemedi: {e}")


def is_dedup(key: str) -> bool:
    dedup = load_dedup()
    now = time.time()
    dedup = {k: v for k, v in dedup.items() if now - v < DEDUP_TTL}
    if key in dedup:
        return True
    dedup[key] = now
    save_dedup(dedup)
    return False


def list_pending() -> list[Path]:
    PENDING_DIR.mkdir(parents=True, exist_ok=True)
    return sorted(PENDING_DIR.glob("*.json"))


def move_to_done(filepath: Path, prefix: str = ""):
    DONE_DIR.mkdir(parents=True, exist_ok=True)
    dest_name = f"{prefix}{filepath.name}" if prefix else filepath.name
    shutil.move(str(filepath), str(DONE_DIR / dest_name))
    logger.info(f"Taşındı → done/{dest_name}")


def process_pending() -> dict:
    """
    Bekleyen dosyaları döndür — agent bu listeyi kullanarak MCP çağrısı yapar.
    Bu fonksiyon doğrudan MCP çağrısı YAPMAZ (subprocess kısıtı nedeniyle).
    """
    files = list_pending()
    if not files:
        logger.info("Kuyruk boş — bekleyen paylaşım yok")
        return {"pending": [], "count": 0}

    logger.info(f"{len(files)} bekleyen paylaşım bulundu")
    pending_items = []

    for filepath in files:
        try:
            with open(filepath) as f:
                payload = json.load(f)

            bot_id    = payload.get("bot_id", "")
            symbol    = payload.get("symbol", "")
            direction = payload.get("direction", "")
            dedup_key = f"{bot_id}|{symbol}|{direction}"

            if is_dedup(dedup_key):
                logger.warning(f"DEDUP: {dedup_key} zaten yayınlandı, atlanıyor")
                move_to_done(filepath, prefix="DEDUP_")
                continue

            image_url = payload.get("image_url", "")
            caption   = payload.get("caption", "")

            if not image_url:
                logger.warning(f"image_url boş: {filepath.name}, atlanıyor")
                move_to_done(filepath, prefix="NO_IMG_")
                continue

            pending_items.append({
                "filepath": str(filepath),
                "filename": filepath.name,
                "image_url": image_url,
                "caption": caption,
                "bot_id": bot_id,
                "symbol": symbol,
                "direction": direction,
            })

        except Exception as e:
            logger.error(f"Dosya okuma hatası {filepath.name}: {e}")

    return {"pending": pending_items, "count": len(pending_items)}


def mark_published(filepath_str: str, success: bool = True):
    """Yayınlanan dosyayı done klasörüne taşı."""
    filepath = Path(filepath_str)
    if filepath.exists():
        prefix = "" if success else "ERROR_"
        move_to_done(filepath, prefix=prefix)


if __name__ == "__main__":
    result = process_pending()
    if result["count"] == 0:
        print("Kuyruk boş — bekleyen paylaşım yok")
    else:
        print(f"{result['count']} paylaşım bekliyor:")
        for item in result["pending"]:
            print(f"  - {item['filename']}: {item['bot_id']} | {item['symbol']} {item['direction']}")
        print("\nNOT: Instagram MCP çağrısı agent tarafından doğrudan yapılmalıdır.")
        print("Her dosya için:")
        print('  manus-mcp-cli tool call create_instagram --server instagram --input \'{"image_url":"...","caption":"..."}\'')
