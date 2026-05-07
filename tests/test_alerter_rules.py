"""Alert rules — verify each rule fires on its trigger and ignores others."""
from __future__ import annotations

from ops.alerter.rules import (
    RULES,
    BreakerDailyRule,
    BreakerWeeklyRule,
    BreakerConsecutiveRule,
    HealthCrashLoopRule,
    HealthUnhealthy15MinRule,
    UNHEALTHY_15MIN_THRESHOLD_SEC,
)


def test_breaker_daily_rule_matches_log_with_daily_loss_phrase():
    """Real breaker.py:155 emits via _trip() → 'BREAKER TRIPPED: Daily loss ... exceeds ...'"""
    rec = {
        "level": "WARNING",
        "logger": "efloud.breaker",
        "message": "🚨 BREAKER TRIPPED: Daily loss -5.12% exceeds -5.0% | Resume at 2026-05-08T00:00:00",
    }
    out = BreakerDailyRule().match_log(rec)
    assert out is not None
    assert "Daily" in out


def test_breaker_weekly_rule_matches_log_with_weekly_drawdown_phrase():
    """Real breaker.py:162 emits via _halt() → level ERROR with 'BREAKER HALTED: Weekly drawdown ...'"""
    rec = {
        "level": "ERROR",
        "logger": "efloud.breaker",
        "message": "⛔ BREAKER HALTED: Weekly drawdown 8.50% reached limit 8.0% | MANUAL RESET REQUIRED",
    }
    out = BreakerWeeklyRule().match_log(rec)
    assert out is not None
    assert "Weekly" in out


def test_breaker_consecutive_rule_matches_log_with_consecutive_phrase():
    """Real breaker.py:168 _trip() → 'BREAKER TRIPPED: 3 consecutive losses'"""
    rec = {
        "level": "WARNING",
        "logger": "efloud.breaker",
        "message": "🚨 BREAKER TRIPPED: 3 consecutive losses | Resume at 2026-05-07T22:00:00",
    }
    out = BreakerConsecutiveRule().match_log(rec)
    assert out is not None


def test_health_crash_loop_rule_fires_on_suspended_status():
    payload = {
        "status": "suspended",
        "failures": ["crash_loop_suspended"],
        "checks": {"crash_count": 3},
    }
    out = HealthCrashLoopRule().match_health(payload, history={})
    assert out is not None
    assert "CRASH LOOP" in out.upper()


def test_health_unhealthy_15min_rule_fires_only_after_threshold():
    """First 503 doesn't fire; only after threshold of sustained 503s does it fire."""
    rule = HealthUnhealthy15MinRule()
    payload = {"status": "unhealthy", "failures": ["loop_tick_stale(120000ms)"]}

    # First poll, history empty → record but don't fire
    history: dict = {}
    out = rule.match_health(payload, history)
    assert out is None
    assert "unhealthy_since_ts" in history

    # Rewind to simulate UNHEALTHY_15MIN_THRESHOLD_SEC + 60 elapsed
    history["unhealthy_since_ts"] -= UNHEALTHY_15MIN_THRESHOLD_SEC + 60
    out = rule.match_health(payload, history)
    assert out is not None
    assert "15" in out or "unhealthy" in out.lower()


def test_trade_opened_rule_matches_safe_orch_open_log():
    """Real safe_orchestrator.py:448 emits via log.info → '✅ [SYMBOL] Opened LONG @ ...'"""
    from ops.alerter.rules import TradeOpenedRule
    rec = {
        "level": "INFO",
        "logger": "efloud.safe_orch",
        "message": "✅ [BTC/USDT] Opened LONG @ 50000.0000 size=0.001000 SL=49000.0000 TP1=51000.0000 TP2=52000.0000 Conf=80",
    }
    out = TradeOpenedRule().match_log(rec)
    assert out is not None
    assert "Opened" in out
    assert "BTC/USDT" in out


def test_trade_opened_rule_has_zero_dedup_window():
    """Every open is unique — should always fire."""
    from ops.alerter.rules import TradeOpenedRule
    assert TradeOpenedRule().dedup_window_sec == 0


def test_rules_list_contains_6_in_scope_rules():
    """Sanity: the exported RULES list has all 6 events (5 from spec §6 + trade.opened)."""
    keys = [r.alert_key for r in RULES]
    expected = {
        "breaker.tripped.daily",
        "breaker.tripped.weekly",
        "breaker.tripped.consecutive",
        "health.crash_loop",
        "health.unhealthy_15min",
        "trade.opened",
    }
    assert set(keys) == expected, f"got {set(keys)}"
