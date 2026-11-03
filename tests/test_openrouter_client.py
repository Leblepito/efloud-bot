"""OpenRouterClient — OpenRouter (OpenAI-compatible) backend for the advisory LLM layer.

Same contract as ``ClaudeClient``: ``complete_json(prompt) -> dict`` with the
canonical fail-safe (``{}`` on ANY failure — no key, HTTP error, JSON parse).
One key (``OPENROUTER_API_KEY``) reaches every model, and the call goes over
``httpx`` (already a bot dependency) rather than the ``openai`` package, which is
NOT in requirements.txt/constraints.txt.
"""
import logging

import httpx
import pytest

from engine.agents import openrouter_client as orc
from engine.agents.openrouter_client import OpenRouterClient, DEFAULT_MODEL

_LOGGER = "efloud.agents.openrouter"


def _fake_openai_response(text: str):
    """Build a minimal httpx.Response shaped like OpenAI chat-completions."""
    body = {"choices": [{"message": {"role": "assistant", "content": text}}]}
    return httpx.Response(200, json=body, request=httpx.Request("POST", "https://x"))


@pytest.fixture(autouse=True)
def _reset_failure_counter():
    """The module-level rate-limiter is shared; keep tests independent."""
    orc._consecutive_failures = 0
    yield
    orc._consecutive_failures = 0


def test_complete_json_parses_openai_shaped_response(monkeypatch):
    captured = {}

    def fake_post(url, **kw):
        captured["url"] = url
        captured["kw"] = kw
        return _fake_openai_response('{"verdict": "ACCEPT", "confidence": 0.8}')

    monkeypatch.setattr(orc.httpx, "post", fake_post)
    out = OpenRouterClient(api_key="fake-key").complete_json("rate this trade")
    assert out == {"verdict": "ACCEPT", "confidence": 0.8}
    assert captured["url"] == orc.OPENROUTER_URL


def test_api_key_in_header_not_url(monkeypatch):
    captured = {}

    def fake_post(url, **kw):
        captured["url"] = url
        captured["kw"] = kw
        return _fake_openai_response('{"ok": true}')

    monkeypatch.setattr(orc.httpx, "post", fake_post)
    OpenRouterClient(api_key="super-secret-key").complete_json("x")
    assert "super-secret-key" not in captured["url"], "API key must NOT be in the URL"
    headers = captured["kw"].get("headers", {})
    assert headers.get("Authorization") == "Bearer super-secret-key"
    assert "content-type" in headers


def test_model_is_sent_in_the_payload(monkeypatch):
    captured = {}

    def fake_post(url, **kw):
        captured["kw"] = kw
        return _fake_openai_response('{"ok": true}')

    monkeypatch.setattr(orc.httpx, "post", fake_post)
    OpenRouterClient(api_key="fake-key", model="deepseek/deepseek-v4-pro").complete_json("x")
    assert captured["kw"]["json"]["model"] == "deepseek/deepseek-v4-pro"
    assert captured["kw"]["json"]["messages"][0]["role"] == "system"


def test_default_model_is_the_deepseek_flash_slug():
    assert DEFAULT_MODEL == "deepseek/deepseek-v4.1-flash"
    assert OpenRouterClient(api_key="k").model == DEFAULT_MODEL


def test_missing_key_returns_empty_and_silent(monkeypatch, caplog):
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    with caplog.at_level(logging.WARNING, logger=_LOGGER):
        assert OpenRouterClient(api_key=None).complete_json("x") == {}
    assert not caplog.records, "missing key is an expected fail-safe, not an error"


def test_http_error_is_fail_safe(monkeypatch):
    def boom(*a, **k):
        raise httpx.ConnectError("network down")

    monkeypatch.setattr(orc.httpx, "post", boom)
    assert OpenRouterClient(api_key="fake-key").complete_json("x") == {}


def test_http_401_is_fail_safe_and_warns_once(monkeypatch, caplog):
    def fake_post(url, **kw):
        return httpx.Response(401, json={"error": "invalid key"},
                              request=httpx.Request("POST", "https://x"))

    monkeypatch.setattr(orc.httpx, "post", fake_post)
    with caplog.at_level(logging.WARNING, logger=_LOGGER):
        assert OpenRouterClient(api_key="fake-key").complete_json("x") == {}
    assert any("OpenRouterClient.complete_json failed" in r.getMessage()
               for r in caplog.records), "a broken key must be visible, not silent"


def test_bad_json_is_fail_safe(monkeypatch):
    monkeypatch.setattr(orc.httpx, "post",
                        lambda url, **kw: _fake_openai_response("this is not json at all"))
    assert OpenRouterClient(api_key="fake-key").complete_json("x") == {}


def test_strips_markdown_fences_and_think_blocks(monkeypatch):
    """Reasoning models (DeepSeek) may wrap JSON in fences or a  thinking block."""
    monkeypatch.setattr(orc.httpx, "post", lambda url, **kw: _fake_openai_response(
        '```json\n{"verdict": "REJECT"}\n```'
    ))
    assert OpenRouterClient(api_key="fake-key").complete_json("x") == {"verdict": "REJECT"}

    monkeypatch.setattr(orc.httpx, "post", lambda url, **kw: _fake_openai_response(
        ' thinkingcheck the structure first</think>\n{"verdict": "NEUTRAL"}'
    ))
    assert OpenRouterClient(api_key="fake-key").complete_json("x") == {"verdict": "NEUTRAL"}

    # Stray prose around the object also survives (first {...} span wins).
    monkeypatch.setattr(orc.httpx, "post", lambda url, **kw: _fake_openai_response(
        'Here is my review:\n{"verdict": "ACCEPT"}\nHope that helps.'
    ))
    assert OpenRouterClient(api_key="fake-key").complete_json("x") == {"verdict": "ACCEPT"}


def test_failure_counter_resets_after_a_success(monkeypatch):
    monkeypatch.setattr(orc.httpx, "post", lambda url, **kw: _fake_openai_response(
        '{"ok": true}'
    ))
    OpenRouterClient(api_key="fake-key").complete_json("x")
    assert orc._consecutive_failures == 0
