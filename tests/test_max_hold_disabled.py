"""safety.max_holding_hours <= 0 disables the max-hold force close (operator 2026-11-08).

Before: the guard compared `hours > max_hold`, so 0 meant "close every position
immediately" in live, while the backtest engine already read 0 as "off". The
operator asked to remove the 36 h force close; 0 now means off in both, and a
positive value keeps closing exactly as before.
"""
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import pytest
import yaml

from engine.safety.position_guard import PositionGuard


@dataclass
class FakePos:
    opened_at: str


def _hours_ago(h: float) -> str:
    return (datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(hours=h)).isoformat()


@pytest.mark.parametrize("max_hold", [0, 0.0, -1, None])
def test_zero_or_negative_disables_force_close(max_hold):
    guard = PositionGuard(max_holding_hours=max_hold)
    for age in (0.01, 36.5, 500.0):
        result = guard.check_holding_time(FakePos(opened_at=_hours_ago(age)))
        assert result.allowed is True
        assert result.warnings == []          # no "aging" warning either


def test_positive_limit_still_force_closes():
    guard = PositionGuard(max_holding_hours=36)
    assert guard.check_holding_time(FakePos(opened_at=_hours_ago(35))).allowed is True
    assert guard.check_holding_time(FakePos(opened_at=_hours_ago(37))).allowed is False


def test_live_config_disables_max_hold():
    with open("configs/config.phase2_1k.yaml", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    assert cfg["safety"]["max_holding_hours"] == 0


def test_disabled_max_hold_is_logged_at_startup(caplog):
    with caplog.at_level("INFO", logger="efloud.posguard"):
        PositionGuard(max_holding_hours=0)
    assert any("DISABLED" in r.getMessage() for r in caplog.records)

