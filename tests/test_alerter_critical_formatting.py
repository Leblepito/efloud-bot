"""CRITICAL alerts keep their raw text and survive Telegram HTML parsing (T-20261107-17).

LLM-layer audit 2026-11-07:
- A3: CRITICAL safety alerts (breaker HALT, crash loop, ...) went through the LLM
  formatter, which rewrote summary/details/action and dropped the raw text.
- A4: alert text was sent with parse_mode=HTML without escaping; a stray `<`
  (the emergency-HALT reason reads "balance $X < $Y") can make Telegram reject
  the message, so the alert is lost until the next matching log line.
"""
from __future__ import annotations

import io
import urllib.error
from pathlib import Path
from unittest import mock

import pytest

from ops.alerter.formatter import StructuredAlert, render_alert_html
from ops.alerter.rules import BreakerDailyRule, BreakerWeeklyRule
from ops.alerter.telegram_client import send_message


@pytest.fixture
def alerter(tmp_path: Path, monkeypatch):
    monkeypatch.setattr("ops.alerter.alerter.DEDUP_DB", str(tmp_path / "dedup.sqlite"))
    monkeypatch.setattr("ops.alerter.alerter.HEARTBEAT_FILE", str(tmp_path / "hb.json"))
    monkeypatch.setattr("ops.alerter.alerter.TELEGRAM_TOKEN", "TOK")
    monkeypatch.setattr("ops.alerter.alerter.TELEGRAM_CHAT_ID", "CHAT")
    from ops.alerter.alerter import Alerter
    return Alerter()


HALT_REC = {
    "level": "ERROR",
    "logger": "efloud.breaker",
    "message": "⛔ BREAKER HALTED: Weekly drawdown 25.40% reached limit 25.0% | MANUAL RESET REQUIRED",
}


def test_critical_alert_bypasses_llm_formatter(alerter):
    with mock.patch("ops.alerter.alerter.format_alert_with_ai") as fmt, \
            mock.patch("ops.alerter.alerter.send_message", return_value=True) as send:
        alerter._dispatch_log(HALT_REC)
    fmt.assert_not_called()
    assert "Weekly drawdown 25.40%" in send.call_args.args[2]


def test_non_critical_alert_still_uses_llm_formatter(alerter):
    rec = {
        "level": "WARNING",
        "logger": "efloud.breaker",
        "message": "BREAKER TRIPPED: 3 consecutive losses | Resume at 2026-11-07T20:00:00",
    }
    with mock.patch("ops.alerter.alerter.format_alert_with_ai", return_value="FMT") as fmt, \
            mock.patch("ops.alerter.alerter.send_message", return_value=True) as send:
        alerter._dispatch_log(rec)
    fmt.assert_called_once()
    assert send.call_args.args[2] == "FMT"


@pytest.mark.parametrize("rule_cls, message", [
    (BreakerDailyRule, "BREAKER TRIPPED: Daily loss -5.12% exceeds -5.0% <limit> & more"),
    (BreakerWeeklyRule, "BREAKER HALTED: Weekly drawdown 25% reached limit 25.0% <x>"),
])
def test_breaker_rules_escape_log_message(rule_cls, message):
    text = rule_cls().match_log({"level": "ERROR", "logger": "efloud.breaker", "message": message})
    assert "&lt;" in text and "<limit>" not in text and "<x>" not in text
    assert text.startswith("🚨 <b>")  # the rule's own markup stays


def test_rendered_llm_fields_are_escaped():
    html_out = render_alert_html(StructuredAlert(
        emoji="⚠️", title="a <b>", severity="WARNING", event_type="breaker",
        summary="loss < 5%", details="x & y", action_required="<script>",
    ))
    assert "loss &lt; 5%" in html_out and "x &amp; y" in html_out
    assert "<script>" not in html_out and "a <b>" not in html_out


def _http_400(body: bytes):
    return urllib.error.HTTPError("u", 400, "Bad Request", {}, io.BytesIO(body))


def test_html_parse_rejection_is_retried_as_plain_text():
    ok_resp = mock.MagicMock()
    ok_resp.__enter__.return_value.status = 200
    calls = []

    def fake_urlopen(req, timeout):
        calls.append(req.data.decode())
        if len(calls) == 1:
            raise _http_400(b'{"ok":false,"description":"Bad Request: can\'t parse entities"}')
        return ok_resp

    with mock.patch("ops.alerter.telegram_client.urllib.request.urlopen", side_effect=fake_urlopen):
        ok = send_message("TOK", "CHAT", "🚨 <b>HALT</b>\nbalance $10 < $20 &amp; x")
    assert ok is True and len(calls) == 2
    assert "parse_mode" not in calls[1]
    import urllib.parse
    retried = urllib.parse.parse_qs(calls[1])["text"][0]
    assert retried == "🚨 HALT\nbalance $10 < $20 & x"


def test_other_http_errors_are_not_retried():
    calls = []

    def fake_urlopen(req, timeout):
        calls.append(1)
        raise _http_400(b'{"ok":false,"description":"Bad Request: chat not found"}')

    with mock.patch("ops.alerter.telegram_client.urllib.request.urlopen", side_effect=fake_urlopen):
        assert send_message("TOK", "CHAT", "<b>x</b>") is False
    assert len(calls) == 1
