"""Overseer sink wrappers — telegram + email. Both delegate to existing ops/
clients (no duplicate transport code) and must never raise on transport error."""
from __future__ import annotations

from unittest import mock


def test_send_overseer_message_calls_alerter_with_prefix(monkeypatch):
    """CRITICAL severity prepends 🚨 — keeps alert triage glanceable in TG."""
    monkeypatch.setenv("EFLOUD_TELEGRAM_TOKEN", "TOK")
    monkeypatch.setenv("EFLOUD_TELEGRAM_CHAT_ID", "123")

    captured: dict = {}

    def fake_send_message(token, chat_id, text, parse_mode="HTML"):
        captured["token"] = token
        captured["chat_id"] = chat_id
        captured["text"] = text
        return True

    monkeypatch.setattr(
        "ops.overseer.sinks.telegram.send_message", fake_send_message
    )

    from ops.overseer.sinks.telegram import send_overseer_message

    ok = send_overseer_message("hello", severity="CRITICAL")
    assert ok is True
    assert captured["token"] == "TOK"
    assert captured["chat_id"] == "123"
    assert captured["text"].startswith("\U0001F6A8")  # 🚨


def test_send_overseer_message_returns_false_on_exception(monkeypatch):
    """Transport failure must NOT propagate — overseer's caller handles retry."""
    monkeypatch.setenv("EFLOUD_TELEGRAM_TOKEN", "TOK")
    monkeypatch.setenv("EFLOUD_TELEGRAM_CHAT_ID", "123")

    def boom(*_a, **_kw):
        raise RuntimeError("simulated network blow-up")

    monkeypatch.setattr("ops.overseer.sinks.telegram.send_message", boom)

    from ops.overseer.sinks.telegram import send_overseer_message

    ok = send_overseer_message("hi", severity="INFO")
    assert ok is False


def test_send_overseer_message_uses_info_prefix_by_default(monkeypatch):
    """Default severity INFO maps to ℹ️ — proves severity dispatch covers default."""
    monkeypatch.setenv("EFLOUD_TELEGRAM_TOKEN", "TOK")
    monkeypatch.setenv("EFLOUD_TELEGRAM_CHAT_ID", "123")
    captured: dict = {}

    def fake_send_message(token, chat_id, text, parse_mode="HTML"):
        captured["text"] = text
        return True

    monkeypatch.setattr("ops.overseer.sinks.telegram.send_message", fake_send_message)
    from ops.overseer.sinks.telegram import send_overseer_message

    send_overseer_message("status update")
    assert captured["text"].startswith("ℹ")  # ℹ️ starts with U+2139


def test_send_overseer_email_calls_smtp_with_subject(monkeypatch):
    """Subject + body forwarded verbatim to ops.daily_report.smtp_client.send_email."""
    monkeypatch.setenv("EFLOUD_SMTP_HOST", "smtp.example.com")
    monkeypatch.setenv("EFLOUD_SMTP_PORT", "587")
    monkeypatch.setenv("EFLOUD_SMTP_USERNAME", "bot@example.com")
    monkeypatch.setenv("EFLOUD_SMTP_PASSWORD", "PW")
    monkeypatch.setenv("EFLOUD_SMTP_FROM", "bot@example.com")
    monkeypatch.setenv("EFLOUD_SMTP_TO", "ops@example.com")

    captured: dict = {}

    def fake_send_email(**kwargs):
        captured.update(kwargs)
        return True

    monkeypatch.setattr(
        "ops.overseer.sinks.email.send_email", fake_send_email
    )

    from ops.overseer.sinks.email import send_overseer_email

    ok = send_overseer_email("Daily report", "## Hello\n\nBody text")
    assert ok is True
    assert captured["subject"] == "Daily report"
    assert "Hello" in captured["body"]
    assert captured["to_addr"] == "ops@example.com"
    assert captured["host"] == "smtp.example.com"
    assert captured["port"] == 587


def test_send_overseer_email_uses_env_default_recipient(monkeypatch):
    """`to=None` falls back to EFLOUD_SMTP_TO — keeps callers env-driven."""
    monkeypatch.setenv("EFLOUD_SMTP_HOST", "smtp.example.com")
    monkeypatch.setenv("EFLOUD_SMTP_PORT", "587")
    monkeypatch.setenv("EFLOUD_SMTP_USERNAME", "bot@example.com")
    monkeypatch.setenv("EFLOUD_SMTP_PASSWORD", "PW")
    monkeypatch.setenv("EFLOUD_SMTP_FROM", "bot@example.com")
    monkeypatch.setenv("EFLOUD_SMTP_TO", "foo@x")

    captured: dict = {}

    def fake_send_email(**kwargs):
        captured.update(kwargs)
        return True

    monkeypatch.setattr("ops.overseer.sinks.email.send_email", fake_send_email)
    from ops.overseer.sinks.email import send_overseer_email

    send_overseer_email("Subj", "Body")
    assert captured["to_addr"] == "foo@x"


def test_send_overseer_email_explicit_to_overrides_env(monkeypatch):
    """Explicit recipient wins over EFLOUD_SMTP_TO — supports ad-hoc routing."""
    monkeypatch.setenv("EFLOUD_SMTP_HOST", "smtp.example.com")
    monkeypatch.setenv("EFLOUD_SMTP_PORT", "587")
    monkeypatch.setenv("EFLOUD_SMTP_USERNAME", "bot@example.com")
    monkeypatch.setenv("EFLOUD_SMTP_PASSWORD", "PW")
    monkeypatch.setenv("EFLOUD_SMTP_FROM", "bot@example.com")
    monkeypatch.setenv("EFLOUD_SMTP_TO", "default@x")

    captured: dict = {}

    def fake_send_email(**kwargs):
        captured.update(kwargs)
        return True

    monkeypatch.setattr("ops.overseer.sinks.email.send_email", fake_send_email)
    from ops.overseer.sinks.email import send_overseer_email

    send_overseer_email("Subj", "Body", to="override@y")
    assert captured["to_addr"] == "override@y"


def test_send_overseer_email_returns_false_on_exception(monkeypatch):
    """SMTP transport failure must NOT propagate — keeps cron caller in control."""
    monkeypatch.setenv("EFLOUD_SMTP_HOST", "smtp.example.com")
    monkeypatch.setenv("EFLOUD_SMTP_USERNAME", "bot@example.com")
    monkeypatch.setenv("EFLOUD_SMTP_PASSWORD", "PW")
    monkeypatch.setenv("EFLOUD_SMTP_TO", "foo@x")

    def boom(**_kw):
        raise OSError("connection refused")

    monkeypatch.setattr("ops.overseer.sinks.email.send_email", boom)
    from ops.overseer.sinks.email import send_overseer_email

    ok = send_overseer_email("S", "B")
    assert ok is False
