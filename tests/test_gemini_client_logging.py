"""A2: a real GeminiClient failure must surface at WARNING, not hide at DEBUG.

The advisory layer is fail-safe ({} on any error), but at DEBUG the operator
could not tell a *broken* key/model (every call 404'ing → silent NEUTRAL, the
A1 class) from a genuinely NEUTRAL verdict. Promote the failure log to WARNING,
rate-limited (1st + every Nth) so a persistent outage doesn't spam every cycle.
A missing key stays silent (an expected fail-safe, not an error).
"""
import logging

import httpx
import pytest

from engine.agents import gemini_client as gc
from engine.agents.gemini_client import GeminiClient

_LOGGER = "efloud.agents.gemini_client"


def _raise_conn(*a, **k):
    raise httpx.ConnectError("simulated network down")


def test_real_failure_logs_at_warning(monkeypatch, caplog):
    monkeypatch.setattr(gc.httpx, "post", _raise_conn)
    monkeypatch.setattr(gc, "_consecutive_failures", 0, raising=False)
    client = GeminiClient(api_key="fake-key")
    with caplog.at_level(logging.WARNING, logger=_LOGGER):
        assert client.complete_json("x") == {}
    assert any(r.levelno >= logging.WARNING for r in caplog.records), (
        "a real LLM failure must surface at WARNING, not be silent at DEBUG"
    )


def test_missing_key_stays_silent(caplog):
    client = GeminiClient(api_key=None)
    with caplog.at_level(logging.WARNING, logger=_LOGGER):
        assert client.complete_json("x") == {}
    assert not caplog.records, "missing key is an expected fail-safe, not an error"


def test_repeated_failures_are_rate_limited(monkeypatch, caplog):
    monkeypatch.setattr(gc.httpx, "post", _raise_conn)
    monkeypatch.setattr(gc, "_consecutive_failures", 0, raising=False)
    client = GeminiClient(api_key="fake-key")
    with caplog.at_level(logging.WARNING, logger=_LOGGER):
        for _ in range(10):
            client.complete_json("x")
    warns = [r for r in caplog.records if r.levelno >= logging.WARNING]
    assert 1 <= len(warns) < 10, "WARNING must be rate-limited, not one per failed call"
