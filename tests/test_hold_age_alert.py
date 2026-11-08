"""Long-hold reminder (operator 2026-11-08, after the 36 h force close was removed).

With safety.hold_alert_hours > 0 the bot logs one HOLD_AGE warning per bucket of
N hours a position stays open; the alerter forwards it to Telegram. Information
only: nothing closes or changes.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock

import yaml

from engine.safe_orchestrator import SafeOrchestrator
from engine.safety.position_guard import PositionGuard


def _hours_ago(h):
    return (datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(hours=h)).isoformat()


def _orch_with(hours_cfg):
    orch = SafeOrchestrator.__new__(SafeOrchestrator)
    orch.config = {"safety": {"hold_alert_hours": hours_cfg}}
    orch.pos_guard = PositionGuard(max_holding_hours=0)
    return orch


def _pos(age_h):
    return SimpleNamespace(id="abc123", symbol="SOL/USDT", direction="LONG", sl=88.55,
                           opened_at=_hours_ago(age_h), avg_entry_price=89.41)


def _hold_lines(caplog):
    return [r.getMessage() for r in caplog.records if "HOLD_AGE" in r.getMessage()]


def test_hold_age_alerts_once_per_bucket(caplog):
    orch, pos = _orch_with(24), _pos(23.0)
    with caplog.at_level(logging.WARNING, logger="efloud.safe_orch"):
        orch._maybe_alert_hold_age(pos)                 # 23 h: nothing yet
        pos.opened_at = _hours_ago(25.0)
        orch._maybe_alert_hold_age(pos)                 # 25 h: bucket 1
        orch._maybe_alert_hold_age(pos)                 # same bucket: silent
        pos.opened_at = _hours_ago(49.0)
        orch._maybe_alert_hold_age(pos)                 # 49 h: bucket 2
    lines = _hold_lines(caplog)
    assert len(lines) == 2
    assert "bucket=1" in lines[0] and "bucket=2" in lines[1]
    assert "SOL/USDT LONG" in lines[0] and "id=abc123" in lines[0] and "entry=89.4100" in lines[0]


def test_hold_age_off_when_not_configured(caplog):
    with caplog.at_level(logging.WARNING, logger="efloud.safe_orch"):
        for cfg in (0, None):
            orch, pos = _orch_with(cfg), _pos(100.0)
            orch._maybe_alert_hold_age(pos)
    assert _hold_lines(caplog) == []


def test_hold_age_never_closes_or_raises():
    orch, pos = _orch_with(24), _pos(500.0)
    orch.lifecycle = MagicMock()
    orch.order_manager = MagicMock()
    orch._maybe_alert_hold_age(pos)
    assert orch.lifecycle.method_calls == [] and orch.order_manager.method_calls == []
    broken = SimpleNamespace(opened_at=_hours_ago(30))       # missing fields
    orch._maybe_alert_hold_age(broken)                        # must not raise


def test_position_age_hours_helper():
    g = PositionGuard(max_holding_hours=0)
    assert abs(g.position_age_hours(SimpleNamespace(opened_at=_hours_ago(10))) - 10) < 0.01
    assert abs(g.position_age_hours(SimpleNamespace(opened_at=_hours_ago(10) + "Z")) - 10) < 0.01
    assert g.position_age_hours(SimpleNamespace(opened_at="")) is None
    assert g.position_age_hours(SimpleNamespace(opened_at="garbage")) is None


def test_live_config_has_24h_hold_alert():
    with open("configs/config.phase2_1k.yaml", encoding="utf-8") as f:
        assert yaml.safe_load(f)["safety"]["hold_alert_hours"] == 24
