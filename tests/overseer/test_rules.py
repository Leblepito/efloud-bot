"""Overseer deterministic rules — pure functions over a state dict.

Each rule returns Optional[Alert]. Tests assert:
  - positive: rule fires on expected pattern, severity + dedup_key sane.
  - negative: rule stays silent below threshold or on missing data.

State dict shape (see ops/overseer/rules.py module docstring):
  now_ts:int, log_lines:list[dict], healthz:dict,
  journal_recent:list[dict], audit_recent:list[dict]|None
"""
from __future__ import annotations

from typing import Any


# ---------- shared helpers ----------------------------------------------------

NOW = 1_700_000_000  # deterministic UTC epoch — keeps assertions reproducible


def _state(**overrides: Any) -> dict[str, Any]:
    """Build a baseline overseer state dict; tests overlay only what they need."""
    base: dict[str, Any] = {
        "now_ts": NOW,
        "log_lines": [],
        "healthz": {"status_code": 200, "last_ok_ts": NOW, "consecutive_failures": 0},
        "journal_recent": [],
        "audit_recent": [],
        "overseer_heartbeat_path": None,
    }
    base.update(overrides)
    return base


# ─────────────────────────────────────────────────────────────────────
# rule_bot_unhealthy
# ─────────────────────────────────────────────────────────────────────


def test_rule_bot_unhealthy_fires_on_3_consecutive_failures():
    from ops.overseer.rules import rule_bot_unhealthy
    s = _state(healthz={"status_code": 503, "last_ok_ts": NOW - 600, "consecutive_failures": 3})
    alert = rule_bot_unhealthy(s)
    assert alert is not None
    assert alert.severity == "CRITICAL"
    assert "3" in alert.dedup_key
    assert "bot_unhealthy" in alert.dedup_key
    assert "healthcheck" in alert.text.lower() or "healthz" in alert.text.lower()


def test_rule_bot_unhealthy_silent_below_threshold():
    from ops.overseer.rules import rule_bot_unhealthy
    s = _state(healthz={"status_code": 503, "last_ok_ts": NOW - 60, "consecutive_failures": 2})
    assert rule_bot_unhealthy(s) is None


# ─────────────────────────────────────────────────────────────────────
# rule_cycle_gap
# ─────────────────────────────────────────────────────────────────────


def test_rule_cycle_gap_fires_when_last_cycle_older_than_5min():
    from ops.overseer.rules import rule_cycle_gap
    last_cycle_ts = NOW - 6 * 60  # 6 min ago
    s = _state(log_lines=[{"event": "cycle_start", "ts": last_cycle_ts}])
    alert = rule_cycle_gap(s)
    assert alert is not None
    assert alert.severity == "WARN"
    assert str(last_cycle_ts) in alert.dedup_key
    assert "cycle_gap" in alert.dedup_key


def test_rule_cycle_gap_silent_within_5min():
    from ops.overseer.rules import rule_cycle_gap
    s = _state(log_lines=[{"event": "cycle_start", "ts": NOW - 30}])
    assert rule_cycle_gap(s) is None


def test_rule_cycle_gap_silent_when_no_cycle_events():
    """No cycle_start at all → nothing to compare; rule stays silent
    (fresh process, gap rule shouldn't false-positive on cold boot)."""
    from ops.overseer.rules import rule_cycle_gap
    assert rule_cycle_gap(_state()) is None


# ─────────────────────────────────────────────────────────────────────
# rule_consecutive_losses
# ─────────────────────────────────────────────────────────────────────


def test_rule_consecutive_losses_fires_on_5_straight_losses():
    from ops.overseer.rules import rule_consecutive_losses
    journal = [
        {"trade_id": f"T{i}", "realized_pnl": -10.0} for i in range(5)
    ]
    s = _state(journal_recent=journal)
    alert = rule_consecutive_losses(s)
    assert alert is not None
    assert alert.severity == "WARN"
    # dedup_key should pin to the most-recent trade id so only one alert per streak
    assert "T4" in alert.dedup_key
    assert "consec_loss" in alert.dedup_key


