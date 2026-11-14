"""LuxAlgo zone alerts (T-20261104-08) — read-only operator early warning.

The alerter tails the bot's JSON log. These rules turn the existing `[lux]`
transition lines and `[v2 reject]` lines into Telegram messages so the operator
sees "price is at / near a zone the bot is tracking" and "the bot rejected the
entry, here is the rule" without reading logs. Default OFF
(EFLOUD_ALERTER_LUX_ALERTS); no order path is involved.
"""
from __future__ import annotations

from pathlib import Path
from unittest import mock

import pytest

from ops.alerter.rules import RULES, LuxZoneAlertRule, V2RejectAlertRule

FLAG = "EFLOUD_ALERTER_LUX_ALERTS"


def _rec(msg, logger="efloud.safe_orch", level="INFO"):
    return {"level": level, "logger": logger, "message": msg}


TOUCH = "[lux] touch ETH/USDT LONG bars=3 price=2315.2 zone=[2309.09-2319.13]"
NEAR = "[lux] near ETH/USDT LONG bars=3 price=2330.5 zone=[2309.09-2319.13] | dist=0.81 ATR"
CONFIRMED = "[lux] confirmed ETH/USDT LONG bars=4 price=2316 zone=[2309.09-2319.13] | entry=2316"
REJECT = "[v2 reject] ETH/USDT: sl_too_far (stop 812.0 > max 640.0)"


@pytest.fixture
def on(monkeypatch):
    monkeypatch.setenv(FLAG, "1")


def test_rules_are_registered():
    kinds = {type(r) for r in RULES}
    assert LuxZoneAlertRule in kinds and V2RejectAlertRule in kinds


@pytest.mark.parametrize("msg", [TOUCH, NEAR, CONFIRMED, REJECT])
def test_default_off_matches_nothing(monkeypatch, msg):
    monkeypatch.delenv(FLAG, raising=False)
    assert LuxZoneAlertRule().match_log(_rec(msg)) is None
    assert V2RejectAlertRule().match_log(_rec(msg)) is None


@pytest.mark.parametrize("msg,word", [(NEAR, "yaklaşıyor"), (TOUCH, "bölgede"), (CONFIRMED, "teyit")])
def test_zone_events_fire_when_on(on, msg, word):
    out = LuxZoneAlertRule().match_log(_rec(msg))
    assert out is not None
    assert "ETH/USDT LONG" in out and "2309.09-2319.13" in out and word in out
    assert "işlem sinyali değil" in out


@pytest.mark.parametrize("msg", [
    "[lux] left ETH/USDT LONG bars=3 price=2325 zone=[2309.09-2319.13]",
    "[lux] reentry ETH/USDT LONG bars=3 price=2315 zone=[2309.09-2319.13]",
    "[lux] expired ETH/USDT LONG after 49 bars (state was waiting for pullback)",
    "[lux] setup+ ETH/USDT LONG zone=[2309.09-2319.13] sl_anchor=2309.09 | LUX internal CHoCH",
    "[lux] scan ETH/USDT htf_bias=BULL ltf_swing=BULL ltf_internal=BULL last_break=x active_obs=5 cands=3 eq=1",
])
def test_noisy_or_flapping_lux_lines_are_ignored(on, msg):
    assert LuxZoneAlertRule().match_log(_rec(msg)) is None


def test_other_loggers_and_levels_are_ignored(on):
    assert LuxZoneAlertRule().match_log(_rec(TOUCH, logger="efloud.runner")) is None
    assert LuxZoneAlertRule().match_log(_rec(TOUCH, level="DEBUG")) is None
    assert V2RejectAlertRule().match_log(_rec(REJECT, logger="efloud.runner")) is None


def test_reject_fires_with_rule_name(on):
    out = V2RejectAlertRule().match_log(_rec(REJECT))
    assert out is not None and "ETH/USDT" in out and "sl_too_far" in out


def test_gate_lines_are_not_rejects(on):
    gate = "[v2 gate] ETH/USDT LONG setup dropped at emit: zone 12.3 ATR away > max_entry_dist_atr 12.0 (src=OB)"
    assert V2RejectAlertRule().match_log(_rec(gate)) is None


def test_dedup_keys_are_per_symbol_event_zone_and_reason(on):
    z = LuxZoneAlertRule()
    k_touch = z.dedup_key(_rec(TOUCH))
    k_conf = z.dedup_key(_rec(CONFIRMED))
    k_other = z.dedup_key(_rec(TOUCH.replace("ETH/USDT", "BTC/USDT")))
    assert len({k_touch, k_conf, k_other}) == 3
    r = V2RejectAlertRule()
    k1 = r.dedup_key(_rec(REJECT))
    k2 = r.dedup_key(_rec(REJECT.replace("sl_too_far", "tp1_too_close")))
    assert k1 != k2 and k1.startswith(r.alert_key)


