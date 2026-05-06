# Aşama 2 — Step 4: Telegram Alerter Sidecar Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship a Telegram alerter sidecar that watches the bot's structured logs + `/healthz` and fires CRITICAL/WARNING alerts on 5 specific events with persistent SQLite dedup. Operator sees real-time issues without watching dashboards.

**Architecture:** Standalone Python process running in its own container (reuses `efloud-bot:latest` image, different `command`). Two input streams: (a) tails `state/logs/efloud_bot.log` via mounted volume, parses JSON lines, runs string-pattern matchers; (b) polls `http://efloud-bot:8080/healthz` every 30s, runs status-based matchers. On match → checks SQLite dedup → if not duplicate, posts to Telegram via stdlib `urllib`. Heartbeat writes to a SEPARATE file (`state/alerter_heartbeat.json` — NOT the bot's `runtime.json`, see §"Spec deviations" for why) every 60s so daily-report (Step 5) can detect a dead alerter.

**Tech Stack:** Python 3.12 stdlib only (`urllib`, `sqlite3`, `json`, `pathlib`, `time`) — no new deps. Reuses `efloud-bot:latest` Docker image. pytest for tests.

**Spec parent:** `docs/superpowers/specs/2026-05-07-asama-2-self-maintenance-observability-design.md` (§4.3 alerter, §6 alert matrix)

**Estimated effort:** 4-5 days for one engineer.

---

## Scope: 5 events shipped here, 3 deferred

Spec §6 lists 8 alert events. This plan ships the 5 that don't require new bot-side logic:

| Event | Source | In Step 4? |
|-------|--------|------------|
| `breaker.tripped.daily` | bot log (existing `_halt(reason)`) | ✅ |
| `breaker.tripped.weekly` | bot log (existing `_halt(reason)`) | ✅ |
| `breaker.tripped.consecutive` | bot log (existing `_halt(reason)`) | ✅ |
| `health.crash_loop` | `/healthz` returns `status:"suspended"` (Step 3) | ✅ |
| `health.unhealthy_15min` | `/healthz` returns 503 for ≥15 min | ✅ |
| `position.stuck_over_6h` | Needs new bot-side detector | ❌ Step 4b |
| `exchange.error_burst` | Needs new exchange-error counter | ❌ Step 4b |
| `balance.unexpected_change` | Needs new balance monitor | ❌ Step 4b |

The 3 deferred events all need new bot-side code BEFORE alerter rules can match them. Follow-up plan (Step 4b) handles the bot-side instrumentation + adds the matching rules.

---

## Spec deviations to call out

The spec §4.3 says "Alerter writes `alerter_heartbeat_ts` to `state/runtime.json` every 60s." **This plan deviates: heartbeat goes to `state/alerter_heartbeat.json` instead.**

Reason: `state/runtime.json` is owned by the bot's `RuntimeState` class (Step 2), which keeps the file in-memory and writes only on state transitions. If the alerter wrote to the same file, both processes would race — alerter's heartbeat write loses to bot's next state-change write, or vice versa. Cleaner separation: alerter owns its heartbeat file exclusively; daily-report (Step 5) reads both files independently. Documented in the runbook + final report. Spec §4.3 wording is bent for correctness.

---

## Codebase reality check

### What's already shipped (master HEAD `6f47529` + Step 3 branch)
- `state/runtime.json` (Step 2) — bot's persistent state with `crash_count`, `fatal_exception_state`. Alerter does NOT modify this.
- `/healthz` endpoint (Step 2 + Step 3) — returns 200/503 with structured `failures` array. Alerter polls this directly inside Docker network at `http://efloud-bot:8080/healthz`.
- `efloud_logs:/app/logs` Docker volume (existing) — bot writes `efloud_bot.log` here via `RotatingFileHandler` (configured in `main.py:setup_logging`). Alerter mounts this volume read-only.
- JSON logging gate via `EFLOUD_LOGGING_FORMAT=json` (Step 1) — alerter assumes JSON; if env flag is unset (plain logs), alerter logs a startup WARNING and pattern matchers fall back to substring search on raw text (degrades but doesn't crash).

### Existing breaker log lines to match against (verified at master HEAD)

`engine/safety/breaker.py` has TWO log paths:
- `_trip(reason, resume_at)` at line 186 calls `log.warning(f"🚨 BREAKER TRIPPED: {reason} | Resume at {resume_at}")` (level WARNING)
- `_halt(reason)` at line 196 calls `log.error(f"⛔ BREAKER HALTED: {reason} | MANUAL RESET REQUIRED")` (level **ERROR** — not WARNING)

Actual reason strings produced (verified in breaker.py lines 146-168):

| Event | Trigger | Path | Reason string fragment |
|-------|---------|------|------------------------|
| Daily loss | line 155 | `_trip` (WARNING) | `"Daily loss {pct}% exceeds -{limit}%"` |
| Weekly DD | line 162 | `_halt` (ERROR) | `"Weekly drawdown {dd_pct}% reached limit {limit}%"` |
| Consecutive | line 168 | `_trip` (WARNING) | `"{n} consecutive losses"` |
| Emergency balance | line 146 | `_halt` (ERROR) | `"Emergency: balance ${current} < threshold ${thresh}"` (out of scope — not in §6 matrix) |

After JsonFormatter (Step 1), `record.getMessage()` returns the full f-string. So:
- Daily message contains: `"BREAKER TRIPPED"` + `"Daily loss"` + `"exceeds"`
- Weekly message contains: `"BREAKER HALTED"` + `"Weekly drawdown"`
- Consecutive message contains: `"BREAKER TRIPPED"` + `"consecutive losses"`

Rules in this plan use TWO-substring checks (event-prefix AND specific-phrase) for robustness against accidental matches on unrelated logger output.

### Container model
Reuse `efloud-bot:latest` image (no separate Dockerfile for alerter). Compose service runs `command: python -m ops.alerter.alerter`. The image already has `urllib` (stdlib) and `sqlite3` (stdlib) — no new deps.

---

## File structure (what gets created vs modified)

**Create:**
- `ops/__init__.py` (empty package marker)
- `ops/alerter/__init__.py` (empty package marker)
- `ops/alerter/dedup.py` (~90 lines) — `Dedup` class wrapping SQLite
- `ops/alerter/telegram_client.py` (~70 lines) — `send_message(token, chat_id, text)` using stdlib urllib
- `ops/alerter/rules.py` (~150 lines) — rule definitions + match functions for log lines and healthz responses
- `ops/alerter/alerter.py` (~180 lines) — main loop combining log-tail + healthz-poll + dedup + Telegram + heartbeat
- `tests/test_alerter_dedup.py` (~80 lines, 5 tests)
- `tests/test_alerter_telegram_client.py` (~60 lines, 2 tests)
- `tests/test_alerter_rules.py` (~140 lines, 6 tests)
- `tests/test_alerter_heartbeat.py` (~40 lines, 1 test)
- `tests/test_alerter_e2e.py` (~80 lines, 1 test)

**Modify:**
- `docker-compose.prod.yml` — add `alerter` service block

**Delete:** none.

---

## Pre-flight

### Task 0: Worktree + branch setup, baseline verification

**Files:** none modified, only environment setup.

- [ ] **Step 0.1: Create dedicated worktree from master**

```powershell
cd C:\Users\utkuc\Downloads\efloud-bot
git worktree add ../efloud-bot-asama2-step4 -b feature/asama-2-step-4-alerter master
cd ../efloud-bot-asama2-step4
```

Expected: new worktree on `feature/asama-2-step-4-alerter`, based on master HEAD. **NOTE: this branches from master, NOT from Step 3's branch.** Step 4 is independent of Step 3 deploy state.

- [ ] **Step 0.2: Verify base tests pass**

```powershell
python -m pytest tests/ -q --no-header 2>&1 | Select-Object -Last 5
```

Expected: 76 pass + 6 skip = 82 collected (Step 2 final state on master). Final test count after Step 4 must be **exactly** `76 + 16 = 92 pass + 6 skip = 98 collected` (per Task 8 dual E2E tests).

- [ ] **Step 0.3: Confirm `state/` and `ops/` paths are sensible**

```powershell
Test-Path state, ops
```

Expected: `True, False` (state/ exists from Step 2; ops/ is new in this plan).

New tests added by this plan (= 16):
- Task 2 (dedup): 5 tests
- Task 3 (telegram_client): 2 tests
- Task 4 (rules): 6 tests
- Task 6 (heartbeat): 1 test
- Task 8 (E2E): 2 tests (log-line dedup + healthz crash-loop)

Running totals at each task boundary:
- After Task 1: baseline (no tests)
- After Task 2: baseline + 5
- After Task 3: baseline + 7
- After Task 4: baseline + 13
- After Task 5: baseline + 13 (no new tests; integration via Task 8 E2E)
- After Task 6: baseline + 14
- After Task 7: baseline + 14 (Docker config; no tests)
- After Task 8: baseline + 16 ← FINAL (98 collected = 92 pass + 6 skip)

---

## Foundation: dedup + telegram client

### Task 1: ops package skeleton

**Files:**
- Create: `ops/__init__.py` (empty)
- Create: `ops/alerter/__init__.py` (empty)

Minimal package markers so `python -m ops.alerter.alerter` works later. Empty files; no logic, no tests.

- [ ] **Step 1.1: Create empty package markers**

```powershell
New-Item -ItemType Directory -Path ops/alerter -Force | Out-Null
"" | Out-File -Encoding utf8 -FilePath ops/__init__.py -NoNewline
"" | Out-File -Encoding utf8 -FilePath ops/alerter/__init__.py -NoNewline
```

- [ ] **Step 1.2: Commit**

```powershell
git add ops/__init__.py ops/alerter/__init__.py
git commit -m "scaffold(ops): empty ops/alerter/ package markers"
```

---

### Task 2: SQLite dedup module

**Files:**
- Create: `ops/alerter/dedup.py` (~90 lines)
- Test: `tests/test_alerter_dedup.py` (5 tests)

Persistent dedup state across alerter restarts. Schema per spec §4.3: `(alert_key TEXT PRIMARY KEY, last_fired_ts INTEGER, fire_count INTEGER)`.

- [ ] **Step 2.1: Write tests first**

Create `tests/test_alerter_dedup.py`:

```python
"""Dedup — SQLite-backed alert dedup with configurable per-key window."""
from __future__ import annotations

import sqlite3
import time
from pathlib import Path

import pytest

from ops.alerter.dedup import Dedup


@pytest.fixture
def dedup(tmp_path: Path) -> Dedup:
    return Dedup(db_path=str(tmp_path / "dedup.sqlite"))


def test_first_fire_is_allowed(dedup: Dedup):
    assert dedup.should_fire("breaker.tripped.daily", window_sec=1800) is True


def test_second_fire_within_window_is_blocked(dedup: Dedup):
    dedup.should_fire("breaker.tripped.daily", window_sec=1800)
    # Immediately again
    assert dedup.should_fire("breaker.tripped.daily", window_sec=1800) is False


def test_fire_after_window_is_allowed(dedup: Dedup):
    """Manually rewind last_fired_ts to simulate elapsed window."""
    dedup.should_fire("breaker.tripped.daily", window_sec=1800)
    # Rewind 31 minutes
    with sqlite3.connect(dedup.db_path) as conn:
        conn.execute(
            "UPDATE alerts SET last_fired_ts = ? WHERE alert_key = ?",
            (int(time.time()) - 31 * 60, "breaker.tripped.daily"),
        )
    assert dedup.should_fire("breaker.tripped.daily", window_sec=1800) is True


def test_fire_count_increments(dedup: Dedup):
    dedup.should_fire("breaker.tripped.daily", window_sec=1800)
    # Force fire again by rewinding window
    with sqlite3.connect(dedup.db_path) as conn:
        conn.execute(
            "UPDATE alerts SET last_fired_ts = ? WHERE alert_key = ?",
            (0, "breaker.tripped.daily"),
        )
    dedup.should_fire("breaker.tripped.daily", window_sec=1800)
    with sqlite3.connect(dedup.db_path) as conn:
        row = conn.execute(
            "SELECT fire_count FROM alerts WHERE alert_key = ?",
            ("breaker.tripped.daily",),
        ).fetchone()
    assert row[0] == 2


def test_corrupted_db_is_recreated(tmp_path: Path):
    """Spec §4.3: corrupt file → log WARNING + recreate. First hour after restart
    may produce 1-2 duplicate alerts; documented behavior."""
    db_path = tmp_path / "dedup.sqlite"
    db_path.write_bytes(b"this is not a valid sqlite database")
    # Construction should not raise
    d = Dedup(db_path=str(db_path))
    # Fresh DB — first fire is allowed
    assert d.should_fire("any.key", window_sec=1800) is True
```

- [ ] **Step 2.2: Run tests, expect FAIL**

```powershell
python -m pytest tests/test_alerter_dedup.py -v 2>&1
```

Expected: ImportError on `ops.alerter.dedup`. All 5 tests fail at collection.

- [ ] **Step 2.3: Implement Dedup class**

Create `ops/alerter/dedup.py`:

```python
"""SQLite-backed alert dedup. Persistent across alerter restarts.

Schema: (alert_key TEXT PRIMARY KEY, last_fired_ts INTEGER, fire_count INTEGER).
On corrupt-file detection, the file is moved aside and a fresh DB is created
(spec §4.3 "auto-recreate on corruption" — first hour after restart may produce
1-2 duplicates).
"""
from __future__ import annotations

import logging
import os
import sqlite3
import time
from pathlib import Path

log = logging.getLogger("efloud.alerter.dedup")

_SCHEMA = """
CREATE TABLE IF NOT EXISTS alerts (
    alert_key       TEXT PRIMARY KEY,
    last_fired_ts   INTEGER NOT NULL,
    fire_count      INTEGER NOT NULL DEFAULT 0
)
"""


class Dedup:
    """SQLite dedup keyed by alert_key with per-key time windows."""

    def __init__(self, db_path: str):
        self.db_path = db_path
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self._open_or_recreate()

    def _open_or_recreate(self) -> None:
        """Open the DB; if file exists but is corrupt, move it aside and create fresh."""
        if Path(self.db_path).exists():
            try:
                with sqlite3.connect(self.db_path) as conn:
                    # Cheap integrity probe
                    conn.execute("PRAGMA integrity_check").fetchone()
                    conn.execute(_SCHEMA)
                return
            except (sqlite3.DatabaseError, sqlite3.OperationalError) as e:
                log.warning(
                    f"alerter dedup DB at {self.db_path} corrupt ({e}); "
                    f"moving aside and recreating"
                )
                backup = f"{self.db_path}.corrupt.{int(time.time())}"
                try:
                    os.replace(self.db_path, backup)
                except OSError:
                    Path(self.db_path).unlink(missing_ok=True)
        # Fresh DB
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(_SCHEMA)

    def should_fire(self, alert_key: str, window_sec: int) -> bool:
        """Return True if this alert is allowed to fire (and record the fire);
        False if it's a duplicate within window_sec.

        Side effect on True: inserts/updates the alert row, increments fire_count.
        """
        now = int(time.time())
        with sqlite3.connect(self.db_path) as conn:
            row = conn.execute(
                "SELECT last_fired_ts, fire_count FROM alerts WHERE alert_key = ?",
                (alert_key,),
            ).fetchone()
            if row is not None:
                last_ts, fire_count = row
                if now - last_ts < window_sec:
                    return False
                # Window elapsed — allow and bump count
                conn.execute(
                    "UPDATE alerts SET last_fired_ts = ?, fire_count = ? "
                    "WHERE alert_key = ?",
                    (now, fire_count + 1, alert_key),
                )
                return True
            # First fire
            conn.execute(
                "INSERT INTO alerts (alert_key, last_fired_ts, fire_count) "
                "VALUES (?, ?, 1)",
                (alert_key, now),
            )
            return True
```

- [ ] **Step 2.4: Run tests, expect PASS**

```powershell
python -m pytest tests/test_alerter_dedup.py -v 2>&1 | Select-Object -Last 10
```

Expected: 5 tests pass.

- [ ] **Step 2.5: Run full suite for regression**

```powershell
python -m pytest tests/ -q 2>&1 | Select-Object -Last 5
```

Expected: 81 pass + 6 skip = 87 collected (76 baseline + 5).

- [ ] **Step 2.6: Commit**

```powershell
git add ops/alerter/dedup.py tests/test_alerter_dedup.py
git commit -m "feat(alerter): SQLite-backed Dedup with auto-recreate on corruption"
```

---

### Task 3: Telegram client (stdlib HTTP)

**Files:**
- Create: `ops/alerter/telegram_client.py` (~70 lines)
- Test: `tests/test_alerter_telegram_client.py` (2 tests using `unittest.mock`)

Minimal `send_message(token, chat_id, text, parse_mode="HTML")` that POSTs to `https://api.telegram.org/bot<TOKEN>/sendMessage`. Stdlib only (`urllib.request` + `urllib.parse`). Returns True on 2xx, logs WARNING + returns False on error.

- [ ] **Step 3.1: Write tests first**

Create `tests/test_alerter_telegram_client.py`:

```python
"""Telegram client — stdlib urllib HTTP wrapper."""
from __future__ import annotations

from unittest import mock

from ops.alerter.telegram_client import send_message


def test_send_message_success_returns_true():
    """Mock urllib.request.urlopen to return a 200 response."""
    fake_response = mock.MagicMock()
    fake_response.__enter__.return_value.status = 200
    fake_response.__enter__.return_value.read.return_value = b'{"ok":true}'
    with mock.patch("ops.alerter.telegram_client.urllib.request.urlopen",
                    return_value=fake_response) as urlopen:
        ok = send_message(token="TOK", chat_id="123", text="hello")
        assert ok is True
        # Verify the URL contains the bot token
        call_arg = urlopen.call_args[0][0]
        assert hasattr(call_arg, "full_url")
        assert "/botTOK/sendMessage" in call_arg.full_url


def test_send_message_http_error_returns_false():
    """Mock urlopen to raise URLError; send_message must return False (NOT raise)."""
    import urllib.error
    with mock.patch(
        "ops.alerter.telegram_client.urllib.request.urlopen",
        side_effect=urllib.error.URLError("network unreachable"),
    ):
        ok = send_message(token="TOK", chat_id="123", text="hello")
        assert ok is False
```

- [ ] **Step 3.2: Run tests, expect FAIL**

```powershell
python -m pytest tests/test_alerter_telegram_client.py -v 2>&1
```

Expected: ImportError on `ops.alerter.telegram_client`. 2 tests fail at collection.

- [ ] **Step 3.3: Implement telegram_client**

Create `ops/alerter/telegram_client.py`:

```python
"""Minimal Telegram bot API client. Stdlib urllib; no `requests` dep.

Single-purpose: POST sendMessage to chat_id. Returns True on 2xx, False on
network/API error. Errors are logged WARNING — caller decides whether to
retry, escalate, or drop.
"""
from __future__ import annotations

import json
import logging
import urllib.error
import urllib.parse
import urllib.request

log = logging.getLogger("efloud.alerter.telegram")

API_BASE = "https://api.telegram.org"
TIMEOUT_SEC = 10


def send_message(
    token: str,
    chat_id: str,
    text: str,
    parse_mode: str = "HTML",
) -> bool:
    """POST sendMessage to Telegram. Returns True on 2xx, False on any error.

    Telegram rate limit is ~30 msg/sec; alerter's caller is expected to enforce
    a 50/min hard cap (spec §4.3) — this function does not throttle.
    """
    if not token or not chat_id:
        log.warning("send_message skipped: missing token or chat_id")
        return False

    url = f"{API_BASE}/bot{token}/sendMessage"
    payload = urllib.parse.urlencode({
        "chat_id": chat_id,
        "text": text,
        "parse_mode": parse_mode,
    }).encode("utf-8")

    req = urllib.request.Request(url, data=payload, method="POST")
    req.add_header("Content-Type", "application/x-www-form-urlencoded")

    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT_SEC) as resp:
            if 200 <= resp.status < 300:
                return True
            body = resp.read(500).decode("utf-8", errors="replace")
            log.warning(f"telegram sendMessage HTTP {resp.status}: {body}")
            return False
    except urllib.error.HTTPError as e:
        body = e.read(500).decode("utf-8", errors="replace") if e.fp else ""
        log.warning(f"telegram sendMessage HTTPError {e.code}: {body}")
        return False
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        log.warning(f"telegram sendMessage transport error: {e}")
        return False
```

- [ ] **Step 3.4: Run tests, expect PASS**

```powershell
python -m pytest tests/test_alerter_telegram_client.py -v 2>&1
```

Expected: 2 tests pass.

- [ ] **Step 3.5: Commit**

```powershell
git add ops/alerter/telegram_client.py tests/test_alerter_telegram_client.py
git commit -m "feat(alerter): stdlib-only Telegram sendMessage client"
```

---

## Rules + main loop

### Task 4: Alert rules + matchers

**Files:**
- Create: `ops/alerter/rules.py` (~150 lines)
- Test: `tests/test_alerter_rules.py` (6 tests)

Defines the 5 in-scope alert events as a list of `Rule` objects. Each rule has:
- `alert_key` (e.g., `"breaker.tripped.daily"`)
- `severity` (`"WARNING"` or `"CRITICAL"`)
- `dedup_window_sec`
- `match_log(rec: dict) -> Optional[str]` — given a parsed JSON log line, return the formatted alert text or None
- `match_health(payload: dict, history: dict) -> Optional[str]` — given a `/healthz` JSON payload + alerter's in-memory history, return formatted alert or None

Most rules implement only ONE of `match_log` or `match_health`. The alerter's main loop calls both methods; rules return None for the irrelevant input type.

- [ ] **Step 4.1: Write tests first**

Create `tests/test_alerter_rules.py`:

```python
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
        "logger": "efloud.safety.breaker",
        "message": "🚨 BREAKER TRIPPED: Daily loss -5.12% exceeds -5.0% | Resume at 2026-05-08T00:00:00",
    }
    out = BreakerDailyRule().match_log(rec)
    assert out is not None
    assert "Daily" in out


def test_breaker_weekly_rule_matches_log_with_weekly_drawdown_phrase():
    """Real breaker.py:162 emits via _halt() → level ERROR with 'BREAKER HALTED: Weekly drawdown ...'"""
    rec = {
        "level": "ERROR",
        "logger": "efloud.safety.breaker",
        "message": "⛔ BREAKER HALTED: Weekly drawdown 8.50% reached limit 8.0% | MANUAL RESET REQUIRED",
    }
    out = BreakerWeeklyRule().match_log(rec)
    assert out is not None
    assert "Weekly" in out


def test_breaker_consecutive_rule_matches_log_with_consecutive_phrase():
    """Real breaker.py:168 emits via _trip() → 'BREAKER TRIPPED: 3 consecutive losses'"""
    rec = {
        "level": "WARNING",
        "logger": "efloud.safety.breaker",
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


def test_rules_list_contains_5_in_scope_rules():
    """Sanity: the exported RULES list has all 5 in-scope events, no more."""
    keys = [r.alert_key for r in RULES]
    expected = {
        "breaker.tripped.daily",
        "breaker.tripped.weekly",
        "breaker.tripped.consecutive",
        "health.crash_loop",
        "health.unhealthy_15min",
    }
    assert set(keys) == expected, f"got {set(keys)}"
```

- [ ] **Step 4.2: Run tests, expect FAIL**

```powershell
python -m pytest tests/test_alerter_rules.py -v 2>&1
```

Expected: ImportError. 6 tests fail at collection.

- [ ] **Step 4.3: Implement rules.py**

Create `ops/alerter/rules.py`:

```python
"""Alert rule definitions — log-line matchers + healthz-payload matchers.

Each Rule defines: alert_key, severity, dedup_window_sec, and at least one of
match_log() / match_health(). The alerter's main loop iterates RULES and calls
both methods on every input — rules return None for input types they don't care
about.

In scope (Step 4):
    breaker.tripped.daily/weekly/consecutive  — log-driven
    health.crash_loop, health.unhealthy_15min  — healthz-driven

Out of scope (Step 4b follow-up):
    position.stuck_over_6h, exchange.error_burst, balance.unexpected_change
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Optional

# Healthz consecutive-failure threshold: 15 minutes
UNHEALTHY_15MIN_THRESHOLD_SEC = 15 * 60


@dataclass
class Rule:
    """Base rule. Subclasses override match_log and/or match_health."""
    alert_key: str = ""
    severity: str = "WARNING"  # "WARNING" or "CRITICAL"
    dedup_window_sec: int = 30 * 60

    def match_log(self, rec: dict) -> Optional[str]:
        """Given a parsed JSON log line dict, return formatted alert text or None."""
        return None

    def match_health(self, payload: dict, history: dict) -> Optional[str]:
        """Given a /healthz response dict and alerter's mutable history dict,
        return formatted alert text or None.

        history is the alerter's in-memory per-rule scratchpad — the rule
        may read/write keys it owns. NOT persisted across alerter restart;
        SQLite dedup is the only persistent state.
        """
        return None


# ─────────────────────────────────────────────────────────────────────
# Log-driven rules
# ─────────────────────────────────────────────────────────────────────


@dataclass
class BreakerDailyRule(Rule):
    """Matches breaker.py:155 _trip() — 'BREAKER TRIPPED: Daily loss ... exceeds ...'"""
    alert_key: str = "breaker.tripped.daily"
    severity: str = "CRITICAL"
    dedup_window_sec: int = 24 * 60 * 60  # 1 per day

    def match_log(self, rec: dict) -> Optional[str]:
        if rec.get("logger") != "efloud.safety.breaker":
            return None
        if rec.get("level") not in ("WARNING", "ERROR", "CRITICAL"):
            return None
        msg = rec.get("message", "")
        # Two-substring check: event prefix AND specific phrase (defends against
        # false positives from unrelated breaker logger output).
        if "BREAKER TRIPPED" in msg and "Daily loss" in msg:
            return f"🚨 <b>Breaker TRIPPED — daily loss limit</b>\n{msg}"
        return None


@dataclass
class BreakerWeeklyRule(Rule):
    """Matches breaker.py:162 _halt() — 'BREAKER HALTED: Weekly drawdown ... reached limit ...' (level ERROR)"""
    alert_key: str = "breaker.tripped.weekly"
    severity: str = "CRITICAL"
    dedup_window_sec: int = 7 * 24 * 60 * 60  # 1 per week

    def match_log(self, rec: dict) -> Optional[str]:
        if rec.get("logger") != "efloud.safety.breaker":
            return None
        if rec.get("level") not in ("WARNING", "ERROR", "CRITICAL"):
            return None
        msg = rec.get("message", "")
        if "BREAKER HALTED" in msg and "Weekly drawdown" in msg:
            return f"🚨 <b>Breaker HALTED — weekly drawdown</b>\n{msg}"
        return None


@dataclass
class BreakerConsecutiveRule(Rule):
    """Matches breaker.py:168 _trip() — 'BREAKER TRIPPED: N consecutive losses'"""
    alert_key: str = "breaker.tripped.consecutive"
    severity: str = "WARNING"
    dedup_window_sec: int = 30 * 60  # 30 min

    def match_log(self, rec: dict) -> Optional[str]:
        if rec.get("logger") != "efloud.safety.breaker":
            return None
        if rec.get("level") not in ("WARNING", "ERROR", "CRITICAL"):
            return None
        msg = rec.get("message", "")
        if "BREAKER TRIPPED" in msg and "consecutive losses" in msg:
            return f"⚠️ <b>Breaker TRIPPED — consecutive losses</b>\n{msg}"
        return None


# ─────────────────────────────────────────────────────────────────────
# Healthz-driven rules
# ─────────────────────────────────────────────────────────────────────


@dataclass
class HealthCrashLoopRule(Rule):
    alert_key: str = "health.crash_loop"
    severity: str = "CRITICAL"
    dedup_window_sec: int = 24 * 60 * 60  # once per occurrence

    def match_health(self, payload: dict, history: dict) -> Optional[str]:
        if payload.get("status") == "suspended" and \
           "crash_loop_suspended" in payload.get("failures", []):
            crash_count = payload.get("checks", {}).get("crash_count", "?")
            return (
                f"🚨 <b>CRASH LOOP detected — bot SUSPENDED</b>\n"
                f"crash_count = {crash_count}\n"
                f"See docs/runbooks/crash-loop-recovery.md"
            )
        return None


@dataclass
class HealthUnhealthy15MinRule(Rule):
    """Fires when /healthz has returned 503 (status:'unhealthy') continuously
    for at least UNHEALTHY_15MIN_THRESHOLD_SEC.

    Uses history dict to track the timestamp of the first 503 in the current
    streak. Resets when /healthz returns ok or suspended.
    """
    alert_key: str = "health.unhealthy_15min"
    severity: str = "CRITICAL"
    dedup_window_sec: int = 24 * 60 * 60

    def match_health(self, payload: dict, history: dict) -> Optional[str]:
        status = payload.get("status")
        if status != "unhealthy":
            # Streak broken — clear history
            history.pop("unhealthy_since_ts", None)
            return None

        now = int(time.time())
        if "unhealthy_since_ts" not in history:
            history["unhealthy_since_ts"] = now
            return None

        elapsed = now - history["unhealthy_since_ts"]
        if elapsed >= UNHEALTHY_15MIN_THRESHOLD_SEC:
            failures = payload.get("failures", [])
            return (
                f"🚨 <b>Health check failing &gt;15 min</b>\n"
                f"elapsed: {elapsed}s\n"
                f"failures: {failures}"
            )
        return None


# ─────────────────────────────────────────────────────────────────────
# Exported list — alerter main loop iterates this
# ─────────────────────────────────────────────────────────────────────

RULES: list[Rule] = [
    BreakerDailyRule(),
    BreakerWeeklyRule(),
    BreakerConsecutiveRule(),
    HealthCrashLoopRule(),
    HealthUnhealthy15MinRule(),
]
```

- [ ] **Step 4.4: Run tests, expect PASS**

```powershell
python -m pytest tests/test_alerter_rules.py -v 2>&1 | Select-Object -Last 10
```

Expected: 6 tests pass.

- [ ] **Step 4.5: Spot-check that rule substrings still match breaker.py at execution time**

The plan's substrings were reconciled against `engine/safety/breaker.py` at master HEAD `6f47529` during plan-writing (see "Existing breaker log lines to match against" reality check above). However, if breaker.py has changed since the plan was written (e.g., another developer touched the log strings), the rules will silently fail to match. Quick verification:

```powershell
Select-String -Path engine\safety\breaker.py -Pattern "_trip\(|_halt\(|BREAKER TRIPPED|BREAKER HALTED" | Select-Object -First 15
```

Confirm the lines still emit the substrings the rules look for: `"BREAKER TRIPPED"` + `"Daily loss"`, `"BREAKER HALTED"` + `"Weekly drawdown"`, `"BREAKER TRIPPED"` + `"consecutive losses"`. If any divergence, surface as DONE_WITH_CONCERNS (do NOT silently change rules — flag for owner review).

- [ ] **Step 4.6: Run full suite for regression**

```powershell
python -m pytest tests/ -q 2>&1 | Select-Object -Last 5
```

Expected: 89 collected (76 baseline + 7 from Tasks 2-3 + 6 from Task 4 = 89).

- [ ] **Step 4.7: Commit**

```powershell
git add ops/alerter/rules.py tests/test_alerter_rules.py
git commit -m "feat(alerter): 5 alert rules (breaker daily/weekly/consecutive + health crash_loop/unhealthy_15min)"
```

---

### Task 5: Alerter main loop

**Files:**
- Create: `ops/alerter/alerter.py` (~180 lines)
- No new test file in this task (E2E in Task 8 covers integration; unit-testing the main loop's `while True` is fragile)

The main loop:
1. Reads config from env: `EFLOUD_TELEGRAM_TOKEN`, `EFLOUD_TELEGRAM_CHAT_ID`, `EFLOUD_LOG_FILE`, `EFLOUD_HEALTHZ_URL` (defaults: `/app/logs/efloud_bot.log`, `http://efloud-bot:8080/healthz`), `EFLOUD_ALERTER_DEDUP_DB` (default: `/app/state/alerter_dedup.sqlite`), `EFLOUD_ALERTER_HEARTBEAT_FILE` (default: `/app/state/alerter_heartbeat.json`)
2. Tail loop: every 1s, read new lines from log file (track byte offset); for each JSON-parseable line, run all rules' `match_log()`
3. Healthz poll: every 30s, GET healthz URL; for each rule run `match_health()`
4. Heartbeat: every 60s, write `{"alerter_heartbeat_ts": <epoch_sec>}` to heartbeat file
5. On rule match: check dedup → if allowed, send Telegram + record dedup
6. Rate limit: hard cap 50 messages/min (drops and logs WARNING when exceeded)

- [ ] **Step 5.1: Implement alerter.py**

Create `ops/alerter/alerter.py`:

```python
"""Telegram alerter — main loop.

Inputs:
- Bot's JSON log file (tailed, per spec §4.3)
- Bot's /healthz endpoint (polled every 30s)

Outputs:
- Telegram messages on rule matches (deduplicated via SQLite)
- Heartbeat written to state/alerter_heartbeat.json every 60s

Run as: python -m ops.alerter.alerter
"""
from __future__ import annotations

import json
import logging
import os
import time
import urllib.error
import urllib.request
from collections import deque
from pathlib import Path

from ops.alerter.dedup import Dedup
from ops.alerter.rules import RULES, Rule
from ops.alerter.telegram_client import send_message

# Configure logging — alerter has its own simple text format, distinct from bot's JSON
logging.basicConfig(
    level=os.environ.get("LOG_LEVEL", "INFO"),
    format="%(asctime)s | %(name)-22s | %(levelname)-5s | %(message)s",
)
log = logging.getLogger("efloud.alerter")

# Cadences
LOG_TAIL_INTERVAL_SEC = 1.0
HEALTHZ_POLL_INTERVAL_SEC = 30.0
HEARTBEAT_INTERVAL_SEC = 60.0

# Rate limit (spec §4.3): 50 messages/min hard cap
RATE_LIMIT_MAX_PER_MIN = 50

# Configurable via env
LOG_FILE = os.environ.get("EFLOUD_LOG_FILE", "/app/logs/efloud_bot.log")
HEALTHZ_URL = os.environ.get("EFLOUD_HEALTHZ_URL", "http://efloud-bot:8080/healthz")
DEDUP_DB = os.environ.get("EFLOUD_ALERTER_DEDUP_DB", "/app/state/alerter_dedup.sqlite")
HEARTBEAT_FILE = os.environ.get(
    "EFLOUD_ALERTER_HEARTBEAT_FILE", "/app/state/alerter_heartbeat.json"
)
TELEGRAM_TOKEN = os.environ.get("EFLOUD_TELEGRAM_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("EFLOUD_TELEGRAM_CHAT_ID", "")


class Alerter:
    def __init__(self):
        self.dedup = Dedup(db_path=DEDUP_DB)
        self.log_offset = 0  # byte offset in log file
        self.healthz_history: dict = {}  # rule.match_health scratchpad
        # Rate limit: rolling 60-second window of message timestamps
        self.send_timestamps: deque = deque()
        # Cadence trackers
        self.next_healthz_poll = 0.0
        self.next_heartbeat = 0.0
        # Stat counters (logged hourly)
        self.stat_log_lines = 0
        self.stat_alerts_fired = 0
        self.stat_alerts_deduped = 0
        self.stat_alerts_rate_limited = 0
        self.next_stats_log = time.time() + 3600

    def run(self) -> None:
        log.info(f"alerter starting — log_file={LOG_FILE} healthz={HEALTHZ_URL}")
        if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
            log.warning(
                "EFLOUD_TELEGRAM_TOKEN or EFLOUD_TELEGRAM_CHAT_ID not set — "
                "alerts will be matched but NOT sent (dry-run mode)"
            )
        # Initial offset: skip existing log content (we don't want to alert on
        # historical events at startup; new lines from now on are what matters)
        self._init_log_offset()

        while True:
            now = time.monotonic()
            self._tail_logs()
            if now >= self.next_healthz_poll:
                self._poll_healthz()
                self.next_healthz_poll = now + HEALTHZ_POLL_INTERVAL_SEC
            if now >= self.next_heartbeat:
                self._write_heartbeat()
                self.next_heartbeat = now + HEARTBEAT_INTERVAL_SEC
            if time.time() >= self.next_stats_log:
                self._log_hourly_stats()
            time.sleep(LOG_TAIL_INTERVAL_SEC)

    def _init_log_offset(self) -> None:
        try:
            self.log_offset = Path(LOG_FILE).stat().st_size
        except FileNotFoundError:
            self.log_offset = 0

    def _tail_logs(self) -> None:
        try:
            stat = Path(LOG_FILE).stat()
        except FileNotFoundError:
            return
        if stat.st_size < self.log_offset:
            # Log was rotated (truncated or replaced); restart from start
            log.info("log file shrank — assuming rotation, resetting offset")
            self.log_offset = 0
        if stat.st_size == self.log_offset:
            return  # no new content
        with open(LOG_FILE, "r", encoding="utf-8", errors="replace") as f:
            f.seek(self.log_offset)
            for line in f:
                self.stat_log_lines += 1
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                except json.JSONDecodeError:
                    # Plain (non-JSON) log line — alerter cannot match; skip silently
                    continue
                self._dispatch_log(rec)
            self.log_offset = f.tell()

    def _dispatch_log(self, rec: dict) -> None:
        for rule in RULES:
            text = rule.match_log(rec)
            if text:
                self._maybe_fire(rule, text)

    def _poll_healthz(self) -> None:
        try:
            req = urllib.request.Request(HEALTHZ_URL)
            with urllib.request.urlopen(req, timeout=5) as resp:
                body = resp.read().decode("utf-8")
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            log.warning(f"healthz poll failed: {e}")
            return
        try:
            payload = json.loads(body)
        except json.JSONDecodeError:
            log.warning(f"healthz body not JSON: {body[:200]}")
            return
        for rule in RULES:
            text = rule.match_health(payload, self.healthz_history)
            if text:
                self._maybe_fire(rule, text)

    def _maybe_fire(self, rule: Rule, text: str) -> None:
        if not self.dedup.should_fire(rule.alert_key, rule.dedup_window_sec):
            self.stat_alerts_deduped += 1
            return
        # Rate limit: drop if 50 already sent in last 60s
        now = time.time()
        while self.send_timestamps and self.send_timestamps[0] < now - 60:
            self.send_timestamps.popleft()
        if len(self.send_timestamps) >= RATE_LIMIT_MAX_PER_MIN:
            self.stat_alerts_rate_limited += 1
            log.warning(
                f"rate limit hit ({RATE_LIMIT_MAX_PER_MIN}/min) — dropping {rule.alert_key}"
            )
            return
        ok = send_message(TELEGRAM_TOKEN, TELEGRAM_CHAT_ID, text)
        if ok:
            self.send_timestamps.append(now)
            self.stat_alerts_fired += 1
            log.info(f"alert fired: {rule.alert_key}")

    def _write_heartbeat(self) -> None:
        try:
            Path(HEARTBEAT_FILE).parent.mkdir(parents=True, exist_ok=True)
            tmp = Path(HEARTBEAT_FILE + ".tmp")
            tmp.write_text(
                json.dumps({"alerter_heartbeat_ts": int(time.time())}),
                encoding="utf-8",
            )
            os.replace(tmp, HEARTBEAT_FILE)
        except OSError as e:
            log.warning(f"heartbeat write failed: {e}")

    def _log_hourly_stats(self) -> None:
        log.info(
            f"hourly stats — log_lines={self.stat_log_lines} "
            f"fired={self.stat_alerts_fired} deduped={self.stat_alerts_deduped} "
            f"rate_limited={self.stat_alerts_rate_limited}"
        )
        self.stat_log_lines = 0
        self.stat_alerts_fired = 0
        self.stat_alerts_deduped = 0
        self.stat_alerts_rate_limited = 0
        self.next_stats_log = time.time() + 3600


def main() -> None:
    Alerter().run()


if __name__ == "__main__":
    main()
```

- [ ] **Step 5.2: Smoke import the module**

```powershell
python -c "from ops.alerter.alerter import Alerter; print('OK')"
```

Expected: prints `OK`. If imports fail, fix before continuing.

- [ ] **Step 5.3: Run full suite for regression**

```powershell
python -m pytest tests/ -q 2>&1 | Select-Object -Last 5
```

Expected: 89 collected unchanged (no new tests in this task).

- [ ] **Step 5.4: Commit**

```powershell
git add ops/alerter/alerter.py
git commit -m "feat(alerter): main loop with log-tail + healthz-poll + dedup + rate limit + heartbeat"
```

---

### Task 6: Heartbeat unit test

**Files:**
- Test: `tests/test_alerter_heartbeat.py` (1 test, ~40 lines)

The heartbeat write logic is small but its file format is the contract daily-report (Step 5) reads. Lock down the schema with a test.

- [ ] **Step 6.1: Write the test**

Create `tests/test_alerter_heartbeat.py`:

```python
"""Heartbeat — alerter writes {alerter_heartbeat_ts: int_epoch_sec} to a
JSON file. Daily-report (Step 5) reads this same shape.
"""
from __future__ import annotations

import json
import time
from pathlib import Path
from unittest import mock


def test_heartbeat_writes_alerter_heartbeat_ts_to_json_file(tmp_path: Path):
    heartbeat_path = tmp_path / "alerter_heartbeat.json"

    # Patch the module-level constant before importing Alerter so the heartbeat
    # path uses our tmp_path instead of the production default.
    with mock.patch("ops.alerter.alerter.HEARTBEAT_FILE", str(heartbeat_path)):
        from ops.alerter.alerter import Alerter
        a = Alerter()
        a._write_heartbeat()

    assert heartbeat_path.exists()
    data = json.loads(heartbeat_path.read_text(encoding="utf-8"))
    assert "alerter_heartbeat_ts" in data
    ts = data["alerter_heartbeat_ts"]
    assert isinstance(ts, int)
    # Within 5 seconds of now
    assert abs(int(time.time()) - ts) < 5
```

- [ ] **Step 6.2: Run test, expect PASS**

```powershell
python -m pytest tests/test_alerter_heartbeat.py -v 2>&1
```

Expected: 1 test passes.

- [ ] **Step 6.3: Run full suite**

```powershell
python -m pytest tests/ -q 2>&1 | Select-Object -Last 5
```

Expected: 90 collected (89 + 1).

- [ ] **Step 6.4: Commit**

```powershell
git add tests/test_alerter_heartbeat.py
git commit -m "test(alerter): heartbeat file schema {alerter_heartbeat_ts}"
```

---

## Deploy + verification

### Task 7: docker-compose alerter service

**Files:**
- Modify: `docker-compose.prod.yml`

Add an `alerter` service that reuses the `efloud-bot:latest` image, runs `python -m ops.alerter.alerter`, mounts logs read-only and state read-write.

- [ ] **Step 7.1: Read current docker-compose.prod.yml**

```powershell
Get-Content docker-compose.prod.yml
```

Confirm shape (efloud-bot, caddy, autoheal services from Step 3 if merged, else just efloud-bot + caddy). The alerter block goes after caddy.

- [ ] **Step 7.2: Add alerter service block**

Add to `docker-compose.prod.yml` after the `caddy:` block (and after `autoheal:` if Step 3 already shipped):

```yaml
  alerter:
    image: efloud-bot:latest          # reuse the bot's image (no separate Dockerfile)
    container_name: efloud-alerter
    restart: unless-stopped
    command: python -m ops.alerter.alerter
    env_file:
      - .env.production
    environment:
      - EFLOUD_LOG_FILE=/app/logs/efloud_bot.log
      - EFLOUD_HEALTHZ_URL=http://efloud-bot:8080/healthz
      - EFLOUD_ALERTER_DEDUP_DB=/app/state/alerter_dedup.sqlite
      - EFLOUD_ALERTER_HEARTBEAT_FILE=/app/state/alerter_heartbeat.json
    volumes:
      - efloud_logs:/app/logs:ro      # read-only — alerter only tails
      - efloud_state:/app/state       # read-write — dedup + heartbeat live here
    depends_on:
      efloud-bot:
        condition: service_started   # don't wait for healthy; alerter watches healthz
    logging:
      driver: json-file
      options:
        max-size: "5m"
        max-file: "3"
```

`.env.production` must contain `EFLOUD_TELEGRAM_TOKEN` and `EFLOUD_TELEGRAM_CHAT_ID` (operator sets these one-time per spec §4.3).

- [ ] **Step 7.3: Validate (optional — local docker)**

```powershell
docker compose -f docker-compose.prod.yml config 2>&1 | Select-Object -First 30
```

Expected: parsed config without errors. If docker not installed locally, SKIP — Hetzner-side validation in Step 9.

- [ ] **Step 7.4: Run full suite for regression (no test changes)**

```powershell
python -m pytest tests/ -q 2>&1 | Select-Object -Last 5
```

Expected: 90 collected unchanged.

- [ ] **Step 7.5: Commit**

```powershell
git add docker-compose.prod.yml
git commit -m "feat(deploy): alerter sidecar service (reuses efloud-bot image, separate command)"
```

---

### Task 8: End-to-end integration test

**Files:**
- Test: `tests/test_alerter_e2e.py` (1 test, ~80 lines)

Synthetic test: write a JSON log line that should fire `breaker.tripped.daily`, verify the alerter dispatches it once + dedups the second time.

- [ ] **Step 8.1: Write E2E test**

Create `tests/test_alerter_e2e.py`:

```python
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
        "logger": "efloud.safety.breaker",
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
```

Both tests are accounted for in Step 0.3's `Task 8 (E2E): 2 tests` budget. The first covers log-driven path (BreakerDailyRule → dedup), the second covers healthz-driven path (HealthCrashLoopRule → fire). Final after Task 8 = baseline 82 + 16 = 98 collected (92 pass + 6 skip).

- [ ] **Step 8.2: Run E2E tests**

```powershell
python -m pytest tests/test_alerter_e2e.py -v 2>&1 | Select-Object -Last 10
```

Expected: 2 tests pass.

- [ ] **Step 8.3: Run full suite**

```powershell
python -m pytest tests/ -q 2>&1 | Select-Object -Last 5
```

Expected: **98 collected = 92 pass + 6 skip** (82 baseline collected + 16 new pass = 98). Update Step 0.3 if you arrive at a different number.

- [ ] **Step 8.4: Commit**

```powershell
git add tests/test_alerter_e2e.py
git commit -m "test(alerter): e2e — log line fires + dedups; healthz payload fires"
```

---

### Task 9: Final verification + push

**Files:** none modified (verification only).

- [ ] **Step 9.1: Full test suite final check**

```powershell
python -m pytest tests/ -q 2>&1 | Select-Object -Last 5
```

Expected: 98 collected (92 pass + 6 skip). Final test budget per Step 0.3 = baseline 82 + 16 = 98.

- [ ] **Step 9.2: Smoke import the alerter package end-to-end**

```powershell
python -c @"
from ops.alerter.alerter import Alerter
from ops.alerter.dedup import Dedup
from ops.alerter.rules import RULES
from ops.alerter.telegram_client import send_message
print(f'rules loaded: {len(RULES)}')
print('alerter import OK')
"@
```

Expected: prints `rules loaded: 5` and `alerter import OK`.

- [ ] **Step 9.3: Code review checklist (manual)**

- `Dedup`: corrupt-file recovery moves aside (doesn't delete) — important for forensics
- `send_message`: never raises; returns False on any error so caller can drop and continue
- Rules: each rule's `match_log` checks logger name AND level AND substring — defends against false positives
- Alerter main loop: never blocks indefinitely (1s tail interval, 30s healthz poll, all timeouts capped at 10s)
- Heartbeat: atomic write via tmp + os.replace (same pattern as RuntimeState)
- No Telegram token / chat_id leaked into log messages anywhere

- [ ] **Step 9.4: Push branch (defer tag until merge)**

```powershell
git push origin feature/asama-2-step-4-alerter
```

- [ ] **Step 9.5: Final report to owner**

Output:
- Branch: `feature/asama-2-step-4-alerter`
- Commits: ~9 (one per task)
- Tests added: 16
- New env vars (operator must set in `.env.production`):
  - `EFLOUD_TELEGRAM_TOKEN=<bot-token-from-BotFather>`
  - `EFLOUD_TELEGRAM_CHAT_ID=<owner's-chat-id-from-getUpdates>`
- New persistent files: `state/alerter_dedup.sqlite`, `state/alerter_heartbeat.json` (both auto-created)
- Rollback: revert branch + `docker compose stop alerter` + remove from compose
- Spec deviation: heartbeat in separate `alerter_heartbeat.json` (not bot's `runtime.json`)
- **Production deploy notes:**
  1. Operator: create Telegram bot via @BotFather, get token; message bot, GET `getUpdates`, get chat_id
  2. Add 2 env vars to `.env.production` on Hetzner
  3. Merge to master + push
  4. SSH Hetzner: `cd /opt/efloud-bot && git pull origin master`
  5. Rebuild image (alerter reuses it): `docker compose -f docker-compose.prod.yml build efloud-bot`
  6. Start alerter: `docker compose -f docker-compose.prod.yml up -d alerter`
  7. Verify: `docker compose -f docker-compose.prod.yml logs alerter --tail 30` should show `alerter starting — log_file=...`
  8. Live verification (optional — outside trading hours): trip the consecutive-loss breaker manually OR write a fake JSON log line containing "Daily loss limit" to the bot's log file → Telegram should receive a CRITICAL message within ~2s
  9. Verify dedup: trip the same alert 5× within 30 min — Telegram should receive only ONE message

---

## What this plan does NOT cover

Per spec §11, deferred to follow-up plans:

- **Step 4b** (follow-up): bot-side detectors for `position.stuck_over_6h`, `exchange.error_burst`, `balance.unexpected_change` + 3 corresponding rules in `ops/alerter/rules.py`. Each requires NEW logic in the bot (position-age tracker, exchange-error rolling counter, balance-snapshot comparator). Estimate: separate 3-5 day plan.
- **Step 5**: Daily email report (reads alerter heartbeat + Supabase trades + log summaries; emits SMTP)
- **Step 6**: Log rotation tuning (custom `GzipRotatingFileHandler`)

---

## Rollback (if anything goes bad)

1. **Revert the branch:** `git revert <merge-commit>` on master, redeploy. Alerter container removed from compose; existing functionality (Steps 1-3) untouched. No data risk.
2. **Disable alerter only:** `docker compose -f docker-compose.prod.yml stop alerter`. Bot keeps running; alerts stop firing. SQLite + heartbeat files remain on disk for inspection.
3. **Revert specific tasks:** each task is its own commit; `git revert <hash>` for any single task that proves problematic.

---

## Acceptance for Step 4

Step 4 is **DONE** when:
- All Task 0-9 checkboxes ticked
- All tests pass (count = baseline 82 + exactly 16 new = 98 collected; 92 pass + 6 skip)
- Smoke import succeeds (`from ops.alerter.alerter import Alerter`)
- `docker compose config` validates the compose file
- Branch pushed
- Operator has Telegram bot token + chat_id ready in `.env.production`
- Owner reviews + approves before promoting to master and Hetzner

After acceptance → write Step 5 plan (daily email report).
