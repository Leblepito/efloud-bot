# `PositionGuard.check_holding_time` TZ Tolerance Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make `PositionGuard.check_holding_time` accept both TZ-naive and TZ-aware ISO timestamps in `position.opened_at` so the bot doesn't crash with `TypeError: can't subtract offset-naive and offset-aware datetimes` when restored positions and live-bot positions mix formats.

**Architecture:** Normalize both sides of the subtraction to TZ-naive UTC before comparing. The function already handles the trailing `Z` (Zulu) marker; extend it to also strip `+00:00` and any `tzinfo` on a successfully-parsed `datetime`. Pure-function change, no I/O, ~3 lines of meaningful diff.

**Tech Stack:** Python 3.12, `datetime`, pytest.

---

## Background — why this is needed

Two code paths produce `position.opened_at`:
- **Live bot path:** `engine/lifecycle.py:189,217,238,269` use `datetime.utcnow().isoformat()` → TZ-naive (e.g. `"2026-05-08T10:14:12.345678"`).
- **Restored / seed path:** any tool that uses `datetime.now(timezone.utc).isoformat()` produces TZ-aware (e.g. `"2026-05-08T10:14:12.345678+00:00"`). Memory's incident report calls out exactly this case.

`engine/safety/position_guard.py:208` does:

```python
opened = datetime.fromisoformat(position.opened_at.replace("Z", ""))
...
age = datetime.utcnow() - opened
```

`replace("Z", "")` strips the trailing Z but leaves `+00:00` intact → `fromisoformat` returns a TZ-aware datetime → `datetime.utcnow()` is TZ-naive → subtraction raises `TypeError`. The whole holding-time check then bypasses the force-close protection (the surrounding orchestrator catches the exception and logs a warning, but the position never gets closed for staleness).

This plan does not unify the bot's clock conventions (a much bigger refactor — see `engine/breaker.py`, `engine/safety/state.py`, `engine/journal.py`, etc.). Scope is narrowly to make `check_holding_time` defensive against either convention.

---

## File Structure

| File | Responsibility | Change kind |
|---|---|---|
| [engine/safety/position_guard.py](../../engine/safety/position_guard.py) | `check_holding_time()` — normalize TZ before subtracting | Modify (~3 lines) |
| [backend/tests/test_position_guard_tz_tolerance.py](../../backend/tests/test_position_guard_tz_tolerance.py) | Unit tests covering naive, Z-suffix, +00:00-suffix, mixed-fractional, garbage | Create |

---

## Chunk 1: TZ-tolerant subtraction + tests

### Task 1: Add TZ tolerance to `check_holding_time`

