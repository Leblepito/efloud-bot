"""MiniMax (OpenAI-compatible) Messages client — advisory LLM backend.

Drop-in replacement for :class:`engine.agents.claude_client.ClaudeClient` /
``GeminiClient``: identical ``complete_json(prompt) -> dict`` contract and the
same canonical ``{}`` fail-safe (no key, HTTP error, JSON parse, timeout).
Callers MUST treat ``{}`` as "no LLM opinion" and fall back to deterministic
logic; the bot must NEVER crash because the LLM is down.

MiniMax exposes an OpenAI-compatible chat-completions endpoint. The API key
travels in the ``Authorization: Bearer`` header (never the URL → no log leak),
and the response is OpenAI-shaped (``choices[0].message.content``). There is no
dedicated JSON mode, so the prompt asks for raw JSON and we tolerate ```json
fences via the shared :func:`_extract_json` helper.
"""

from __future__ import annotations

import logging
import os
from typing import Any, Dict, Optional

import httpx

# Reuse the fence-tolerant JSON extractor (single source of truth).
from .claude_client import _extract_json

log = logging.getLogger("efloud.agents.minimax_client")

MINIMAX_URL = "https://api.minimax.io/v1/chat/completions"

# Canonical default — the fast M2.7 variant: low latency, ideal for a per-signal
# advisory. Override per deployment via config ``model``. Other valid aliases:
# MiniMax-M2.7, MiniMax-M2.5(-highspeed), MiniMax-M2.1, MiniMax-M2, MiniMax-M3.
DEFAULT_MODEL = "MiniMax-M2.7-highspeed"

_consecutive_failures = 0
_WARN_EVERY = 20


class MiniMaxClient:
    """Thin wrapper around MiniMax's OpenAI-compatible chat-completions endpoint.

    Tests can pass ``api_key=None`` to short-circuit to ``{}`` (the canonical
    fail-safe) without any network access.
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: str = DEFAULT_MODEL,
        *,
        timeout: float = 30.0,
        max_tokens: int = 2048,
    ) -> None:
        # max_tokens is generous on purpose: M2.x reasoning models spend tokens
        # on a <think> block before the JSON answer; too small a budget truncates
        # the answer (finish_reason=length → {}). timeout likewise allows for the
        # reasoning latency. _extract_json strips the think block.
        self.api_key = api_key or os.getenv("MINIMAX_API_KEY")
        self.model = model
        self.timeout = float(timeout)
        self.max_tokens = int(max_tokens)

    def complete_json(self, prompt: str, *, timeout: Optional[float] = None) -> Dict[str, Any]:
        """Single-shot JSON call. Returns the parsed object, or ``{}`` on any failure."""
        global _consecutive_failures
        if not self.api_key:
            return {}  # expected fail-safe (no key) — silent, not an error
        headers = {
            "Authorization": f"Bearer {self.api_key}",
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
                MINIMAX_URL, headers=headers, json=payload,
                timeout=timeout or self.timeout,
            )
            r.raise_for_status()
            text = r.json()["choices"][0]["message"]["content"]
            result = _extract_json(text)
            _consecutive_failures = 0  # recovered → reset the rate-limiter
            return result
        except Exception as e:
            _consecutive_failures += 1
            if _consecutive_failures == 1 or _consecutive_failures % _WARN_EVERY == 0:
                log.warning(
                    "MiniMaxClient.complete_json failed (#%d, returning {}): %r",
                    _consecutive_failures, e,
                )
            return {}
