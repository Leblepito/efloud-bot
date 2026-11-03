"""OpenRouter (OpenAI-compatible) client — advisory LLM backend.

Drop-in sibling of :class:`engine.agents.claude_client.ClaudeClient`: identical
``complete_json(prompt) -> dict`` contract and the same canonical fail-safe —
``{}`` on ANY failure (no key, HTTP error, JSON parse, timeout). Callers MUST
treat ``{}`` as "no LLM opinion" and fall back to deterministic logic; the bot
must NEVER crash because the LLM is down.

Why OpenRouter instead of a direct provider SDK:
  * ONE key (``OPENROUTER_API_KEY``) reaches every model — switching the
    advisory model becomes a config edit, not an env/key migration.
  * It speaks the OpenAI chat-completions dialect, but this client talks to it
    over ``httpx`` — already a bot dependency — instead of the ``openai``
    package, which is NOT in ``requirements.txt``/``constraints.txt``. That
    keeps the bot image unchanged and avoids ever constructing a client with a
    missing SDK (the latent trap in ``deepseek_client.py``).
  * The key travels in the ``Authorization: Bearer`` header, never in the URL,
    so it cannot leak into an httpx error string.

Cost/latency default is ``deepseek/deepseek-v4.1-flash`` — the fast tier the
operator picked on 2026-11-03. Override per deployment with
``config["model"]`` (or the ``LLM_PROVIDER`` env lever for the provider).

The failure log mirrors the Claude/Gemini clients' A2 behaviour: a genuine
failure surfaces at WARNING (rate-limited) so a broken key/model stays visible
without spamming every cycle; a missing key stays silent (expected fail-safe).
"""

from __future__ import annotations

import logging
import os
from typing import Any, Dict, Optional

import httpx

from .claude_client import _extract_json

log = logging.getLogger("efloud.agents.openrouter")

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"

# Canonical default — DeepSeek V4.1 Flash: fast + cheap, but reasoning-capable,
# so it fits both the per-trade team review and the per-signal advisory.
DEFAULT_MODEL = "deepseek/deepseek-v4.1-flash"

_SYSTEM_PROMPT = (
    "You are a JSON-only API. Reply with a single valid JSON object and nothing "
    "else: no markdown fences, no commentary, no trailing text."
)

# Module-level so the rate-limiter spans all callers sharing the backend.
_consecutive_failures = 0
# Surface the 1st failure, then every Nth, to avoid per-cycle WARNING spam.
_WARN_EVERY = 20


class OpenRouterClient:
    """Thin wrapper around OpenRouter's ``/api/v1/chat/completions``.

    Tests can pass ``api_key=None`` to short-circuit to ``{}`` (the canonical
    fail-safe) without any network access.
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: str = DEFAULT_MODEL,
        *,
        timeout: float = 30.0,
        max_tokens: int = 1024,
        referer: Optional[str] = None,
        title: str = "efloud-bot",
    ) -> None:
        self.api_key = api_key or os.getenv("OPENROUTER_API_KEY")
        self.model = model
        self.timeout = float(timeout)
        self.max_tokens = int(max_tokens)
        # Optional OpenRouter attribution headers — never send an empty value
        # (some proxies reject blank headers).
        self.referer = referer or os.getenv("OPENROUTER_HTTP_REFERER") or None
        self.title = title or None

    def complete_json(self, prompt: str, *, timeout: Optional[float] = None) -> Dict[str, Any]:
        """Single-shot JSON call. Returns the parsed object, or ``{}`` on any failure."""
        global _consecutive_failures
        if not self.api_key:
            return {}  # expected fail-safe (no key) — silent, not an error

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "content-type": "application/json",
        }
        if self.referer:
            headers["HTTP-Referer"] = self.referer
        if self.title:
            headers["X-Title"] = self.title

        payload = {
            "model": self.model,
            "max_tokens": self.max_tokens,
            "temperature": 0.2,
            "messages": [
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
        }
        try:
            r = httpx.post(
                OPENROUTER_URL, headers=headers, json=payload,
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
                    "OpenRouterClient.complete_json failed (#%d, returning {}): %r",
                    _consecutive_failures, e,
                )
            return {}


__all__ = ["OpenRouterClient", "DEFAULT_MODEL", "OPENROUTER_URL"]
