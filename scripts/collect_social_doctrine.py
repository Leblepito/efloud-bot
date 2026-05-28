"""Script to automate social doctrine collection from Efloud public feeds.

Run this periodically (e.g. via cron) to build the research archive.
Usage: python -m scripts.collect_social_doctrine
"""
import asyncio
import logging
import sys
from pathlib import Path

# Ensure project root is in path for module imports
sys.path.append(str(Path(__file__).parent.parent))

from backend.social.feeds import fetch_social_feeds
from backend.social.doctrine import extract_doctrine
from backend.social.archive import append_doctrine_snapshot

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger("efloud.scripts.collect_social_doctrine")

ARCHIVE_PATH = Path("state/social_doctrine.jsonl")

async def run_collection():
    log.info("Starting social doctrine collection...")
    
    try:
        feeds = await fetch_social_feeds()
    except Exception as exc:
        log.error("Failed to fetch social feeds: %s", exc)
        return

    telegram_items = feeds.get("telegram", [])
    twitter_items = feeds.get("twitter", [])
    all_items = telegram_items + twitter_items
    
    log.info("Fetched %d Telegram items, %d Twitter items.", len(telegram_items), len(twitter_items))
    
    new_count = 0
    for item in all_items:
        try:
            doctrine = extract_doctrine(item)
            result = append_doctrine_snapshot(ARCHIVE_PATH, item, doctrine)
            if result.get("written"):
                new_count += 1
                log.info("Archived new doctrine: %s", result.get("dedup_key"))
        except Exception as exc:
            log.error("Failed to process item %s: %s", item.get("id"), exc)

    log.info("Collection finished. Added %d new items to %s", new_count, ARCHIVE_PATH)

if __name__ == "__main__":
    asyncio.run(run_collection())
