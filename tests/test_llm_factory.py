"""make_llm_client — provider switch for the advisory LLM backend.

One factory so the three call sites (agent team, macro sentiment, structure
validation) all resolve the same provider from config. Default is Claude
(``provider: claude``); Gemini stays selectable as a fallback. Both backends
duck-type the ``complete_json(prompt) -> dict`` contract.
"""
from engine.agents.llm import (
    make_llm_client,
    provider_key_present,
    resolve_provider,
    PROVIDER_KEY_ENV,
)
from engine.agents.claude_client import ClaudeClient
from engine.agents.gemini_client import GeminiClient
from engine.agents.minimax_client import MiniMaxClient
from engine.agents.openrouter_client import OpenRouterClient, DEFAULT_MODEL as OR_DEFAULT_MODEL


def test_default_is_claude():
    client = make_llm_client({})
    assert isinstance(client, ClaudeClient)


def test_explicit_minimax():
    client = make_llm_client({"provider": "minimax"})
    assert isinstance(client, MiniMaxClient)
    assert "M2.7" in client.model


def test_minimax_model_override():
    client = make_llm_client({"provider": "minimax", "model": "MiniMax-M2.5"})
    assert isinstance(client, MiniMaxClient)
    assert client.model == "MiniMax-M2.5"


def test_minimax_via_env_lever(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "minimax")
    assert isinstance(make_llm_client(), MiniMaxClient)


def test_explicit_claude():
    client = make_llm_client({"provider": "claude", "model": "claude-haiku-4-5-20251001"})
    assert isinstance(client, ClaudeClient)
    assert client.model == "claude-haiku-4-5-20251001"  # gitleaks:allow (model ID, not a secret)


def test_explicit_gemini_fallback():
    client = make_llm_client({"provider": "gemini", "model": "gemini-2.0-flash"})
    assert isinstance(client, GeminiClient)
    assert client.model == "gemini-2.0-flash"


def test_provider_is_case_insensitive():
    assert isinstance(make_llm_client({"provider": "CLAUDE"}), ClaudeClient)
    assert isinstance(make_llm_client({"provider": "Gemini"}), GeminiClient)


def test_api_key_passthrough():
    client = make_llm_client({"provider": "claude", "api_key": "k123"})
    assert client.api_key == "k123"


def test_unknown_provider_defaults_to_claude():
    # An unrecognised provider must not crash the bot — fall back to the default.
    assert isinstance(make_llm_client({"provider": "bogus"}), ClaudeClient)


def test_llm_provider_env_is_global_lever(monkeypatch):
    # A site that passes no config still honours LLM_PROVIDER — the single
    # global switch to revert everything to gemini.
    monkeypatch.setenv("LLM_PROVIDER", "gemini")
    assert isinstance(make_llm_client(), GeminiClient)
    assert isinstance(make_llm_client({}), GeminiClient)


def test_config_provider_overrides_env(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "gemini")
    # explicit config beats the env fallback
    assert isinstance(make_llm_client({"provider": "claude"}), ClaudeClient)


# ── OpenRouter (operator decision 2026-11-03) ──────────────────────────────────


def test_explicit_openrouter():
    client = make_llm_client({"provider": "openrouter"})
    assert isinstance(client, OpenRouterClient)
    assert client.model == OR_DEFAULT_MODEL


def test_openrouter_model_override():
    client = make_llm_client({"provider": "openrouter", "model": "deepseek/deepseek-v4-pro"})
    assert isinstance(client, OpenRouterClient)
    assert client.model == "deepseek/deepseek-v4-pro"


def test_openrouter_via_env_lever(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "openrouter")
    assert isinstance(make_llm_client(), OpenRouterClient)
    assert isinstance(make_llm_client({"provider": "OPENROUTER"}), OpenRouterClient)


def test_openrouter_api_key_from_env(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-fixture-key")
    assert OpenRouterClient().api_key == "test-fixture-key"


# ── provider_key_present: the startup/sentiment gate ──────────────────────────


def test_resolve_provider_precedence(monkeypatch):
    assert resolve_provider({}) == "claude"
    assert resolve_provider(None) == "claude"
    monkeypatch.setenv("LLM_PROVIDER", "OpenRouter")
    assert resolve_provider({}) == "openrouter"
    assert resolve_provider({"provider": "Claude"}) == "claude"  # config wins


def test_key_present_reads_the_resolved_provider_env(monkeypatch):
    # A hard-coded ANTHROPIC/GEMINI check used to skip a working OpenRouter
    # deployment; the gate must follow the resolved provider's env var.
    for env_name in PROVIDER_KEY_ENV.values():
        monkeypatch.delenv(env_name, raising=False)
    monkeypatch.setenv("OPENROUTER_API_KEY", "x")
    assert provider_key_present({"provider": "openrouter"}) is True
    assert provider_key_present({"provider": "claude"}) is False
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    assert provider_key_present({"provider": "openrouter"}) is False


def test_key_present_honours_an_inline_config_key(monkeypatch):
    for env_name in PROVIDER_KEY_ENV.values():
        monkeypatch.delenv(env_name, raising=False)
    assert provider_key_present({"provider": "openrouter", "api_key": "inline"}) is True


def test_key_present_unknown_provider_falls_back_to_default_backend(monkeypatch):
    for env_name in PROVIDER_KEY_ENV.values():
        monkeypatch.delenv(env_name, raising=False)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "x")
    # unknown provider → claude client → claude key is the one that matters
    assert provider_key_present({"provider": "bogus"}) is True