def test_alerter_dispatch_dedups_per_event_not_per_rule(tmp_path: Path, monkeypatch, on):
    """Two different zones fire twice; the same zone event again is deduped."""
    monkeypatch.setattr("ops.alerter.alerter.DEDUP_DB", str(tmp_path / "dedup.sqlite"))
    monkeypatch.setattr("ops.alerter.alerter.HEARTBEAT_FILE", str(tmp_path / "hb.json"))
    monkeypatch.setattr("ops.alerter.alerter.TELEGRAM_TOKEN", "TOK")
    monkeypatch.setattr("ops.alerter.alerter.TELEGRAM_CHAT_ID", "CHAT")
    from ops.alerter.alerter import Alerter

    with mock.patch("ops.alerter.alerter.send_message", return_value=True) as send:
        a = Alerter()
        a._dispatch_log(_rec(TOUCH))
        a._dispatch_log(_rec(TOUCH.replace("ETH/USDT", "BTC/USDT")))
        a._dispatch_log(_rec(TOUCH))
        assert send.call_count == 2


def test_lux_alerts_bypass_llm_formatting(tmp_path: Path, monkeypatch, on):
    """Zone levels must reach the operator verbatim: an LLM rewrite could alter
    prices or add an 'action' that reads like a trade call."""
    monkeypatch.setattr("ops.alerter.alerter.DEDUP_DB", str(tmp_path / "dedup.sqlite"))
    monkeypatch.setattr("ops.alerter.alerter.HEARTBEAT_FILE", str(tmp_path / "hb.json"))
    monkeypatch.setattr("ops.alerter.alerter.TELEGRAM_TOKEN", "TOK")
    monkeypatch.setattr("ops.alerter.alerter.TELEGRAM_CHAT_ID", "CHAT")
    from ops.alerter.alerter import Alerter

    with mock.patch("ops.alerter.alerter.send_message", return_value=True) as send, \
         mock.patch("ops.alerter.alerter.format_alert_with_ai") as fmt:
        a = Alerter()
        a._dispatch_log(_rec(TOUCH))
        a._dispatch_log(_rec(REJECT))
    fmt.assert_not_called()
    assert send.call_count == 2
    assert "2309.09-2319.13" in send.call_args_list[0].args[2]


@pytest.mark.parametrize("level", ["INFO", "WARNING"])
def test_reject_fires_for_info_and_warning(on, level):
    msg = "[v2 reject] ETH/USDT: sizing failed (insufficient margin)"
    assert V2RejectAlertRule().match_log(_rec(msg, level=level)) is not None


def test_alert_text_is_html_escaped(on):
    """Telegram parse_mode=HTML refuses a raw '<=' — the alert would be lost."""
    out = V2RejectAlertRule().match_log(_rec("[v2 reject] ETH/USDT: size <= 0 (0.0)"))
    assert "&lt;=" in out and "<=" not in out


# ── K1 (ADR-0012): new entries paused → zone alerts must not claim the bot is
# waiting to enter. The alerter shares the bot's env_file (.env.production), so
# EFLOUD_PAUSE_NEW_ENTRIES is the same switch the bot reads (position_guard).
PAUSE = "EFLOUD_PAUSE_NEW_ENTRIES"


@pytest.mark.parametrize("msg", [NEAR, TOUCH, CONFIRMED])
def test_zone_alerts_say_paused_when_entries_paused(on, monkeypatch, msg):
    monkeypatch.setenv(PAUSE, "true")
    out = LuxZoneAlertRule().match_log(_rec(msg))
    assert out is not None and "ETH/USDT LONG" in out
    assert "DURDURULDU" in out and "işlem açmaz" in out
    assert "teyit mumu bekliyor" not in out
    assert "emir kontrollerine gidiyor" not in out


@pytest.mark.parametrize("val", ["false", "0", "", "maybe"])
def test_zone_alerts_unchanged_when_not_paused(on, monkeypatch, val):
    monkeypatch.setenv(PAUSE, val)
    out = LuxZoneAlertRule().match_log(_rec(TOUCH))
    assert "teyit mumu bekliyor" in out and "DURDURULDU" not in out


def test_pause_truthy_set_matches_position_guard():
    from engine.safety import position_guard
    from ops.alerter import rules
    assert rules.PAUSE_ENV == position_guard._ENV_VAR_NAME
    assert set(rules.PAUSE_TRUE) == set(position_guard._ENV_TRUE)
