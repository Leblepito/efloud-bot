"""End-to-end: synthetic log line + healthz payload → alerter dispatch + dedup.

Uses a real Dedup against tmp_path SQLite and a mocked send_message. Does NOT
spin up the full while-True main loop; calls the dispatch helpers directly.
"""
from __future__ import annotations

from pathlib import Path
from unittest import mock


def test_breaker_daily_log_fires_once_and_then_dedups(tmp_path: Path, monkeypatch):
    monkeypatch.setattr("ops.alerter.alerter.DEDUP_DB", str(tmp_path / "dedup.sqlite"))
    monkeypatch.setattr("ops.alerter.alerter.HEARTBEAT_FILE", str(tmp_path / "hb.json"))
    monkeypatch.setattr("ops.alerter.alerter.TELEGRAM_TOKEN", "TOK")
    monkeypatch.setattr("ops.alerter.alerter.TELEGRAM_CHAT_ID", "CHAT")

    from ops.alerter.alerter import Alerter

    rec = {
        "level": "WARNING",
        "logger": "efloud.breaker",
        # Realistic message — matches actual breaker.py:155 → _trip → log.warning
        # output. Rule requires both "BREAKER TRIPPED" and "Daily loss" substrings.
        "message": "🚨 BREAKER TRIPPED: Daily loss -5.12% exceeds -5.0% | Resume at 2026-05-08T00:00:00",
    }

    with mock.patch("ops.alerter.alerter.send_message", return_value=True) as send:
        a = Alerter()
        # Fire 1: first match → should send
        a._dispatch_log(rec)
        assert send.call_count == 1, "first matching log should fire telegram"
        first_text = send.call_args.args[2]
        assert "Daily" in first_text or "daily" in first_text.lower()

        # Fire 2: same record again → dedup blocks it (window is 24h for daily)
        a._dispatch_log(rec)
        assert send.call_count == 1, "duplicate within window should be deduped"


def test_health_crash_loop_payload_fires_once(tmp_path: Path, monkeypatch):
    monkeypatch.setattr("ops.alerter.alerter.DEDUP_DB", str(tmp_path / "dedup.sqlite"))
    monkeypatch.setattr("ops.alerter.alerter.HEARTBEAT_FILE", str(tmp_path / "hb.json"))
    monkeypatch.setattr("ops.alerter.alerter.TELEGRAM_TOKEN", "TOK")
    monkeypatch.setattr("ops.alerter.alerter.TELEGRAM_CHAT_ID", "CHAT")

    from ops.alerter.alerter import Alerter
    from ops.alerter.rules import HealthCrashLoopRule

    payload = {
        "status": "suspended",
        "failures": ["crash_loop_suspended"],
        "checks": {"crash_count": 3},
    }

    with mock.patch("ops.alerter.alerter.send_message", return_value=True) as send:
        a = Alerter()
        # Manually invoke the rule via _maybe_fire (the real flow goes through
        # _poll_healthz which makes a real HTTP request — out of scope here)
        rule = HealthCrashLoopRule()
        text = rule.match_health(payload, a.healthz_history)
        assert text is not None
        a._maybe_fire(rule, text)
        assert send.call_count == 1
        assert "CRASH LOOP" in send.call_args.args[2].upper()
