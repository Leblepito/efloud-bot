"""Instagram client - tier2 render + Meta Graph API.

Activation:
- env INSTAGRAM_ENABLED=true (default false → no-op)
- env INSTAGRAM_BUSINESS_ACCOUNT_ID (required)
- env FACEBOOK_ACCESS_TOKEN (required)

Interface: Same as XurlClient - post_draft(draft) -> InstagramResponse(post_id, post_url)
"""
from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import requests

log = logging.getLogger("efloud.instagram")

# ────────────────────────── Constants ──────────────────────────

BASE_URL = "https://graph.facebook.com/v18.0"
SUBPROCESS_TIMEOUT_SEC = 15
MAX_LOG_BODY = 1024


# ────────────────────────── Exceptions ──────────────────────────


class InstagramError(Exception):
    """Base Instagram client error."""


class InstagramDisabled(InstagramError):
    """Flag off veya credentials eksik."""


class InstagramComplianceViolation(InstagramError):
    """Post content compliance gate'i geçemedi."""


class InstagramSubprocessError(InstagramError):
    """API call non-zero exit veya timeout."""


# ────────────────────────── Response ──────────────────────────


@dataclass
class InstagramResponse:
    """Bir post çağrısının sonucu."""
    ok: bool
    dry_run: bool = False
    would_execute: bool = False
    post_id: Optional[str] = None
    post_url: Optional[str] = None
    stdout: str = ""
    stderr: str = ""
    exit_code: Optional[int] = None
    raw: dict = None

    def to_dict(self) -> dict:
        return {
            "ok": self.ok,
            "dry_run": self.dry_run,
            "would_execute": self.would_execute,
            "post_id": self.post_id,
            "post_url": self.post_url,
            "exit_code": self.exit_code,
        }


# ────────────────────────── Env gating ──────────────────────────


def _enabled() -> bool:
    """INSTAGRAM_ENABLED env truthy check."""
    raw = os.environ.get("INSTAGRAM_ENABLED", "").strip().lower()
    return raw in ("1", "true", "yes", "on")


def _credential(name: str) -> Optional[str]:
    """Instagram credential env read."""
    raw = os.environ.get(name, "").strip()
    return raw if raw else None


# ────────────────────────── Client ──────────────────────────


class InstagramClient:
    """Instagram client - tier2 render + Meta Graph API."""

    def __init__(self, dry_run: bool = False):
        self.dry_run = dry_run
        self._active = False
        self._business_account_id = None
        self._access_token = None

        if _enabled():
            self._business_account_id = _credential("INSTAGRAM_BUSINESS_ACCOUNT_ID")
            self._access_token = _credential("FACEBOOK_ACCESS_TOKEN")
            if self._business_account_id and self._access_token:
                self._active = True
                log.info("Instagram client active")
            else:
                log.warning("Instagram enabled but credentials missing")
        else:
            log.info("Instagram client disabled (env flag)")

    def is_active(self) -> bool:
        """Client enabled ve credentials var."""
        return self._active

    def post(self, text: str, *, image_path: Optional[str] = None) -> InstagramResponse:
        """Instagram post at (image + caption).

        Args:
            text: caption text
            image_path: local image path (tier2 render output)

        Returns:
            InstagramResponse with post_id and post_url
        """
        if not self._active:
            # No-op instead of exception - worker should skip, not fail
            return InstagramResponse(
                ok=False, dry_run=False, would_execute=False,
                post_id=None, post_url=None,
                stderr="Instagram client not active (credentials missing)",
                exit_code=-1,
            )

        if self.dry_run:
            return InstagramResponse(
                ok=True, dry_run=True, would_execute=True,
                post_id=None, post_url=None
            )

        try:
            # 1. Create container
            container_url = f"{BASE_URL}/{self._business_account_id}/media"
            container_data = {
                "image_url": image_path,  # In real implementation, upload image first
                "caption": text,
                "access_token": self._access_token,
            }

            response = requests.post(container_url, data=container_data, timeout=SUBPROCESS_TIMEOUT_SEC)
            container_result = response.json()

            if response.status_code != 200 or "id" not in container_result:
                return InstagramResponse(
                    ok=False, dry_run=False,
                    stderr=str(container_result),
                    exit_code=response.status_code,
                )

            container_id = container_result["id"]

            # 2. Publish container
            publish_url = f"{BASE_URL}/{self._business_account_id}/media_publish"
            publish_data = {
                "creation_id": container_id,
                "access_token": self._access_token,
            }

            response = requests.post(publish_url, data=publish_data, timeout=SUBPROCESS_TIMEOUT_SEC)
            publish_result = response.json()

            if response.status_code != 200 or "id" not in publish_result:
                return InstagramResponse(
                    ok=False, dry_run=False,
                    stderr=str(publish_result),
                    exit_code=response.status_code,
                )

            post_id = publish_result["id"]
            post_url = f"https://www.instagram.com/p/{post_id}"

            return InstagramResponse(
                ok=True, dry_run=False, would_execute=False,
                post_id=post_id, post_url=post_url,
                exit_code=response.status_code,
            )

        except Exception as e:
            log.error(f"Instagram post failed: {e}")
            return InstagramResponse(
                ok=False, dry_run=False,
                stderr=str(e),
                exit_code=-1,
            )

    def post_draft(self, draft) -> InstagramResponse:
        """ContentDraft -> Instagram post.

        Uses same interface as XurlClient for worker compatibility.

        Media resolution (2026-07-26 fix): the media is taken from the draft's
        own ``meta['media']`` — the rendered chart/clip paths that Lane D
        (``scripts/chart_render.py``) and Lane G (``scripts/lane_g_social.py``)
        already produced. The previous implementation imported a
        ``render_promo_card`` helper from ``tier2_renderers`` that does not
        exist in that module, so every Instagram publish raised ImportError
        before reaching the Graph API.
        """
        media = draft.meta.get("media") or []
        if isinstance(media, str):
            media = [media]
        image_path = next((m for m in media if str(m).lower().endswith(
            (".png", ".jpg", ".jpeg"))), None)
        if image_path is None and media:
            image_path = media[0]

        return self.post(text=draft.body, image_path=image_path)


# Singleton instance
_client_instance: Optional[InstagramClient] = None


def get_instagram_client() -> InstagramClient:
    """Get singleton Instagram client instance."""
    global _client_instance
    if _client_instance is None:
        _client_instance = InstagramClient()
    return _client_instance