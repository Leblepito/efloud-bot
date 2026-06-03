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
    here is ``gemini-2.0-flash`` (a real, callable v1beta alias). All
    callers MUST reference ``DEFAULT_MODEL`` rather than hardcoding a
    literal — a non-existent alias 404s on every call and silently
    degrades the whole advisory layer to NEUTRAL (see A1 regression test).
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

# Canonical default — a REAL Gemini alias on the v1beta generateContent
# endpoint. Do NOT pin a non-existent alias here (an earlier invalid alias
# 404'd on every call). Override per deployment via ``agent_team.model``.
DEFAULT_MODEL = "gemini-2.0-flash"

# A2: surface real call failures at WARNING (not silent DEBUG) so a broken
# key/model is visible — but rate-limit so a persistent outage doesn't spam
# every cycle. Module-level (clients are constructed per-call in some callers).
_consecutive_failures = 0
_WARN_EVERY = 25  # WARNING on the 1st failure and every 25th thereafter


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
        global _consecutive_failures
        if not self.api_key:
            return {}  # expected fail-safe (no key) — silent, not an error
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
            result = json.loads(text)
            _consecutive_failures = 0  # A2: recovered → reset the rate-limiter
            return result
        except Exception as e:
            # A2: a genuine failure (HTTP/parse/timeout) — surface at WARNING so a
            # broken key/model is visible, rate-limited to avoid per-cycle spam.
            _consecutive_failures += 1
            msg = (f"GeminiClient.complete_json failed "
                   f"(#{_consecutive_failures}, returning {{}}): {e!r}")
            if _consecutive_failures == 1 or _consecutive_failures % _WARN_EVERY == 0:
                log.warning(msg)
            else:
                log.debug(msg)
            return {}
