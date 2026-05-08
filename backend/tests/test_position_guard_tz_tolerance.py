"""PositionGuard.check_holding_time must handle both TZ-naive and TZ-aware
opened_at strings. Live bot writes naive (datetime.utcnow().isoformat());
restored / seeded positions can carry +00:00 or Z suffix.

Without normalization, the subtraction raises TypeError and the holding-time
guard silently fails open — positions never force-close on age."""
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import pytest

from engine.safety.position_guard import PositionGuard


@dataclass
class FakePos:
    opened_at: str


@pytest.fixture
def guard():
    return PositionGuard(max_holding_hours=1)


def _hours_ago(h: float, tz_aware: bool, suffix: str = "") -> str:
    if tz_aware:
        return (datetime.now(timezone.utc) - timedelta(hours=h)).isoformat()
    base = (datetime.utcnow() - timedelta(hours=h)).isoformat()
    return base + suffix  # support "Z" or empty


def test_naive_isoformat_under_threshold_allowed(guard):
    pos = FakePos(opened_at=_hours_ago(0.5, tz_aware=False))
    result = guard.check_holding_time(pos)
    assert result.allowed is True


def test_naive_isoformat_over_threshold_blocked(guard):
    pos = FakePos(opened_at=_hours_ago(2, tz_aware=False))
    result = guard.check_holding_time(pos)
    assert result.allowed is False
    assert "exceeds max" in (result.reason or "")


def test_tz_aware_plus_offset_under_threshold_allowed(guard):
    """Restored/seeded format (+00:00) — must NOT raise TypeError."""
    pos = FakePos(opened_at=_hours_ago(0.5, tz_aware=True))
    result = guard.check_holding_time(pos)
    assert result.allowed is True


def test_tz_aware_plus_offset_over_threshold_blocked(guard):
    """Restored format, aged out — must force-close, not silently allow."""
    pos = FakePos(opened_at=_hours_ago(2, tz_aware=True))
    result = guard.check_holding_time(pos)
    assert result.allowed is False
    assert "exceeds max" in (result.reason or "")


def test_zulu_suffix_under_threshold(guard):
    pos = FakePos(opened_at=_hours_ago(0.5, tz_aware=False, suffix="Z"))
    result = guard.check_holding_time(pos)
    assert result.allowed is True


def test_garbage_opened_at_fails_open(guard):
    """Existing behavior: unparseable string → allow (don't block trading)."""
    pos = FakePos(opened_at="not a date")
    result = guard.check_holding_time(pos)
    assert result.allowed is True


def test_empty_opened_at_allowed(guard):
    """Existing behavior: empty string → allow."""
    pos = FakePos(opened_at="")
    result = guard.check_holding_time(pos)
    assert result.allowed is True


def test_warning_zone_returns_allowed_with_warning(guard):
    """Above 80% of max but under max → allowed with warning."""
    pos = FakePos(opened_at=_hours_ago(0.85, tz_aware=True))  # 85% of 1h
    result = guard.check_holding_time(pos)
    assert result.allowed is True
    assert any("aging" in w.lower() for w in (result.warnings or []))