**Files:**
- Modify: [engine/safety/position_guard.py:202-227](../../engine/safety/position_guard.py#L202-L227)
- Create: [backend/tests/test_position_guard_tz_tolerance.py](../../backend/tests/test_position_guard_tz_tolerance.py)

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/test_position_guard_tz_tolerance.py`:

```python
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
    # Tight max_holding_hours so we can test threshold crossing without huge dt
    return PositionGuard(max_holding_hours=1)


def _hours_ago(h: float, tz_aware: bool, suffix: str = "") -> str:
    if tz_aware:
        return (datetime.now(timezone.utc) - timedelta(hours=h)).isoformat()
    base = (datetime.utcnow() - timedelta(hours=h)).isoformat()
    return base + suffix  # support "Z" or empty


def test_naive_isoformat_under_threshold_allowed(guard):
    """Bot's own format (TZ-naive) — 30 min old → allowed."""
    pos = FakePos(opened_at=_hours_ago(0.5, tz_aware=False))
    result = guard.check_holding_time(pos)
    assert result.allowed is True


def test_naive_isoformat_over_threshold_blocked(guard):
    """Bot's own format (TZ-naive) — 2h old, max 1h → force close."""
    pos = FakePos(opened_at=_hours_ago(2, tz_aware=False))
    result = guard.check_holding_time(pos)
    assert result.allowed is False
    assert "exceeds max" in (result.reason or "")


def test_tz_aware_plus_offset_under_threshold_allowed(guard):
    """Restored/seeded format (`+00:00`) — must NOT raise TypeError."""
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
    """`Z` suffix (rare, but possible from external tools)."""
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
    """Above 80% of max but under max → allowed but with warning."""
    pos = FakePos(opened_at=_hours_ago(0.85, tz_aware=True))  # 85% of 1h
    result = guard.check_holding_time(pos)
    assert result.allowed is True
    assert any("aging" in w.lower() for w in (result.warnings or []))
```

- [ ] **Step 2: Run tests — confirm TZ-aware tests fail with TypeError**

```
pytest backend/tests/test_position_guard_tz_tolerance.py -v
```

Expected: `test_tz_aware_plus_offset_under_threshold_allowed` and `test_tz_aware_plus_offset_over_threshold_blocked` raise `TypeError: can't subtract offset-naive and offset-aware datetimes` (or fail by returning `allowed=True` from the broad `except Exception` swallow at line 209-210). Either way, FAIL.

The naive / Z / empty / garbage tests should already PASS without the fix — we keep them to lock in current behavior.

- [ ] **Step 3: Apply the TZ normalization**

Edit [engine/safety/position_guard.py:202-227](../../engine/safety/position_guard.py#L202-L227). Replace the body of `check_holding_time` with:

```python
    def check_holding_time(self, position) -> PositionCheckResult:
        """Pozisyon çok uzun süredir açık mı?

        Tolerates both TZ-naive ('2026-05-08T10:14:12') and TZ-aware
        ('2026-05-08T10:14:12+00:00' / '...Z') opened_at formats. Mixing
        the two used to raise TypeError on subtraction, silently bypassing
        the force-close protection (2026-05-08 incident).
        """
        if not position.opened_at:
            return PositionCheckResult(True)

        raw = position.opened_at
        # Strip trailing Z so fromisoformat accepts it (Z support pre-3.11).
        if raw.endswith("Z"):
            raw = raw[:-1]

        try:
            opened = datetime.fromisoformat(raw)
        except Exception:
            return PositionCheckResult(True)

        # Drop tzinfo so the subtraction is naive-vs-naive. We're comparing
        # against datetime.utcnow() which is naive UTC, so a TZ-aware UTC
        # value can be safely de-zoned without arithmetic distortion.
        if opened.tzinfo is not None:
            opened = opened.replace(tzinfo=None)

        age = datetime.utcnow() - opened
        hours = age.total_seconds() / 3600

        if hours > self.max_hold:
            return PositionCheckResult(
                False,
                f"Position age {hours:.1f}h exceeds max {self.max_hold}h — force close recommended"
            )

        if hours > self.max_hold * 0.8:
            return PositionCheckResult(
                True,
                warnings=[f"Position aging: {hours:.1f}h / {self.max_hold}h"]
            )

        return PositionCheckResult(True)
```

- [ ] **Step 4: Run tests — all 8 pass**

```
pytest backend/tests/test_position_guard_tz_tolerance.py -v
```

Expected: 8 PASS.

- [ ] **Step 5: Run the full guard test suite**

```
pytest backend/tests/ -k "guard or position_guard or holding" -v
```

Expected: existing tests still pass.

- [ ] **Step 6: Commit**

```
git add engine/safety/position_guard.py backend/tests/test_position_guard_tz_tolerance.py
git commit -m "fix(safety): make check_holding_time TZ-tolerant

Live-bot positions use datetime.utcnow().isoformat() (TZ-naive); restored
or seeded positions can carry +00:00 / Z suffix (TZ-aware). The previous
implementation only stripped 'Z' and crashed with TypeError on +00:00,
silently bypassing the force-close protection.

Strip Z, parse, then drop tzinfo if present so the subtraction is always
naive UTC vs. naive UTC. 8 unit tests cover both formats including the
warning-zone (>80% of max) path."
```

---

## Chunk 2: PR + deploy

### Task 2: Open PR + deploy

**Files:** none

- [ ] **Step 1: Push branch**

Branch name: `fix/position-guard-tz-tolerance`

```
git push -u origin fix/position-guard-tz-tolerance
```

- [ ] **Step 2: Open PR**

```
gh pr create --title "fix(safety): TZ-tolerant check_holding_time" --body "$(cat <<'EOF'
## Summary
- `PositionGuard.check_holding_time` only stripped trailing `Z` before `datetime.fromisoformat()`. With `+00:00`-style ISO timestamps (TZ-aware), the resulting datetime mixed with `datetime.utcnow()` (TZ-naive) raised TypeError, getting swallowed and silently bypassing the force-close protection.
- Fix: parse, then drop tzinfo if present. Subtraction is always naive-vs-naive UTC.

## Test plan
- [x] 8 unit tests covering naive/aware/Z/empty/garbage/warning-zone paths.
- [x] No existing guard tests regressed.
EOF
)"
```

- [ ] **Step 3: Merge + deploy**

```
gh pr merge --squash --delete-branch
ssh efloud@178.104.122.91 'cd /opt/efloud-bot && git pull && bash deploy/deploy.sh'
```

- [ ] **Step 4: No special post-deploy verification needed**

This bug only surfaces when a position lives long enough to age out (max_holding_hours=48 in production). The unit tests are sufficient; no need to wait 48h to confirm in prod.