def test_rule_consecutive_losses_silent_when_one_win_breaks_streak():
    from ops.overseer.rules import rule_consecutive_losses
    journal = [
        {"trade_id": "T0", "realized_pnl": -10.0},
        {"trade_id": "T1", "realized_pnl": -10.0},
        {"trade_id": "T2", "realized_pnl": -10.0},
        {"trade_id": "T3", "realized_pnl": -10.0},
        {"trade_id": "T4", "realized_pnl": +5.0},
    ]
    s = _state(journal_recent=journal)
    assert rule_consecutive_losses(s) is None


def test_rule_consecutive_losses_silent_when_fewer_than_5_trades():
    """Need at least N=5 closed trades; partial history must not false-positive."""
    from ops.overseer.rules import rule_consecutive_losses
    journal = [{"trade_id": f"T{i}", "realized_pnl": -10.0} for i in range(3)]
    s = _state(journal_recent=journal)
    assert rule_consecutive_losses(s) is None


# ─────────────────────────────────────────────────────────────────────
# rule_audit_score_dropping
# ─────────────────────────────────────────────────────────────────────


def test_rule_audit_score_dropping_fires_on_low_median():
    from ops.overseer.rules import rule_audit_score_dropping
    audits = [{"overall_score": 4.5} for _ in range(10)]
    s = _state(audit_recent=audits)
    alert = rule_audit_score_dropping(s)
    assert alert is not None
    assert alert.severity == "WARN"
    assert "audit_drop" in alert.dedup_key
    # daily granularity dedup_key (yyyy-mm-dd token)
    assert "date=" in alert.dedup_key


def test_rule_audit_score_dropping_silent_when_audit_recent_is_none():
    """Audit infra disabled → graceful skip, no None-deref."""
    from ops.overseer.rules import rule_audit_score_dropping
    s = _state(audit_recent=None)
    assert rule_audit_score_dropping(s) is None


def test_rule_audit_score_dropping_silent_on_healthy_median():
    from ops.overseer.rules import rule_audit_score_dropping
    audits = [{"overall_score": 7.0} for _ in range(10)]
    s = _state(audit_recent=audits)
    assert rule_audit_score_dropping(s) is None


def test_rule_audit_score_dropping_silent_with_fewer_than_10_rows():
    """Need 10 rows minimum to compute meaningful median — small samples ignored."""
    from ops.overseer.rules import rule_audit_score_dropping
    audits = [{"overall_score": 3.0} for _ in range(4)]
    s = _state(audit_recent=audits)
    assert rule_audit_score_dropping(s) is None


# ─────────────────────────────────────────────────────────────────────
# rule_regime_flipflop
# ─────────────────────────────────────────────────────────────────────


def test_rule_regime_flipflop_fires_on_4_changes_in_10_min():
    from ops.overseer.rules import rule_regime_flipflop
    # 4 transitions inside a 10-min window for BTCUSDT
    base = NOW - 8 * 60
    log = [
        {"event": "regime_change", "symbol": "BTCUSDT", "ts": base + 0,   "regime": "TRENDING"},
        {"event": "regime_change", "symbol": "BTCUSDT", "ts": base + 60,  "regime": "RANGING"},
        {"event": "regime_change", "symbol": "BTCUSDT", "ts": base + 180, "regime": "VOLATILE"},
        {"event": "regime_change", "symbol": "BTCUSDT", "ts": base + 300, "regime": "TRENDING"},
        {"event": "regime_change", "symbol": "BTCUSDT", "ts": base + 420, "regime": "RANGING"},
    ]
    s = _state(log_lines=log)
    alert = rule_regime_flipflop(s)
    assert alert is not None
    assert alert.severity == "WARN"
    assert "regime_flipflop" in alert.dedup_key
    assert "BTCUSDT" in alert.dedup_key


def test_rule_regime_flipflop_silent_on_2_changes():
    from ops.overseer.rules import rule_regime_flipflop
    log = [
        {"event": "regime_change", "symbol": "BTCUSDT", "ts": NOW - 300, "regime": "TRENDING"},
        {"event": "regime_change", "symbol": "BTCUSDT", "ts": NOW - 120, "regime": "RANGING"},
    ]
    s = _state(log_lines=log)
    assert rule_regime_flipflop(s) is None


