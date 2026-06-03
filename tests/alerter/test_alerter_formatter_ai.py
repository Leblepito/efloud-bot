import pytest
from unittest.mock import patch
from ops.alerter.formatter import format_alert_with_ai


def test_format_alert_with_ai_fallback():
    """When the LLM yields nothing (no key / outage → {}), return raw text."""
    from engine.agents import claude_client as cc
    with patch.object(cc.ClaudeClient, "complete_json", return_value={}):
        res = format_alert_with_ai("raw alert message", "WARNING", "breaker.tripped.consecutive")
        assert res == "raw alert message"


def test_format_alert_with_ai_success():
    """A successful LLM JSON payload is rendered to structured HTML.

    Default provider is Claude — patch ClaudeClient.complete_json (the client
    already handles the Anthropic response shape + fence stripping internally).
    """
    payload = {
        "emoji": "⚠️", "title": "Breaker Tripped", "severity": "WARNING",
        "event_type": "breaker", "summary": "Consecutive losses exceeded",
        "details": "3 consecutive losses", "action_required": "Check strategies",
    }
    from engine.agents import claude_client as cc
    with patch.object(cc.ClaudeClient, "complete_json", return_value=payload):
        res = format_alert_with_ai("raw msg", "WARNING", "breaker.tripped.consecutive")

    assert "⚠️ <b>Breaker Tripped</b>" in res
    assert "(WARNING)" in res
    assert "<b>Event:</b> <code>breaker</code>" in res
    assert "<b>Summary:</b> Consecutive losses exceeded" in res
    assert "<b>Details:</b> 3 consecutive losses" in res
    assert "⚠️ <b>Action Required:</b> <i>Check strategies</i>" in res
