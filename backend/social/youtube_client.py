"""YouTube client - gTTS audio + tier2 visual + moviepy 9:16.

Activation:
- env YOUTUBE_ENABLED=true (default false → no-op)
- env YOUTUBE_OAUTH_REFRESH_TOKEN (required)

Interface: Same as XurlClient - post_draft(draft) -> YouTubeResponse(post_id, post_url)

Dependencies (optional - if missing, client no-ops):
- gTTS (audio)
- moviepy (video editing)
- google-api-python-client (YouTube Data API)
- google-auth-oauthlib (OAuth refresh)

Deps ekle: pip install gTTS moviepy google-api-python-client google-auth-oauthlib
"""
from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

log = logging.getLogger("efloud.youtube")

# ────────────────────────── Constants ──────────────────────────

SUBPROCESS_TIMEOUT_SEC = 30  # YouTube upload takes longer
MAX_LOG_BODY = 1024

# Try to import dependencies, set flag if missing
_GTTS_AVAILABLE = False
_MOVIEPY_AVAILABLE = False
_YOUTUBE_API_AVAILABLE = False

try:
    from gtts import gTTS
    _GTTS_AVAILABLE = True
except ImportError:
    log.warning("gTTS not available - YouTube client will be limited")

try:
    from moviepy.editor import CompositeVideoClip, ImageClip, AudioFileClip, TextClip, ColorClip
    _MOVIEPY_AVAILABLE = True
except ImportError:
    log.warning("moviepy not available - YouTube client will be limited")

try:
    import google.auth.transport.requests
    import google.oauth2.credentials
    from googleapiclient.discovery import build
    from googleapiclient.http import MediaFileUpload
    _YOUTUBE_API_AVAILABLE = True
except ImportError:
    log.warning("YouTube API libs not available - YouTube client will be limited")


# ────────────────────────── Exceptions ──────────────────────────


class YouTubeError(Exception):
    """Base YouTube client error."""


class YouTubeDisabled(YouTubeError):
    """Flag off veya credentials eksik."""


class YouTubeDependencyError(YouTubeError):
    """Required dependencies missing."""


class YouTubeSubprocessError(YouTubeError):
    """API call non-zero exit veya timeout."""


# ────────────────────────── Response ──────────────────────────


@dataclass
class YouTubeResponse:
    """Bir video upload çağrısının sonucu."""
    ok: bool
    dry_run: bool = False
    would_execute: bool = False
    post_id: Optional[str] = None  # YouTube video ID
    post_url: Optional[str] = None  # YouTube watch URL
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
    """YOUTUBE_ENABLED env truthy check."""
    raw = os.environ.get("YOUTUBE_ENABLED", "").strip().lower()
    return raw in ("1", "true", "yes", "on")


def _credential(name: str) -> Optional[str]:
    """YouTube credential env read."""
    raw = os.environ.get(name, "").strip()
    return raw if raw else None


# ────────────────────────── Client ──────────────────────────