def test_rule_regime_flipflop_ignores_events_outside_10min_window():
    """Old regime changes (>10 min) must not count toward the flipflop budget."""
    from ops.overseer.rules import rule_regime_flipflop
    log = [
        {"event": "regime_change", "symbol": "BTCUSDT", "ts": NOW - 3600, "regime": "TRENDING"},
        {"event": "regime_change", "symbol": "BTCUSDT", "ts": NOW - 3500, "regime": "RANGING"},
        {"event": "regime_change", "symbol": "BTCUSDT", "ts": NOW - 3400, "regime": "VOLATILE"},
        {"event": "regime_change", "symbol": "BTCUSDT", "ts": NOW - 60,   "regime": "TRENDING"},
    ]
    s = _state(log_lines=log)
    assert rule_regime_flipflop(s) is None


# ─────────────────────────────────────────────────────────────────────
# rule_reverse_block_streak
# ─────────────────────────────────────────────────────────────────────


def test_rule_reverse_block_streak_fires_on_3_blocks_in_30min():
    from ops.overseer.rules import rule_reverse_block_streak
    log = [
        {"event": "REVERSE_BLOCKED_NOT_PROFITABLE", "ts": NOW - 1500},
        {"event": "REVERSE_BLOCKED_NOT_PROFITABLE", "ts": NOW - 900},
        {"event": "REVERSE_BLOCKED_NOT_PROFITABLE", "ts": NOW - 60},
    ]
    s = _state(log_lines=log)
    alert = rule_reverse_block_streak(s)
    assert alert is not None
    assert alert.severity == "INFO"
    assert "reverse_block_streak" in alert.dedup_key


def test_rule_reverse_block_streak_silent_on_2_blocks():
    from ops.overseer.rules import rule_reverse_block_streak
    log = [
        {"event": "REVERSE_BLOCKED_NOT_PROFITABLE", "ts": NOW - 900},
        {"event": "REVERSE_BLOCKED_NOT_PROFITABLE", "ts": NOW - 60},
    ]
    s = _state(log_lines=log)
    assert rule_reverse_block_streak(s) is None


def test_rule_reverse_block_streak_ignores_blocks_outside_30min():
    """Events older than 30 min must not count — keeps signal scoped to recent activity."""
    from ops.overseer.rules import rule_reverse_block_streak
    log = [
        {"event": "REVERSE_BLOCKED_NOT_PROFITABLE", "ts": NOW - 7200},
        {"event": "REVERSE_BLOCKED_NOT_PROFITABLE", "ts": NOW - 5400},
        {"event": "REVERSE_BLOCKED_NOT_PROFITABLE", "ts": NOW - 60},
    ]
    s = _state(log_lines=log)
    assert rule_reverse_block_streak(s) is None


# ─────────────────────────────────────────────────────────────────────
# OVERSEER_RULES registry
# ─────────────────────────────────────────────────────────────────────


def test_overseer_rules_registry_includes_all_six_rules():
    """Registry must expose all rules so watch.py can iterate; guards against
    accidental drop when adding new rules."""
    from ops.overseer.rules import OVERSEER_RULES
    names = {r.name for r in OVERSEER_RULES}
    assert names == {
        "bot_unhealthy",
        "cycle_gap",
        "consecutive_losses",
        "audit_score_dropping",
        "regime_flipflop",
        "reverse_block_streak",
    }


def test_rules_are_pure_state_not_mutated():
    """Calling every rule on a state dict must not mutate it — caller relies on
    state being a stable snapshot across the rule loop."""
    from ops.overseer.rules import OVERSEER_RULES
    s = _state(
        log_lines=[{"event": "cycle_start", "ts": NOW - 10}],
        healthz={"status_code": 200, "last_ok_ts": NOW, "consecutive_failures": 0},
    )
    import copy
    snapshot = copy.deepcopy(s)
    for r in OVERSEER_RULES:
        r.check(s)
    assert s == snapshot
