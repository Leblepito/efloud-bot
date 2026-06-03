"""Anthropic (Claude) Messages client — advisory LLM backend.

Drop-in replacement for :class:`engine.agents.gemini_client.GeminiClient`:
identical ``complete_json(prompt) -> dict`` contract and the same canonical
fail-safe — ``{}`` on ANY failure (no key, HTTP error, JSON parse, timeout).
Callers MUST treat ``{}`` as "no LLM opinion" and fall back to deterministic
logic; the bot must NEVER crash because the LLM is down.

Why Claude over the Gemini client (see [[efloud-audit-2026-06-02]]):
  * The API key travels in the ``x-api-key`` HEADER, never in the URL, so it
    cannot leak into an httpx error string (the Gemini ``?key=`` URL leak).
  * Stable model alias — no 404-class silent-degradation regression.

The failure log mirrors the Gemini client's A2 behaviour: a genuine failure
surfaces at WARNING (rate-limited) so a broken key/model is visible without
spamming every cycle; a missing key stays silent (an expected fail-safe).
"""

from __future__ import annotations

import json
import logging
import os
import re
from typing import Any, Dict, Optional

import httpx

log = logging.getLogger("efloud.agents.claude_client")

ANTHROPIC_URL = "https://api.anthropic.com/v1/messages"
ANTHROPIC_VERSION = "2023-06-01"

# Canonical default — Haiku 4.5: fast + cheap, ideal for a per-signal advisory
# that does not need heavy reasoning. Override per deployment via config.
DEFAULT_MODEL = "claude-haiku-4-5-20251001"

# Module-level so the rate-limiter spans all callers sharing the backend.
_consecutive_failures = 0
# Surface the 1st failure, then every Nth, to avoid per-cycle WARNING spam.
_WARN_EVERY = 20


def _extract_json(text: str) -> Dict[str, Any]:
    """Parse a JSON object out of an LLM's text.

    Tolerates, in order: reasoning models that prepend a ``<think>…</think>``
    block (e.g. MiniMax-M2), ```json fences, and stray prose around the object
    (fallback: parse the first ``{…}`` span). Raises if no JSON is present —
    the caller's ``complete_json`` converts that to the canonical ``{}``.
    """
    s = text.strip()
    # Reasoning models emit a think block before the answer — drop it.
    if "<think>" in s:
        s = re.sub(r"<think>.*?</think>", "", s, flags=re.DOTALL).strip()
    if s.startswith("```"):
        # strip a leading ```json / ``` fence and the trailing ```
        s = s.split("```", 2)[1] if s.count("```") >= 2 else s.strip("`")
        if s.lstrip().lower().startswith("json"):
            s = s.lstrip()[4:]
        s = s.strip().rstrip("`").strip()
    try:
        return json.loads(s)
    except Exception:
        # Fallback: pull the first balanced-looking {...} span out of prose.
        m = re.search(r"\{.*\}", s, flags=re.DOTALL)
        if m:
            return json.loads(m.group(0))
        raise


class ClaudeClient:
    """Thin wrapper around Anthropic's ``/v1/messages`` REST endpoint.

    Tests can pass ``api_key=None`` to short-circuit to ``{}`` (the canonical
    fail-safe) without any network access.
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: str = DEFAULT_MODEL,
        *,
        timeout: float = 20.0,
        max_tokens: int = 1024,
    ) -> None:
        self.api_key = api_key or os.getenv("ANTHROPIC_API_KEY")
        self.model = model
        self.timeout = float(timeout)
        self.max_tokens = int(max_tokens)

    def complete_json(self, prompt: str, *, timeout: Optional[float] = None) -> Dict[str, Any]:
        """Single-shot JSON call. Returns the parsed object, or ``{}`` on any failure."""
        global _consecutive_failures
        if not self.api_key:
            return {}  # expected fail-safe (no key) — silent, not an error
        headers = {
            "x-api-key": self.api_key,
            "anthropic-version": ANTHROPIC_VERSION,
            "content-type": "application/json",
        }
        payload = {
            "model": self.model,
            "max_tokens": self.max_tokens,
            "temperature": 0.2,
            "messages": [{"role": "user", "content": prompt}],
        }
        try:
            r = httpx.post(
                ANTHROPIC_URL, headers=headers, json=payload,
                timeout=timeout or self.timeout,
            )
            r.raise_for_status()
            text = r.json()["content"][0]["text"]
            result = _extract_json(text)
            _consecutive_failures = 0  # recovered → reset the rate-limiter
            return result
        except Exception as e:
            _consecutive_failures += 1
            if _consecutive_failures == 1 or _consecutive_failures % _WARN_EVERY == 0:
                log.warning(
                    "ClaudeClient.complete_json failed (#%d, returning {}): %r",
                    _consecutive_failures, e,
                )
            return {}