class YouTubeClient:
    """YouTube client - gTTS audio + tier2 visual + moviepy 9:16."""

    def __init__(self, dry_run: bool = False):
        self.dry_run = dry_run
        self._active = False
        self._refresh_token = None
        self._youtube = None

        if not _enabled():
            log.info("YouTube client disabled (env flag)")
            return

        if not all([_GTTS_AVAILABLE, _MOVIEPY_AVAILABLE, _YOUTUBE_API_AVAILABLE]):
            log.warning("YouTube enabled but dependencies missing - no-op mode")
            return

        self._refresh_token = _credential("YOUTUBE_OAUTH_REFRESH_TOKEN")
        if self._refresh_token:
            self._active = True
            log.info("YouTube client active")
        else:
            log.warning("YouTube enabled but credentials missing")

    def is_active(self) -> bool:
        """Client enabled ve credentials var."""
        return self._active

    def _create_video(self, text: str, image_path: Optional[str] = None) -> Optional[str]:
        """Create 9:16 video from text and image.

        Returns:
            Path to generated video file or None if failed
        """
        if not all([_GTTS_AVAILABLE, _MOVIEPY_AVAILABLE]):
            return None

        try:
            # 1. Generate audio
            tts = gTTS(text=text, lang='tr', slow=False)
            audio_path = "cache/temp_audio.mp3"
            tts.save(audio_path)

            # 2. Create video
            audio = AudioFileClip(audio_path)
            duration = audio.duration

            # Background
            bg = ColorClip(size=(1080, 1920), color=(0, 0, 0), duration=duration)

            # Add image if provided
            if image_path and Path(image_path).exists():
                img = ImageClip(image_path).resize(height=1080).set_duration(duration)
                img = img.set_position("center")
                video = CompositeVideoClip([bg, img])
            else:
                video = bg

            # Set audio
            final_video = video.set_audio(audio)

            # Export
            output_path = "cache/temp_video.mp4"
            final_video.write_videofile(output_path, fps=24, codec="libx264", audio_codec="aac")

            return output_path

        except Exception as e:
            log.error(f"Video creation failed: {e}")
            return None

    def _refresh_credentials(self):
        """Refresh OAuth credentials."""
        if not _YOUTUBE_API_AVAILABLE:
            return False

        try:
            # Create credentials from refresh token
            credentials = google.oauth2.credentials.Credentials(
                token=None,
                refresh_token=self._refresh_token,
                token_uri="https://oauth2.googleapis.com/token",
                client_id=None,  # Not needed for refresh
                client_secret=None,
                scopes=["https://www.googleapis.com/auth/youtube.upload"]
            )

            # Refresh
            request = google.auth.transport.requests.Request()
            credentials.refresh(request)

            # Build YouTube service
            self._youtube = build("youtube", "v3", credentials=credentials)
            return True

        except Exception as e:
            log.error(f"OAuth refresh failed: {e}")
            return False

    def post(self, text: str, *, video_path: Optional[str] = None) -> YouTubeResponse:
        """YouTube Short upload (9:16 video).

        Args:
            text: video title/description
            video_path: local video path (generated or provided)

        Returns:
            YouTubeResponse with video_id and watch_url
        """
        if not self._active:
            # No-op instead of exception - worker should skip, not fail
            return YouTubeResponse(
                ok=False, dry_run=False, would_execute=False,
                post_id=None, post_url=None,
                stderr="YouTube client not active (credentials missing)",
                exit_code=-1,
            )

        if self.dry_run:
            return YouTubeResponse(
                ok=True, dry_run=True, would_execute=True,
                post_id=None, post_url=None
            )

        # Generate video if not provided
        if not video_path:
            from backend.social.tier2_renderers import render_promo_card
            image_path = render_promo_card(None)  # Will use default template
            video_path = self._create_video(text, image_path)

        if not video_path or not Path(video_path).exists():
            return YouTubeResponse(
                ok=False, dry_run=False,
                stderr="Video creation failed",
                exit_code=-1,
            )

        try:
            # Refresh credentials if needed
            if not self._youtube:
                if not self._refresh_credentials():
                    return YouTubeResponse(
                        ok=False, dry_run=False,
                        stderr="OAuth refresh failed",
                        exit_code=-1,
                    )

            # Upload video
            request = self._youtube.videos().insert(
                part="snippet,status",
                body={
                    "snippet": {
                        "title": text[:100],  # YouTube title limit
                        "description": text,
                        "categoryId": "22",  # People & Blogs
                    },
                    "status": {
                        "privacyStatus": "public",  # Or "unlisted" for testing
                    }
                },
                media_body=MediaFileUpload(video_path, resumable=True)
            )

            response = request.Execute()

            if "id" not in response:
                return YouTubeResponse(
                    ok=False, dry_run=False,
                    stderr=str(response),
                    exit_code=-1,
                )

            video_id = response["id"]
            post_url = f"https://www.youtube.com/watch?v={video_id}"

            return YouTubeResponse(
                ok=True, dry_run=False, would_execute=False,
                post_id=video_id, post_url=post_url,
                exit_code=200,
            )

        except Exception as e:
            log.error(f"YouTube upload failed: {e}")
            return YouTubeResponse(
                ok=False, dry_run=False,
                stderr=str(e),
                exit_code=-1,
            )

    def post_draft(self, draft) -> YouTubeResponse:
        """ContentDraft -> YouTube Short.

        Uses same interface as XurlClient for worker compatibility.
        """
        return self.post(text=draft.body, video_path=None)


# Singleton instance
_client_instance: Optional[YouTubeClient] = None


def get_youtube_client() -> YouTubeClient:
    """Get singleton YouTube client instance."""
    global _client_instance
    if _client_instance is None:
        _client_instance = YouTubeClient()
    return _client_instance