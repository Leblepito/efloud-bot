"""
X (Twitter) publisher via xurl CLI — Lane E adapter.

xurl Go binary (T-026) bu publisher'ın transport katmanı:
  - Default OFF (config.xurl.enabled = false → publish noop)
  - Single-tweet: xurl post <body> --media=<url> --reply-to=<id>
  - Thread: ilk tweet reply chain olarak

Compliance:
  - Envelope payload scripts.content_compliance.find_violations'tan geçmiş olmalı
  - Bu kontrol publisher'da değil LaneEPublisher'da (defense in depth)
  - Burada tekrar kontrol etmiyoruz (zaten pending_review → approved gate)
"""
from __future__ import annotations

import logging
import shutil
import subprocess
from typing import Optional

from .base import PublishResult, Publisher

logger = logging.getLogger(__name__)


class XurlPublisher(Publisher):
    """xurl CLI üzerinden X/Twitter'a yayın.

    Env:
        X_API_ENABLED=true → gerçek publish
        X_API_ENABLED=false (default) → noop (PublishResult.ok=True, ref=None)
    """

    name = "xurl"
    enabled = False  # default OFF; config.xurl.enabled ile override

    def __init__(self, enabled: Optional[bool] = None) -> None:
        if enabled is not None:
            self.enabled = enabled
        self._binary_path: str | None = None
        self._binary_checked = False

    def _binary_available(self) -> bool:
        """xurl binary yüklü mü? Cache'li kontrol (her publish'ta aramaz)."""
        if not self._binary_checked:
            self._binary_path = shutil.which("xurl")
            self._binary_checked = True
        return self._binary_path is not None

    def publish(self, envelope: dict) -> PublishResult:
        """Envelope → X post.

        Envelope contract:
            {
                "draft_id": "...",
                "body": "caption text",
                "media": ["url1", "url2"],          # optional
                "thread": ["tweet2", "tweet3", ...], # optional (first = body)
                "reply_to": "post_id",                # optional (chain)
            }
        """
        if not self.enabled:
            logger.info("xurl publisher disabled (X_API_ENABLED=false) → noop")
            return PublishResult(platform=self.name, ok=True, ref=None)

        if not self._binary_available():
            return PublishResult(
                platform=self.name,
                ok=False,
                error=f"xurl binary bulunamadı (PATH'ya ekleyin veya XURL_BIN_PATH env)",
            )

        body = envelope.get("body", "")
        media = envelope.get("media", [])
        thread = envelope.get("thread", [])
        reply_to = envelope.get("reply_to")

        try:
            # Single tweet veya thread'in ilk tweet'i
            ref = self._post_single(body, media=media, reply_to=reply_to)

            # Thread devamı
            last_ref = ref
            for tweet in thread:
                last_ref = self._post_single(tweet, media=[], reply_to=last_ref)

            return PublishResult(platform=self.name, ok=True, ref=ref)
        except Exception as e:
            logger.exception("xurl publish failed")
            return PublishResult(platform=self.name, ok=False, error=str(e))

    def _post_single(
        self,
        body: str,
        media: list[str] | None = None,
        reply_to: str | None = None,
    ) -> str:
        """xurl subprocess call → platform post id."""
        assert self._binary_path is not None, "binary_available=True ama path None"

        cmd = [self._binary_path, "post", body]
        for url in media or []:
            cmd.extend(["--media", url])
        if reply_to:
            cmd.extend(["--reply-to", reply_to])

        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=30,
            check=True,
        )
        # xurl stdout: son satır post_id (tweet ID)
        # Format örnek: "Posted: https://x.com/ualgotrade/status/1234567890"
        # Son satırdan ID çıkar (basit parsing)
        stdout = result.stdout.strip()
        # "Posted: <url>" veya sadece "<id>" olabilir
        if "status/" in stdout:
            return stdout.split("status/")[-1].split()[0].rstrip("/")
        return stdout.splitlines()[-1] if stdout else ""
