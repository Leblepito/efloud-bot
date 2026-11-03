"""Provider factory for the advisory LLM backend.

Resolves which LLM client the advisory layer uses from config, so the three
call sites (agent team, macro sentiment, structure validation) stay in sync.
Default is Claude; Gemini remains selectable as a fallback. Both backends
duck-type ``complete_json(prompt) -> dict`` with the canonical ``{}`` fail-safe,
so callers are agnostic to which one they hold.

Config (under ``agent_team`` / ``llm`` / the sentiment block, as applicable):
    provider: claude | openrouter | gemini | minimax | deepseek   # default: claude
    model:    <provider model id>         # default: that provider's DEFAULT_MODEL
    api_key:  <optional override>         # else read from the provider's env var
"""

from __future__ import annotations

import os
from typing import Any, Dict, Optional

from .claude_client import ClaudeClient, DEFAULT_MODEL as CLAUDE_DEFAULT_MODEL
from .gemini_client import GeminiClient, DEFAULT_MODEL as GEMINI_DEFAULT_MODEL
from .minimax_client import MiniMaxClient, DEFAULT_MODEL as MINIMAX_DEFAULT_MODEL
from .deepseek_client import DeepSeekClient, DEFAULT_MODEL as DEEPSEEK_DEFAULT_MODEL
from .openrouter_client import OpenRouterClient, DEFAULT_MODEL as OPENROUTER_DEFAULT_MODEL

# Provider → the env var that carries its key. Adding a provider here is what
# makes ``provider_key_present()`` (and therefore the startup/sentiment gate in
# ``backend/bot_runner.py``) aware of it — a new backend that is missing from
# this map would look "unconfigured" and its advisory calls would be skipped.
PROVIDER_KEY_ENV: Dict[str, str] = {
    "claude": "ANTHROPIC_API_KEY",
    "gemini": "GEMINI_API_KEY",
    "minimax": "MINIMAX_API_KEY",
    "deepseek": "DEEPSEEK_API_KEY",
    "openrouter": "OPENROUTER_API_KEY",
}

DEFAULT_PROVIDER = "claude"


def resolve_provider(config: Optional[Dict[str, Any]] = None) -> str:
    """Provider resolution order: ``config["provider"]`` → ``LLM_PROVIDER`` env → ``claude``."""
    cfg = dict(config or {})
    return str(cfg.get("provider") or os.getenv("LLM_PROVIDER") or DEFAULT_PROVIDER).strip().lower()


def provider_key_present(config: Optional[Dict[str, Any]] = None) -> bool:
    """True when the resolved provider has a usable key.

    Callers use this to skip an advisory call that would return ``{}`` anyway
    (and to log *why* it was skipped). An unknown provider resolves to the
    default backend, so its key is what we look for.
    """
    cfg = dict(config or {})
    if cfg.get("api_key"):
        return True
    env_name = PROVIDER_KEY_ENV.get(resolve_provider(cfg), PROVIDER_KEY_ENV[DEFAULT_PROVIDER])
    return bool(os.getenv(env_name))


def make_llm_client(config: Optional[Dict[str, Any]] = None):
    """Build the configured LLM client. Unknown providers fall back to Claude.

    Provider resolution order: ``config["provider"]`` → ``LLM_PROVIDER`` env →
    ``"claude"``. The env var is the single global lever: set e.g.
    ``LLM_PROVIDER=minimax`` (or ``gemini``) to switch every call site (agent
    team, sentiment, structure validation, alerter) at once, even the ones that
    hold no config. A bad ``provider`` value must never crash the bot — it
    degrades to the default backend, consistent with the advisory layer's
    fail-safe ethos.
    """
    cfg = dict(config or {})
    provider = resolve_provider(cfg)
    api_key = cfg.get("api_key")
    model = cfg.get("model")

    if provider == "gemini":
        return GeminiClient(api_key=api_key, model=model or GEMINI_DEFAULT_MODEL)
    if provider == "minimax":
        return MiniMaxClient(api_key=api_key, model=model or MINIMAX_DEFAULT_MODEL)
    if provider == "deepseek":
        return DeepSeekClient(api_key=api_key, model=model or DEEPSEEK_DEFAULT_MODEL)
    if provider == "openrouter":
        return OpenRouterClient(api_key=api_key, model=model or OPENROUTER_DEFAULT_MODEL)
    # default + unknown → claude
    return ClaudeClient(api_key=api_key, model=model or CLAUDE_DEFAULT_MODEL)
