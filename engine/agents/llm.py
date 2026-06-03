"""Provider factory for the advisory LLM backend.

Resolves which LLM client the advisory layer uses from config, so the three
call sites (agent team, macro sentiment, structure validation) stay in sync.
Default is Claude; Gemini remains selectable as a fallback. Both backends
duck-type ``complete_json(prompt) -> dict`` with the canonical ``{}`` fail-safe,
so callers are agnostic to which one they hold.

Config (under ``agent_team`` / ``llm`` / the sentiment block, as applicable):
    provider: claude | gemini     # default: claude
    model:    <provider model id> # default: that provider's DEFAULT_MODEL
    api_key:  <optional override>  # else read from the provider's env var
"""

from __future__ import annotations

import os
from typing import Any, Dict, Optional

from .claude_client import ClaudeClient, DEFAULT_MODEL as CLAUDE_DEFAULT_MODEL
from .gemini_client import GeminiClient, DEFAULT_MODEL as GEMINI_DEFAULT_MODEL


def make_llm_client(config: Optional[Dict[str, Any]] = None):
    """Build the configured LLM client. Unknown providers fall back to Claude.

    Provider resolution order: ``config["provider"]`` → ``LLM_PROVIDER`` env →
    ``"claude"``. The env var is the single global lever: set ``LLM_PROVIDER=gemini``
    to revert every call site (agent team, sentiment, structure validation) at
    once, even the ones that hold no config. A bad ``provider`` value must never
    crash the bot — it degrades to the default backend, consistent with the
    advisory layer's fail-safe ethos.
    """
    cfg = dict(config or {})
    provider = str(cfg.get("provider") or os.getenv("LLM_PROVIDER") or "claude").strip().lower()
    api_key = cfg.get("api_key")
    model = cfg.get("model")

    if provider == "gemini":
        return GeminiClient(api_key=api_key, model=model or GEMINI_DEFAULT_MODEL)
    # default + unknown → claude
    return ClaudeClient(api_key=api_key, model=model or CLAUDE_DEFAULT_MODEL)
