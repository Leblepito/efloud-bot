"""SL-coverage blind spots (risk-ops follow-up to PR #350 / Ö1).

When Binance's algo-order read fails, neither post-placement verify nor
reconcile can confirm SL/TP (both fail closed). That was silent: only WARNING
log lines. These alerter rules surface it without touching the bot:
- VerifyNoReadRule: a new position's protection could not be confirmed at all.
- AlgoFetchStreakRule: reconcile's algo read failed >= 3 times within 10 min
  (a single transient failure — seen once a month in prod — does not alert).
Both sit behind EFLOUD_ALERTER_SL_ALERTS like the other SL rules.
"""
from __future__ import annotations

import pytest

from ops.alerter.rules import RULES, AlgoFetchStreakRule, VerifyNoReadRule

FLAG = "EFLOUD_ALERTER_SL_ALERTS"
RECON = ("Reconcile: algo orders fetch failed: binance GET https://fapi.binance.com/fapi/v1/"
         "openAlgoOrders 503 — TP1-hit detection may misfire")
NO_READ = ("verify.no_read_tolerated: BTC/USDT LONG — could not confirm SL/TP "
           "(all reads failed); leaving to reconcile")


def _rec(msg, ts="2026-11-14T15:00:00+00:00", logger="efloud.exchange", level="WARNING"):
    return {"ts": ts, "level": level, "logger": logger, "message": msg}


@pytest.fixture
def on(monkeypatch):
    monkeypatch.setenv(FLAG, "1")


def test_rules_registered():
    kinds = {type(r) for r in RULES}
    assert VerifyNoReadRule in kinds and AlgoFetchStreakRule in kinds


def test_default_off(monkeypatch):
    monkeypatch.delenv(FLAG, raising=False)
    assert VerifyNoReadRule().match_log(_rec(NO_READ)) is None
    r = AlgoFetchStreakRule()
    assert all(r.match_log(_rec(RECON, ts=f"2026-11-14T15:0{i}:00+00:00")) is None for i in range(5))


def test_verify_no_read_alerts_with_symbol(on):
    out = VerifyNoReadRule().match_log(_rec(NO_READ))
    assert out is not None and "BTC/USDT LONG" in out and "doğrulanamadı" in out
    assert VerifyNoReadRule().dedup_key(_rec(NO_READ)).endswith("BTC/USDT.LONG")


def test_verify_rule_ignores_other_lines(on):
    assert VerifyNoReadRule().match_log(_rec(RECON)) is None


def test_single_reconcile_failure_does_not_alert(on):
    assert AlgoFetchStreakRule().match_log(_rec(RECON)) is None


def test_three_failures_within_10_min_alert_once_streak(on):
    r = AlgoFetchStreakRule()
    assert r.match_log(_rec(RECON, ts="2026-11-14T15:00:00+00:00")) is None
    assert r.match_log(_rec(RECON, ts="2026-11-14T15:04:00+00:00")) is None
    out = r.match_log(_rec(RECON, ts="2026-11-14T15:09:00+00:00"))
    assert out is not None and "SL" in out and "3" in out


def test_failures_spread_beyond_window_do_not_alert(on):
    r = AlgoFetchStreakRule()
    for ts in ("2026-11-14T15:00:00+00:00", "2026-11-14T15:11:00+00:00",
               "2026-11-14T15:22:00+00:00", "2026-11-14T15:33:00+00:00"):
        assert r.match_log(_rec(RECON, ts=ts)) is None


def test_streak_rule_ignores_unrelated_and_bad_ts(on):
    r = AlgoFetchStreakRule()
    assert r.match_log(_rec("Reconcile: positions ok")) is None
    assert r.match_log(_rec(RECON, ts="not-a-time")) is None
