"""Overseer Summarizer — Claude API NL özet üretici.

Covers: offline mode, cost-cap guard, model/max_tokens contract,
usage accounting, error placeholder, lazy import. All Claude API calls
mocked via a Protocol-shaped fake — no real anthropic SDK call ever.
"""
from __future__ import annotations

import builtins
from typing import Any

import pytest


# ─────────────────────────────────────────────────────────────────────
# Test doubles — minimal stand-ins for the Anthropic client + state.
# ─────────────────────────────────────────────────────────────────────


class _Usage:
    def __init__(self, input_tokens: int, output_tokens: int):
        self.input_tokens = input_tokens
        self.output_tokens = output_tokens


class _Response:
    """Mimics anthropic.types.Message: content list + usage object."""

    def __init__(self, text: str, input_tokens: int = 100, output_tokens: int = 50):
        # Each content block is a typed object with .type and .text — we use
        # a SimpleNamespace-ish stand-in below to keep dependency surface zero.
        self.content = [type("Block", (), {"type": "text", "text": text})()]
        self.usage = _Usage(input_tokens, output_tokens)


class _FakeAnthropicClient:
    """Captures the last call args so tests can assert on model / messages."""

    def __init__(self, *, response: _Response | None = None, raise_exc: Exception | None = None):
        self._response = response or _Response("özet metni")
        self._raise_exc = raise_exc
        self.calls: list[dict[str, Any]] = []

    def messages_create(self, *, model: str, max_tokens: int, system: str, messages: list[dict]):
        self.calls.append(
            {"model": model, "max_tokens": max_tokens, "system": system, "messages": messages}
        )
        if self._raise_exc is not None:
            raise self._raise_exc
        return self._response


class _FakeState:
    """State double — tracks record_llm_call + lets tests pin calls-today."""

    def __init__(self, calls_today: int = 0):
        self._calls_today = calls_today
        self.recorded: list[tuple[int, int]] = []

    def get_llm_calls_today(self) -> int:
        return self._calls_today

    def record_llm_call(self, token_in: int, token_out: int) -> int:
        self.recorded.append((token_in, token_out))
        self._calls_today += 1
        return self._calls_today


# ─────────────────────────────────────────────────────────────────────
# Offline & cost-cap guards.
# ─────────────────────────────────────────────────────────────────────


def test_summarizer_offline_returns_placeholder(monkeypatch):
    """EFLOUD_OVERSEER_LLM_OFFLINE=1 → no API call, placeholder returned.

    Locks the deploy-time kill-switch: rollouts can stage the overseer
    without burning API quota before signing off on quality."""
    from ops.overseer.summarizer import Summarizer

    monkeypatch.setenv("EFLOUD_OVERSEER_LLM_OFFLINE", "1")
    state = _FakeState()
    client = _FakeAnthropicClient()
    s = Summarizer(state, client=client)

    out = s.hourly_summary(recent_log_lines=[], journal_recent=[])

    assert out == "<LLM offline>"
    assert client.calls == []
    assert state.recorded == []


def test_summarizer_cap_exceeded_returns_placeholder():
    """When today's calls already reached the daily cap, the next call is
    a no-op + placeholder, so a runaway loop can never blow the budget."""
    from ops.overseer.summarizer import Summarizer

    state = _FakeState(calls_today=500)
    client = _FakeAnthropicClient()
    s = Summarizer(state, client=client, daily_cap=500)

    out = s.hourly_summary(recent_log_lines=[], journal_recent=[])

    assert out == "<LLM cap exceeded>"
    assert client.calls == []
    assert state.recorded == []


def test_summarizer_is_offline_reads_env(monkeypatch):
    """is_offline() purely reflects the env var so callers can branch upfront."""
    from ops.overseer.summarizer import Summarizer

    state = _FakeState()
    client = _FakeAnthropicClient()
    s = Summarizer(state, client=client)

    monkeypatch.delenv("EFLOUD_OVERSEER_LLM_OFFLINE", raising=False)
    assert s.is_offline() is False
    monkeypatch.setenv("EFLOUD_OVERSEER_LLM_OFFLINE", "1")
    assert s.is_offline() is True


# ─────────────────────────────────────────────────────────────────────
# Hourly summary — happy path.
# ─────────────────────────────────────────────────────────────────────


def test_summarizer_hourly_calls_anthropic_with_correct_model(monkeypatch):
    """Locks the model + max_tokens contract — the only knob external
    callers should ever change is the constructor `model` arg."""
    from ops.overseer.summarizer import Summarizer

    monkeypatch.delenv("EFLOUD_OVERSEER_LLM_OFFLINE", raising=False)
    state = _FakeState()
    client = _FakeAnthropicClient(response=_Response("özet"))
    s = Summarizer(state, client=client)

    s.hourly_summary(
        recent_log_lines=[{"ts": "now", "level": "INFO", "msg": "tick"}],
        journal_recent=[{"symbol": "BTC/USDT"}],
    )

    assert len(client.calls) == 1
    call = client.calls[0]
    assert call["model"] == "claude-haiku-4-5-20251001"
    assert call["max_tokens"] == 600


def test_summarizer_hourly_records_llm_call_with_usage(monkeypatch):
    """Token deltas surfaced by the API must flow into the state counter so
    the daily-cap guard sees the real spend, not just call counts."""
    from ops.overseer.summarizer import Summarizer

    monkeypatch.delenv("EFLOUD_OVERSEER_LLM_OFFLINE", raising=False)
    state = _FakeState()
    client = _FakeAnthropicClient(response=_Response("özet", input_tokens=120, output_tokens=80))
    s = Summarizer(state, client=client)

    s.hourly_summary(recent_log_lines=[], journal_recent=[])

    assert state.recorded == [(120, 80)]


