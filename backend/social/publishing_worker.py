"""Background worker - process approved drafts and publish to platforms.

This worker runs in the background (via FastAPI lifespan or cron) and:
1. Polls for APPROVED drafts from the database
2. Publishes each draft to its target platforms (X, Instagram, YouTube)
3. Updates draft status to SENT (all success) or FAILED (any failure)
4. Logs all actions for audit trail

Activation:
- Auto-starts with FastAPI backend (lifespan event)
- Or runs manually: python -m backend.social.publishing_worker
"""
from __future__ import annotations

import asyncio
import logging
import os
from datetime import datetime, timezone
from typing import Optional

from backend.db import db
from backend.social.queue_storage import load_draft, save_draft, list_by_status
from backend.social.content_queue import ContentStatus, ContentDraft
from backend.social.xurl_client import XurlClient
from backend.social.instagram_client import InstagramClient
from backend.social.youtube_client import YouTubeClient

log = logging.getLogger("efloud.publishing_worker")

# Worker configuration
POLL_INTERVAL_SEC = 60  # Check for APPROVED drafts every minute
MAX_RETRIES = 3


class PublishingWorker:
    """Background worker that processes approved content drafts."""

    def __init__(self):
        self._running = False
        self._task: Optional[asyncio.Task] = None

        # Initialize clients (lazy - only if enabled)
        self._x_client = None
        self._instagram_client = None
        self._youtube_client = None

    def _get_clients(self):
        """Lazy initialize platform clients."""
        if self._x_client is None:
            self._x_client = XurlClient()
        if self._instagram_client is None:
            self._instagram_client = InstagramClient()
        if self._youtube_client is None:
            self._youtube_client = YouTubeClient()

        return {
            "x": self._x_client,
            "instagram": self._instagram_client,
            "youtube": self._youtube_client,
        }

    async def process_approved_drafts(self) -> int:
        """Process all APPROVED drafts.

        Returns:
            Number of drafts processed
        """
        if not db.pool:
            log.warning("DB pool not ready - skipping worker run")
            return 0

        try:
            # Get all APPROVED drafts
            drafts = await list_by_status(db.pool, ContentStatus.APPROVED, limit=50)

            if not drafts:
                log.debug("No APPROVED drafts to process")
                return 0

            log.info(f"Found {len(drafts)} APPROVED drafts to process")

            processed = 0
            for draft in drafts:
                try:
                    await self._process_draft(draft)
                    processed += 1
                except Exception as e:
                    log.error(f"Failed to process draft {draft.draft_id[:8]}…: {e}")

            return processed

        except Exception as e:
            log.error(f"Worker run failed: {e}", exc_info=True)
            return 0

    async def _process_draft(self, draft: ContentDraft) -> None:
        """Process a single draft - publish to target platforms.

        Args:
            draft: ContentDraft in APPROVED status
        """
        log.info(f"Processing draft {draft.draft_id[:8]}… (lang={draft.lang}, type={draft.post_type})")

        # Get target platforms from draft meta (default: X only)
        platforms = draft.meta.get("platforms", ["x"])
        if not isinstance(platforms, list):
            platforms = ["x"]

        log.info(f"Target platforms: {platforms}")

        # Get clients
        clients = self._get_clients()

        # Track results - preserve existing successful posts from previous runs
        results = draft.meta.get("publish_results", {})
        publish_errors = draft.meta.get("publish_errors", [])

        for platform in platforms:
            # Skip if already successfully published (avoid duplicate posts)
            if platform in results and results[platform].get("ok"):
                log.info(f"Skipping {platform} - already published (post_id: {results[platform].get('post_id')})")
                continue

            try:
                client = clients.get(platform)
                if not client or not client.is_active():
                    log.warning(f"Platform {platform} not active - skipping")
                    error_msg = f"{platform}: client not active"
                    if error_msg not in publish_errors:
                        publish_errors.append(error_msg)
                    results[platform] = {"ok": False, "error": "client not active"}
                    continue

                # Publish using unified interface
                response = client.post_draft(draft)

                if response.ok:
                    results[platform] = {
                        "ok": True,
                        "post_id": response.post_id,
                        "post_url": response.post_url,
                    }
                    log.info(f"✅ Published to {platform}: {response.post_url}")
                else:
                    error_msg = response.stderr or "unknown error"
                    results[platform] = {"ok": False, "error": error_msg}
                    if error_msg not in publish_errors:
                        publish_errors.append(error_msg)
                    log.error(f"❌ Failed to publish to {platform}: {error_msg}")

            except Exception as e:
                error_msg = str(e)
                results[platform] = {"ok": False, "error": error_msg}
                if error_msg not in publish_errors:
                    publish_errors.append(error_msg)
                log.error(f"❌ Exception publishing to {platform}: {e}")

        # Update draft status - check if all target platforms are now successful
        all_success = all(results.get(p, {}).get("ok") for p in platforms)

        if all_success:
            # All target platforms succeeded
            draft.status = ContentStatus.SENT
            draft.meta["published_at"] = datetime.now(timezone.utc).isoformat()
            draft.meta["publish_results"] = results
            # Clear errors on final success
            draft.meta.pop("publish_errors", None)
            draft.meta.pop("failed_at", None)
            log.info(f"✅ Draft {draft.draft_id[:8]}… marked as SENT")
        else:
            # At least one target platform still pending/failed - keep as APPROVED for retry
            draft.status = ContentStatus.APPROVED  # Stay in APPROVED for worker retry
            draft.meta["publish_results"] = results
            draft.meta["publish_errors"] = publish_errors
            if "failed_at" not in draft.meta:
                draft.meta["failed_at"] = datetime.now(timezone.utc).isoformat()
            log.warning(f"⚠️  Draft {draft.draft_id[:8]}… still has failures - remaining in APPROVED for retry")

        # Save updated draft
        await save_draft(db.pool, draft)

    async def run(self) -> None:
        """Run worker loop until stopped."""
        self._running = True
        log.info("Publishing worker started")

        while self._running:
            try:
                await self.process_approved_drafts()
            except Exception as e:
                log.error(f"Worker loop error: {e}", exc_info=True)

            # Wait before next poll
            for _ in range(POLL_INTERVAL_SEC):
                if not self._running:
                    break
                await asyncio.sleep(1)

        log.info("Publishing worker stopped")

    def stop(self) -> None:
        """Stop the worker."""
        self._running = False


# Global worker instance
_worker: Optional[PublishingWorker] = None


def get_worker() -> PublishingWorker:
    """Get singleton worker instance."""
    global _worker
    if _worker is None:
        _worker = PublishingWorker()
    return _worker


# FastAPI lifespan integration
async def start_worker():
    """Start worker in background (called from FastAPI lifespan)."""
    worker = get_worker()
    if not worker._running:
        worker._task = asyncio.create_task(worker.run())
        log.info("Worker started via lifespan")


async def stop_worker():
    """Stop worker (called from FastAPI lifespan)."""
    worker = get_worker()
    worker.stop()
    if worker._task:
        worker._task.cancel()
        try:
            await worker._task
        except asyncio.CancelledError:
            pass
    log.info("Worker stopped via lifespan")


# Manual run (for testing or standalone execution)
async def main():
    """Run worker once for testing."""
    worker = get_worker()
    count = await worker.process_approved_drafts()
    print(f"Processed {count} drafts")


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())