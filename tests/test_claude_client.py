"""ClaudeClient — Anthropic Messages backend for the advisory LLM layer.

Drop-in replacement for ``GeminiClient``: same ``complete_json(prompt) -> dict``
contract, same canonical fail-safe (``{}`` on ANY failure). Two things it fixes
over the Gemini client by construction:
  * the API key travels in the ``x-api-key`` HEADER, never in the URL, so it
    cannot leak into an httpx error string (the Gemini ``?key=`` leak); and
  * it targets a real, stable Anthropic model alias (no 404-class regression).
"""
import json
import logging

import httpx
import pytest

from engine.agents import claude_client as cc
from engine.agents.claude_client import ClaudeClient

_LOGGER = "efloud.agents.claude_client"


def _fake_anthropic_response(text: str):
    """Build a minimal httpx.Response shaped like Anthropic /v1/messages."""
    body = {"content": [{"type": "text", "text": text}]}
    return httpx.Response(200, json=body, request=httpx.Request("POST", "https://x"))


def test_complete_json_parses_anthropic_response(monkeypatch):
    captured = {}

    def fake_post(url, **kw):
        captured["url"] = url
        captured["kw"] = kw
        return _fake_anthropic_response('{"verdict": "ACCEPT", "confidence": 0.8}')

    monkeypatch.setattr(cc.httpx, "post", fake_post)
    client = ClaudeClient(api_key="fake-key")
    out = client.complete_json("rate this trade")
    assert out == {"verdict": "ACCEPT", "confidence": 0.8}


def test_api_key_in_header_not_url(monkeypatch):
    captured = {}

    def fake_post(url, **kw):
        captured["url"] = url
        captured["kw"] = kw
        return _fake_anthropic_response('{"ok": true}')

    monkeypatch.setattr(cc.httpx, "post", fake_post)
    client = ClaudeClient(api_key="super-secret-key")
    client.complete_json("x")
    assert "super-secret-key" not in captured["url"], "API key must NOT be in the URL"
    headers = captured["kw"].get("headers", {})
    assert headers.get("x-api-key") == "super-secret-key", "key must travel in x-api-key header"
    assert "anthropic-version" in headers


def test_missing_key_returns_empty_and_silent(caplog):
    client = ClaudeClient(api_key=None)
    with caplog.at_level(logging.WARNING, logger=_LOGGER):
        assert client.complete_json("x") == {}
    assert not caplog.records, "missing key is an expected fail-safe, not an error"


def test_http_error_is_fail_safe(monkeypatch):
    def boom(*a, **k):
        raise httpx.ConnectError("network down")

    monkeypatch.setattr(cc.httpx, "post", boom)
    client = ClaudeClient(api_key="fake-key")
    assert client.complete_json("x") == {}


def test_bad_json_is_fail_safe(monkeypatch):
    def fake_post(url, **kw):
        return _fake_anthropic_response("this is not json at all")

    monkeypatch.setattr(cc.httpx, "post", fake_post)
    client = ClaudeClient(api_key="fake-key")
    assert client.complete_json("x") == {}


def test_strips_markdown_fences(monkeypatch):
    """Claude sometimes wraps JSON in ```json fences; the client must tolerate it."""
    def fake_post(url, **kw):
        return _fake_anthropic_response('```json\n{"verdict": "REJECT"}\n```')

    monkeypatch.setattr(cc.httpx, "post", fake_post)
    client = ClaudeClient(api_key="fake-key")
    assert client.complete_json("x") == {"verdict": "REJECT"}