def test_summarizer_hourly_returns_text_content(monkeypatch):
    """The returned string must be the assistant's text — content[0].text —
    not the whole response object."""
    from ops.overseer.summarizer import Summarizer

    monkeypatch.delenv("EFLOUD_OVERSEER_LLM_OFFLINE", raising=False)
    state = _FakeState()
    client = _FakeAnthropicClient(response=_Response("son saatin durumu: bot çalışıyor"))
    s = Summarizer(state, client=client)

    out = s.hourly_summary(recent_log_lines=[], journal_recent=[])

    assert out == "son saatin durumu: bot çalışıyor"


def test_summarizer_hourly_passes_user_message_with_context(monkeypatch):
    """Recent log/journal data must reach the user message so the model can
    actually summarize *this hour*, not return a vague boilerplate."""
    from ops.overseer.summarizer import Summarizer

    monkeypatch.delenv("EFLOUD_OVERSEER_LLM_OFFLINE", raising=False)
    state = _FakeState()
    client = _FakeAnthropicClient()
    s = Summarizer(state, client=client)

    lines = [{"ts": "t1", "msg": "log entry A"}]
    journal = [{"symbol": "OP/USDT", "pnl_pct": "1.5"}]
    s.hourly_summary(recent_log_lines=lines, journal_recent=journal)

    msgs = client.calls[0]["messages"]
    assert isinstance(msgs, list) and len(msgs) >= 1
    user_text = msgs[-1].get("content", "")
    # User message must mention the data we passed (loose check — exact
    # serialization is impl detail, but the surface must include both).
    assert "log entry A" in user_text
    assert "OP/USDT" in user_text


# ─────────────────────────────────────────────────────────────────────
# Failure modes.
# ─────────────────────────────────────────────────────────────────────


def test_summarizer_api_exception_returns_error_placeholder(monkeypatch):
    """API failure must NOT raise — overseer is best-effort; placeholder
    lets the alerter/report keep running. state.record_llm_call must NOT
    fire for failed calls (no tokens spent at the application layer)."""
    from ops.overseer.summarizer import Summarizer

    monkeypatch.delenv("EFLOUD_OVERSEER_LLM_OFFLINE", raising=False)
    state = _FakeState()
    client = _FakeAnthropicClient(raise_exc=RuntimeError("boom"))
    s = Summarizer(state, client=client)

    out = s.hourly_summary(recent_log_lines=[], journal_recent=[])

    assert out == "<LLM error>"
    assert state.recorded == []


# ─────────────────────────────────────────────────────────────────────
# Daily report variant.
# ─────────────────────────────────────────────────────────────────────


def test_summarizer_daily_report_includes_metrics_in_prompt(monkeypatch):
    """daily_report serializes the metrics dict into the user message so the
    model can reason over them (and ops can read what was sent)."""
    from ops.overseer.summarizer import Summarizer

    monkeypatch.delenv("EFLOUD_OVERSEER_LLM_OFFLINE", raising=False)
    state = _FakeState()
    client = _FakeAnthropicClient(response=_Response("# Günlük rapor"))
    s = Summarizer(state, client=client)

    closed = [{"symbol": "BTC/USDT", "pnl_pct": "0.8", "reason": "TP1"}]
    metrics = {"trades": 5, "win_rate": "60%", "total_pnl_pct": "1.4"}
    out = s.daily_report(closed_trades_24h=closed, key_metrics=metrics)

    assert out == "# Günlük rapor"
    assert len(client.calls) == 1
    user_text = client.calls[0]["messages"][-1].get("content", "")
    assert "BTC/USDT" in user_text
    assert "win_rate" in user_text
    assert "60%" in user_text


def test_summarizer_daily_report_respects_offline(monkeypatch):
    """Daily report shares the offline kill-switch — same code path, same
    placeholder, so a single env flip silences both flows."""
    from ops.overseer.summarizer import Summarizer

    monkeypatch.setenv("EFLOUD_OVERSEER_LLM_OFFLINE", "1")
    state = _FakeState()
    client = _FakeAnthropicClient()
    s = Summarizer(state, client=client)

    out = s.daily_report(closed_trades_24h=[], key_metrics={})

    assert out == "<LLM offline>"
    assert client.calls == []


# ─────────────────────────────────────────────────────────────────────
# Lazy import guard.
# ─────────────────────────────────────────────────────────────────────


def test_summarizer_lazy_import_anthropic_only_when_needed(monkeypatch):
    """In offline mode the anthropic SDK must not be imported — required so
    the overseer can run in test/staging envs without the SDK installed."""
    from ops.overseer.summarizer import Summarizer

    real_import = builtins.__import__
    bad: list[str] = []

    def guard_import(name, *args, **kwargs):
        if name == "anthropic" or name.startswith("anthropic."):
            bad.append(name)
            raise ImportError(f"anthropic must not be imported in offline path: {name}")
        return real_import(name, *args, **kwargs)

    monkeypatch.setenv("EFLOUD_OVERSEER_LLM_OFFLINE", "1")
    state = _FakeState()
    # client=None forces the lazy path; offline guard must short-circuit first.
    s = Summarizer(state, client=None)

    monkeypatch.setattr(builtins, "__import__", guard_import)
    out = s.hourly_summary(recent_log_lines=[], journal_recent=[])

    assert out == "<LLM offline>"
    assert bad == []
