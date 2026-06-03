"""MiniMaxClient — MiniMax (OpenAI-compatible) backend for the advisory layer.

Drop-in replacement for the other LLM clients: same ``complete_json(prompt) -> dict``
contract + canonical ``{}`` fail-safe. Key travels in the ``Authorization: Bearer``
header (never the URL). Response is OpenAI-shaped (``choices[0].message.content``).
"""
import logging

import httpx

from engine.agents import minimax_client as mc
from engine.agents.minimax_client import MiniMaxClient

_LOGGER = "efloud.agents.minimax_client"


def _fake_openai_response(text: str):
    body = {"choices": [{"message": {"role": "assistant", "content": text}}]}
    return httpx.Response(200, json=body, request=httpx.Request("POST", "https://x"))


def test_complete_json_parses_openai_response(monkeypatch):
    def fake_post(url, **kw):
        return _fake_openai_response('{"verdict": "ACCEPT", "confidence": 0.7}')

    monkeypatch.setattr(mc.httpx, "post", fake_post)
    client = MiniMaxClient(api_key="fake-key")
    assert client.complete_json("x") == {"verdict": "ACCEPT", "confidence": 0.7}


def test_api_key_in_bearer_header_not_url(monkeypatch):
    captured = {}

    def fake_post(url, **kw):
        captured["url"] = url
        captured["kw"] = kw
        return _fake_openai_response('{"ok": true}')

    monkeypatch.setattr(mc.httpx, "post", fake_post)
    client = MiniMaxClient(api_key="super-secret-key")
    client.complete_json("x")
    assert "super-secret-key" not in captured["url"], "key must NOT be in the URL"
    headers = captured["kw"].get("headers", {})
    assert headers.get("Authorization") == "Bearer super-secret-key"


def test_missing_key_returns_empty_and_silent(caplog):
    client = MiniMaxClient(api_key=None)
    with caplog.at_level(logging.WARNING, logger=_LOGGER):
        assert client.complete_json("x") == {}
    assert not caplog.records, "missing key is an expected fail-safe, not an error"


def test_http_error_is_fail_safe(monkeypatch):
    def boom(*a, **k):
        raise httpx.ConnectError("network down")

    monkeypatch.setattr(mc.httpx, "post", boom)
    assert MiniMaxClient(api_key="fake-key").complete_json("x") == {}


def test_bad_json_is_fail_safe(monkeypatch):
    monkeypatch.setattr(mc.httpx, "post", lambda url, **kw: _fake_openai_response("not json"))
    assert MiniMaxClient(api_key="fake-key").complete_json("x") == {}


def test_strips_markdown_fences(monkeypatch):
    monkeypatch.setattr(
        mc.httpx, "post",
        lambda url, **kw: _fake_openai_response('```json\n{"verdict": "REJECT"}\n```'),
    )
    assert MiniMaxClient(api_key="fake-key").complete_json("x") == {"verdict": "REJECT"}


def test_default_model_is_fast_variant():
    assert "M2.7" in MiniMaxClient(api_key="k").model


def test_strips_reasoning_think_block(monkeypatch):
    """MiniMax-M2 is a reasoning model: it emits <think>...</think> before the
    answer. The client must drop the think block and parse the trailing JSON."""
    raw = ('<think>\nThe user wants JSON. I should output the verdict.\n</think>\n\n'
           '{"verdict": "ACCEPT", "confidence": 0.6}')
    monkeypatch.setattr(mc.httpx, "post", lambda url, **kw: _fake_openai_response(raw))
    assert MiniMaxClient(api_key="fake-key").complete_json("x") == {
        "verdict": "ACCEPT", "confidence": 0.6}


def test_extracts_json_amid_prose(monkeypatch):
    """Even without a think block, tolerate stray prose around the JSON object."""
    raw = 'Here is the result: {"valid": true, "confidence": 0.9} — done.'
    monkeypatch.setattr(mc.httpx, "post", lambda url, **kw: _fake_openai_response(raw))
    assert MiniMaxClient(api_key="fake-key").complete_json("x") == {
        "valid": True, "confidence": 0.9}


def test_default_max_tokens_has_reasoning_budget():
    # Reasoning models burn tokens on the think block before the answer; the
    # default must leave room for the JSON to actually appear.
    assert MiniMaxClient(api_key="k").max_tokens >= 1500
