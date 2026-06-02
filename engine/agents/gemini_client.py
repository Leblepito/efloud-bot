"""Common Gemini REST client — single source of truth for LLM HTTP calls.

This is the shared client used by:
  * ``engine.ai.sentiment`` (macro sentiment)
  * ``engine.signals``     (validate_signal_with_gemini)
  * ``engine.agents.*``     (role agents)

Behaviour contract (do not break without updating all callers):
  * ``complete_json`` returns ``{}`` on ANY failure (no key, HTTP error,
    JSON parse, timeout, etc). The caller MUST treat ``{}`` as
    "no LLM opinion" and fall back to deterministic logic. This is the
    canonical fail-safe: the bot must NEVER crash because Gemini is down.

  * Model is pinned in config (``agent_team.model`` etc). The default
    here is ``gemini-1.5-flash`` per the canonical plan; if you bump
    the alias, also update the configs and re-test fail-safe.
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any, Dict, Optional

import httpx

log = logging.getLogger("efloud.agents.gemini_client")

GEMINI_URL = (
    "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
)

# Canonical default. ``gemini-2.0-flash`` is also stable on the v1beta
# endpoint as of 2026-06; switch via config when ready.
DEFAULT_MODEL = "gemini-3.5-flash"


class GeminiClient:
    """Thin wrapper around Gemini's generateContent REST endpoint.

    Designed to be a drop-in replacement for the inline ``httpx.post``
    calls previously scattered across the codebase. Tests can pass
    ``api_key=None`` to short-circuit to ``{}`` (the canonical fail-safe).
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: str = DEFAULT_MODEL,
        *,
        timeout: float = 20.0,
    ) -> None:
        self.api_key = api_key or os.getenv("GEMINI_API_KEY")
        self.model = model
        self.timeout = float(timeout)

    def complete_json(self, prompt: str, *, timeout: Optional[float] = None) -> Dict[str, Any]:
        """Single-shot JSON call.

        Returns the parsed JSON on success, or ``{}`` on any failure
        (missing key, HTTP error, JSON parse, unexpected schema). The
        caller is expected to treat ``{}`` as "no opinion".
        """
        if not self.api_key:
            return {}
        url = GEMINI_URL.format(model=self.model) + f"?key={self.api_key}"
        payload = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {
                "temperature": 0.2,
                "response_mime_type": "application/json",
            },
        }
        try:
            r = httpx.post(url, json=payload, timeout=timeout or self.timeout)
            r.raise_for_status()
            text = r.json()["candidates"][0]["content"]["parts"][0]["text"]
            return json.loads(text)
        except Exception as e:
            log.debug(f"GeminiClient.complete_json failed (returning {{}}): {e!r}")
            return {}
