# Aşama 2 — Step 5: Daily Email Report Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship a daily email cron at 08:00 UTC that summarizes the previous 24 hours of trading: equity delta, trade list, win/loss stats, and an "ALERTER DOWN" prefix when the alerter's heartbeat is stale (≥2h since last write). Operator gets a clean SMTP digest without watching dashboards.

**Architecture:** Standalone Python script (`ops/daily_report/report.py`) running in a one-shot Docker container that reuses `efloud-bot:latest`. Reads last-24h `trades` + `equity_history` rows from Supabase via the existing `backend/db.py:Database` class, reads `state/alerter_heartbeat.json` to detect a dead alerter, composes a plain-text markdown body, sends via SMTP using stdlib `smtplib` + `email.message.EmailMessage`. Hetzner crontab triggers `docker compose run --rm daily-report` at 08:00 UTC daily, with a shell `||` fallback that pings Telegram if the cron itself fails.

**Tech Stack:** Python 3.12 stdlib only (`smtplib`, `email.message`, `asyncio`, `json`, `pathlib`, `datetime`) + reused `backend.db.Database` (asyncpg). No Jinja2 — markdown body is composed via inline f-strings (one fixed shape per spec §4.4). pytest for tests.

**Spec parent:** `docs/superpowers/specs/2026-05-07-asama-2-self-maintenance-observability-design.md` (§4.4 daily email + §4.3 heartbeat dead-man's switch)

**Estimated effort:** 4-5 days for one engineer.

---

## Codebase reality check

### What's already in place (master HEAD post Aşama 2 Steps 1-4)

- `backend/db.py:Database` — asyncpg pool, with `fetch_recent_trades(limit)` (line 103) and `fetch_equity_history(days)` (line 141). Both already exist; we add a 24h-windowed `fetch_trades_since(since_ts)` method.
- `state/alerter_heartbeat.json` — written every 60s by alerter (Step 4). Schema: `{"alerter_heartbeat_ts": <epoch_seconds_int>}`. Daily report reads it.
- `ops/__init__.py` + `ops/alerter/__init__.py` — package markers from Step 4. Step 5 adds `ops/daily_report/`.
- `efloud-bot:latest` Docker image — already includes all Python deps. Daily report reuses it (no separate Dockerfile).
- `EFLOUD_TELEGRAM_TOKEN` + `EFLOUD_TELEGRAM_CHAT_ID` env vars — already in `.env.production` (Step 4 deploy). Used by the failure-to-send wrapper.

### Why no Jinja2

Spec §4.4 said "Jinja2 template" but the body has one fixed shape with simple substitutions. Jinja2 adds a dependency + a separate template file for marginal benefit. Plan deviates: inline markdown via f-strings in `ops/daily_report/render.py`. Documented in §"Spec deviations" below.

### Existing breaker / restart / anomaly counters: not in scope

Spec §4.4 example email lists "Breaker trips: N", "Restarts: N", "Anomalies (alerter): N". These require either:
- New DB columns or events tables (breaker events not currently persisted)
- Docker API queries for restart counts
- Reading alerter's SQLite dedup table

To keep Step 5 scope manageable, the email body in this plan covers:
- ✅ PnL summary (equity, trades, win rate, best/worst)
- ✅ Trade list (last 24h)
- ✅ ALERTER DOWN prefix when heartbeat stale
- ❌ Breaker trips count, restart count, anomalies count → Step 5b (follow-up)

The email body has a "## Operational" section that says `(see Telegram for breaker / alert detail)` — pointing the operator to the Step 4 alerter for those events.

---

## Spec deviations to call out

1. **No Jinja2:** template is an inline f-string in `render.py`. KISS for one fixed body shape.
2. **Breaker / restart / anomaly counters deferred:** Step 5b will add them when supporting infrastructure (events tables, log queries) is ready.
3. **Subject line uses ASCII separators:** spec example used em-dash (`—`) but some SMTP servers/clients have charset quirks. Plan uses ASCII hyphen (`-`). Cosmetic only.

---

## File structure (what gets created vs modified)

**Create:**
- `ops/daily_report/__init__.py` (empty package marker)
- `ops/daily_report/aggregate.py` (~80 lines) — `compute_summary(trades, equity_history)` pure function
- `ops/daily_report/heartbeat.py` (~50 lines) — `check_alerter_heartbeat(path)` returns `(stale: bool, age_sec: int | None)`
- `ops/daily_report/smtp_client.py` (~80 lines) — `send_email(host, port, username, password, from_addr, to_addr, subject, body)` returns bool
- `ops/daily_report/render.py` (~120 lines) — `render_email(summary, trades, heartbeat_status, report_date) -> (subject, body)`
- `ops/daily_report/report.py` (~120 lines) — main script (DB → aggregate → render → send), runs once and exits
- `tests/test_daily_aggregate.py` (~120 lines, 5 tests)
- `tests/test_daily_heartbeat.py` (~70 lines, 3 tests)
- `tests/test_daily_smtp.py` (~60 lines, 2 tests)
- `tests/test_daily_render.py` (~120 lines, 4 tests)
- `tests/test_daily_e2e.py` (~80 lines, 1 test)
- `docs/runbooks/daily-report-cron-setup.md` (~60 lines) — Hetzner crontab setup procedure

**Modify:**
- `backend/db.py` — add `fetch_trades_since(since_ts: datetime) -> list[dict]` method (mirror of `fetch_recent_trades` but windowed)
- `docker-compose.prod.yml` — add `daily-report` service block with `profiles: [scheduled]` so default `up -d` does NOT start it

**Delete:** none.

---

## Pre-flight

### Task 0: Worktree + branch setup, baseline verification

**Files:** none modified, only environment setup.

- [ ] **Step 0.1: Create dedicated worktree from master**

```powershell
cd C:\Users\utkuc\Downloads\efloud-bot
git worktree add ../efloud-bot-asama2-step5 -b feature/asama-2-step-5-daily-report master
cd ../efloud-bot-asama2-step5
```

Expected: new worktree on `feature/asama-2-step-5-daily-report` from master HEAD (which has Steps 1-4 + TP1/TradeClosed rules merged).

- [ ] **Step 0.2: Verify base tests pass + capture baseline**

```powershell
python -m pytest tests/ -q --no-header 2>&1 | Select-Object -Last 5
```

Expected: master has Steps 1-4 + 2 trade rules merged. Test count should be `BASELINE_PASSED = 98 ± 2` and `BASELINE_SKIPPED = 6` (DB-dependent skips). Record actual numbers; final after Step 5 must be **exactly** `BASELINE_PASSED + 15` passed (skip count unchanged at 6). If baseline differs from 98, adjust Step 0.3 accordingly.

- [ ] **Step 0.3: Test budget**

New tests added by this plan (= 15):
- Task 2 (`tests/test_daily_aggregate.py`): 5 tests (`test_empty_trades`, `test_all_winners`, `test_all_losers`, `test_mixed_with_best_and_worst`, `test_equity_delta_computed`)
- Task 3 (`tests/test_daily_heartbeat.py`): 3 tests (`test_fresh_heartbeat_not_stale`, `test_old_heartbeat_is_stale`, `test_missing_file_is_stale`)
- Task 4 (`tests/test_daily_smtp.py`): 2 tests (`test_send_email_success_returns_true`, `test_send_email_smtp_error_returns_false`)
- Task 5 (`tests/test_daily_render.py`): 4 tests (`test_subject_includes_date_and_equity`, `test_body_contains_trade_list`, `test_alerter_down_prefix_when_stale`, `test_empty_trades_renders_no_trades_today`)
- Task 9 (`tests/test_daily_e2e.py`): 1 test (`test_full_report_cycle_with_mocked_db_and_smtp`)

Total: 5+3+2+4+1 = **15**.

Running totals at task boundaries:
- After Task 1: baseline (no tests)
- After Task 2: baseline + 5
- After Task 3: baseline + 8
- After Task 4: baseline + 10
- After Task 5: baseline + 14
- After Task 6: baseline + 14 (no new tests; integration via Task 9 E2E)
- After Task 7: baseline + 14 (Docker config only)
- After Task 8: baseline + 14 (markdown runbook only)
- After Task 9: baseline + 15 ← FINAL

---

## Foundation

### Task 1: ops/daily_report/ package skeleton

**Files:**
- Create: `ops/daily_report/__init__.py` (empty)

Minimal package marker. No tests.

- [ ] **Step 1.1: Create empty package marker**

```powershell
"" | Out-File -Encoding utf8 -FilePath ops/daily_report/__init__.py -NoNewline
```

If `ops/daily_report/` directory doesn't exist yet, create it first:
```powershell
New-Item -ItemType Directory -Path ops/daily_report -Force | Out-Null
```

- [ ] **Step 1.2: Commit**

```powershell
git add ops/daily_report/__init__.py
git commit -m "scaffold(daily-report): empty ops/daily_report/ package marker"
```

---

### Task 2: PnL aggregation pure function

**Files:**
- Create: `ops/daily_report/aggregate.py`
- Test: `tests/test_daily_aggregate.py` (5 tests)

`compute_summary(trades, equity_history)` takes raw DB rows and returns a dict with computed fields (equity start/end, trade count, win rate, best/worst). Pure function, easy to unit-test.

- [ ] **Step 2.1: Write tests first**

Create `tests/test_daily_aggregate.py`:

```python
"""Daily report aggregate — compute_summary(trades, equity_history)."""
from __future__ import annotations

from datetime import datetime, timezone

from ops.daily_report.aggregate import compute_summary


def _trade(symbol: str, pnl: float, direction: str = "LONG", reason: str = "TP2") -> dict:
    """Helper to build a trade row matching the DB schema."""
    return {
        "id": "abc-123",
        "symbol": symbol,
        "direction": direction,
        "entry": 100.0,
        "exit": 100.0 + pnl / 0.01 if direction == "LONG" else 100.0 - pnl / 0.01,
        "size": 0.01,
        "pnl_usdt": pnl,
        "pnl_pct": pnl / 100.0 * 100,  # rough
        "reason": reason,
        "opened_at": datetime(2026, 5, 7, 10, 0, tzinfo=timezone.utc),
        "closed_at": datetime(2026, 5, 7, 12, 0, tzinfo=timezone.utc),
        "confluence": 80,
    }


def _equity(balance: float, ts: datetime) -> dict:
    return {"ts": ts, "balance": balance, "open_positions_count": 0}


def test_empty_trades():
    summary = compute_summary(trades=[], equity_history=[])
    assert summary["trade_count"] == 0
    assert summary["wins"] == 0
    assert summary["losses"] == 0
    assert summary["win_rate_pct"] is None  # undefined when no trades
    assert summary["best_trade"] is None
    assert summary["worst_trade"] is None
    assert summary["equity_start"] is None
    assert summary["equity_end"] is None


def test_all_winners():
    trades = [_trade("BTC/USDT", 10.0), _trade("ETH/USDT", 5.0)]
    summary = compute_summary(trades=trades, equity_history=[])
    assert summary["trade_count"] == 2
    assert summary["wins"] == 2
    assert summary["losses"] == 0
    assert summary["win_rate_pct"] == 100.0
    assert summary["best_trade"]["pnl_usdt"] == 10.0
    assert summary["worst_trade"]["pnl_usdt"] == 5.0  # in all-winners list, "worst" is smallest win


def test_all_losers():
    trades = [_trade("BTC/USDT", -10.0, reason="SL"), _trade("ETH/USDT", -5.0, reason="SL")]
    summary = compute_summary(trades=trades, equity_history=[])
    assert summary["wins"] == 0
    assert summary["losses"] == 2
    assert summary["win_rate_pct"] == 0.0
    assert summary["best_trade"]["pnl_usdt"] == -5.0  # least bad
    assert summary["worst_trade"]["pnl_usdt"] == -10.0


def test_mixed_with_best_and_worst():
    trades = [
        _trade("BTC/USDT", 15.0),
        _trade("ETH/USDT", -8.0, reason="SL"),
        _trade("XRP/USDT", 3.0),
        _trade("DOGE/USDT", -2.0, reason="SL"),
    ]
    summary = compute_summary(trades=trades, equity_history=[])
    assert summary["trade_count"] == 4
    assert summary["wins"] == 2
    assert summary["losses"] == 2
    assert summary["win_rate_pct"] == 50.0
    assert summary["best_trade"]["symbol"] == "BTC/USDT"
    assert summary["worst_trade"]["symbol"] == "ETH/USDT"


def test_equity_delta_computed():
    eq_start = datetime(2026, 5, 7, 8, 0, tzinfo=timezone.utc)
    eq_end = datetime(2026, 5, 8, 8, 0, tzinfo=timezone.utc)
    equity_history = [_equity(2000.0, eq_start), _equity(2050.0, eq_end)]
    summary = compute_summary(trades=[], equity_history=equity_history)
    assert summary["equity_start"] == 2000.0
    assert summary["equity_end"] == 2050.0
    assert summary["equity_delta_usdt"] == 50.0
    assert summary["equity_delta_pct"] == 2.5
```

- [ ] **Step 2.2: Run tests, expect FAIL**

```powershell
python -m pytest tests/test_daily_aggregate.py -v 2>&1
```

Expected: ImportError on `ops.daily_report.aggregate`. All 5 tests fail at collection.

- [ ] **Step 2.3: Implement aggregate.py**

Create `ops/daily_report/aggregate.py`:

```python
"""Daily report aggregation — compute_summary() pure function.

Takes raw DB rows (trades + equity_history) and returns a dict with computed
fields suitable for rendering. No I/O, no DB calls — caller fetches rows first.
"""
from __future__ import annotations

from typing import Any, Optional


def compute_summary(
    trades: list[dict],
    equity_history: list[dict],
) -> dict[str, Any]:
    """Aggregate last-24h trades + equity into summary dict.

    Args:
        trades: list of trade dicts (closed trades within window).
                Each must have keys: symbol, direction, pnl_usdt, reason, opened_at, closed_at.
        equity_history: list of equity_history rows (balance over time).
                Must have keys: ts, balance.

    Returns:
        dict with: trade_count, wins, losses, win_rate_pct, best_trade, worst_trade,
                   equity_start, equity_end, equity_delta_usdt, equity_delta_pct.
        None for any field that can't be computed (no trades, no equity history).
    """
    summary: dict[str, Any] = {
        "trade_count": len(trades),
        "wins": 0,
        "losses": 0,
        "win_rate_pct": None,
        "best_trade": None,
        "worst_trade": None,
        "equity_start": None,
        "equity_end": None,
        "equity_delta_usdt": None,
        "equity_delta_pct": None,
    }

    # Trade aggregation — wins/losses by pnl_usdt sign
    if trades:
        wins = [t for t in trades if (t.get("pnl_usdt") or 0) > 0]
        losses = [t for t in trades if (t.get("pnl_usdt") or 0) < 0]
        summary["wins"] = len(wins)
        summary["losses"] = len(losses)
        # win_rate over decided trades only (skip break-even pnl=0)
        decided = len(wins) + len(losses)
        if decided > 0:
            summary["win_rate_pct"] = round(len(wins) / decided * 100, 2)

        # Best / worst by pnl_usdt
        sorted_trades = sorted(trades, key=lambda t: t.get("pnl_usdt") or 0)
        summary["best_trade"] = sorted_trades[-1]
        summary["worst_trade"] = sorted_trades[0]

    # Equity delta — first vs last balance in window
    if equity_history:
        sorted_eq = sorted(equity_history, key=lambda e: e["ts"])
        first = sorted_eq[0]["balance"]
        last = sorted_eq[-1]["balance"]
        summary["equity_start"] = round(first, 2)
        summary["equity_end"] = round(last, 2)
        summary["equity_delta_usdt"] = round(last - first, 2)
        if first > 0:
            summary["equity_delta_pct"] = round((last - first) / first * 100, 2)

    return summary
```

- [ ] **Step 2.4: Run tests, expect PASS**

```powershell
python -m pytest tests/test_daily_aggregate.py -v 2>&1 | Select-Object -Last 10
```

Expected: 5 tests pass.

- [ ] **Step 2.5: Run full suite for regression**

```powershell
python -m pytest tests/ -q 2>&1 | Select-Object -Last 5
```

Expected: baseline + 5 collected.

- [ ] **Step 2.6: Commit**

```powershell
git add ops/daily_report/aggregate.py tests/test_daily_aggregate.py
git commit -m "feat(daily-report): compute_summary aggregator (pnl, win-rate, best/worst, equity delta)"
```

---

### Task 3: Heartbeat staleness check

**Files:**
- Create: `ops/daily_report/heartbeat.py`
- Test: `tests/test_daily_heartbeat.py` (3 tests)

Reads `state/alerter_heartbeat.json` (written by Step 4 alerter every 60s) and returns `(stale: bool, age_sec: Optional[int])`. Threshold per spec §4.3: 2 hours.

- [ ] **Step 3.1: Write tests first**

Create `tests/test_daily_heartbeat.py`:

```python
"""Heartbeat staleness check — reads state/alerter_heartbeat.json."""
from __future__ import annotations

import json
import time
from pathlib import Path

from ops.daily_report.heartbeat import (
    HEARTBEAT_STALE_AFTER_SEC,
    check_alerter_heartbeat,
)


def test_fresh_heartbeat_not_stale(tmp_path: Path):
    hb_path = tmp_path / "alerter_heartbeat.json"
    hb_path.write_text(json.dumps({"alerter_heartbeat_ts": int(time.time())}))
    stale, age = check_alerter_heartbeat(str(hb_path))
    assert stale is False
    assert age is not None
    assert age < 5  # within 5s of now


def test_old_heartbeat_is_stale(tmp_path: Path):
    """Heartbeat written 3 hours ago > 2h threshold → stale."""
    hb_path = tmp_path / "alerter_heartbeat.json"
    three_hours_ago = int(time.time()) - 3 * 60 * 60
    hb_path.write_text(json.dumps({"alerter_heartbeat_ts": three_hours_ago}))
    stale, age = check_alerter_heartbeat(str(hb_path))
    assert stale is True
    assert age is not None
    assert age >= HEARTBEAT_STALE_AFTER_SEC


def test_missing_file_is_stale(tmp_path: Path):
    """No heartbeat file → alerter never wrote one → treat as stale."""
    hb_path = tmp_path / "does_not_exist.json"
    stale, age = check_alerter_heartbeat(str(hb_path))
    assert stale is True
    assert age is None  # can't compute age if file missing
```

- [ ] **Step 3.2: Run tests, expect FAIL**

```powershell
python -m pytest tests/test_daily_heartbeat.py -v 2>&1
```

Expected: ImportError. 3 tests fail at collection.

- [ ] **Step 3.3: Implement heartbeat.py**

Create `ops/daily_report/heartbeat.py`:

```python
"""Heartbeat staleness check for daily report.

Reads `state/alerter_heartbeat.json` (written by Step 4 alerter every 60s) and
determines whether the alerter is alive. Stale heartbeat → daily report adds
'ALERTER DOWN' subject prefix per spec §4.3.
"""
from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import Optional, Tuple

log = logging.getLogger("efloud.daily_report.heartbeat")

# Spec §4.3: alerter writes every 60s; >2h since last write means alerter died
HEARTBEAT_STALE_AFTER_SEC = 2 * 60 * 60


def check_alerter_heartbeat(path: str) -> Tuple[bool, Optional[int]]:
    """Return (stale, age_sec).

    - stale=True if file missing OR ts is older than HEARTBEAT_STALE_AFTER_SEC.
    - age_sec is None if the file is missing or unreadable; otherwise the
      number of seconds since the last heartbeat write.
    """
    p = Path(path)
    if not p.exists():
        log.warning(f"alerter heartbeat file missing: {path}")
        return (True, None)
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        ts = int(data["alerter_heartbeat_ts"])
    except (json.JSONDecodeError, KeyError, TypeError, ValueError) as e:
        log.warning(f"alerter heartbeat file corrupt/malformed ({path}): {e}")
        return (True, None)

    age = int(time.time()) - ts
    stale = age >= HEARTBEAT_STALE_AFTER_SEC
    return (stale, age)
```

- [ ] **Step 3.4: Run tests, expect PASS**

```powershell
python -m pytest tests/test_daily_heartbeat.py -v 2>&1 | Select-Object -Last 8
```

Expected: 3 tests pass.

- [ ] **Step 3.5: Commit**

```powershell
git add ops/daily_report/heartbeat.py tests/test_daily_heartbeat.py
git commit -m "feat(daily-report): check_alerter_heartbeat (stale=True if >2h or missing)"
```

---

### Task 4: SMTP sender (stdlib)

**Files:**
- Create: `ops/daily_report/smtp_client.py`
- Test: `tests/test_daily_smtp.py` (2 tests)

Stdlib `smtplib` + `email.message.EmailMessage`. STARTTLS by default (Gmail port 587). Returns True on success, False on any error (logged WARNING, never raises).

- [ ] **Step 4.1: Write tests first**

Create `tests/test_daily_smtp.py`:

```python
"""SMTP client — stdlib smtplib wrapper for daily report send."""
from __future__ import annotations

from unittest import mock

from ops.daily_report.smtp_client import send_email


def test_send_email_success_returns_true():
    """Mock SMTP connection that accepts send_message. Returns True."""
    with mock.patch("ops.daily_report.smtp_client.smtplib.SMTP") as smtp_cls:
        smtp_inst = smtp_cls.return_value.__enter__.return_value
        smtp_inst.send_message = mock.MagicMock()
        ok = send_email(
            host="smtp.example.com", port=587,
            username="bot@example.com", password="appPASS",
            from_addr="bot@example.com", to_addr="ops@example.com",
            subject="Test report", body="Body content",
        )
        assert ok is True
        smtp_inst.starttls.assert_called_once()
        smtp_inst.login.assert_called_once_with("bot@example.com", "appPASS")
        smtp_inst.send_message.assert_called_once()


def test_send_email_smtp_error_returns_false():
    """Mock SMTP raising on connect → send_email logs and returns False (no raise)."""
    import smtplib
    with mock.patch(
        "ops.daily_report.smtp_client.smtplib.SMTP",
        side_effect=smtplib.SMTPException("connection refused"),
    ):
        ok = send_email(
            host="smtp.example.com", port=587,
            username="bot@example.com", password="appPASS",
            from_addr="bot@example.com", to_addr="ops@example.com",
            subject="Test report", body="Body content",
        )
        assert ok is False
```

- [ ] **Step 4.2: Run tests, expect FAIL**

```powershell
python -m pytest tests/test_daily_smtp.py -v 2>&1
```

Expected: ImportError. 2 tests fail at collection.

- [ ] **Step 4.3: Implement smtp_client.py**

Create `ops/daily_report/smtp_client.py`:

```python
"""SMTP send — stdlib smtplib + email.message wrapper for daily report.

Uses STARTTLS (port 587 default). Returns True on 2xx-equivalent success,
False on any exception. Errors logged WARNING; caller (the cron command)
relies on exit code to trigger the failure-to-send Telegram fallback.
"""
from __future__ import annotations

import logging
import smtplib
from email.message import EmailMessage

log = logging.getLogger("efloud.daily_report.smtp")

TIMEOUT_SEC = 30


def send_email(
    host: str,
    port: int,
    username: str,
    password: str,
    from_addr: str,
    to_addr: str,
    subject: str,
    body: str,
) -> bool:
    """Send a plain-text email. Returns True on success, False on any error."""
    if not host or not username or not password or not to_addr:
        log.warning("send_email skipped: missing required SMTP config")
        return False

    msg = EmailMessage()
    msg["From"] = from_addr
    msg["To"] = to_addr
    msg["Subject"] = subject
    msg.set_content(body, subtype="plain", charset="utf-8")

    try:
        with smtplib.SMTP(host, port, timeout=TIMEOUT_SEC) as smtp:
            smtp.starttls()
            smtp.login(username, password)
            smtp.send_message(msg)
        return True
    except (smtplib.SMTPException, OSError) as e:
        log.warning(f"send_email failed via {host}:{port}: {e}")
        return False
```

- [ ] **Step 4.4: Run tests, expect PASS**

```powershell
python -m pytest tests/test_daily_smtp.py -v 2>&1
```

Expected: 2 tests pass.

- [ ] **Step 4.5: Commit**

```powershell
git add ops/daily_report/smtp_client.py tests/test_daily_smtp.py
git commit -m "feat(daily-report): SMTP send_email via stdlib smtplib + STARTTLS"
```

---

### Task 5: Email body composer (markdown)

**Files:**
- Create: `ops/daily_report/render.py`
- Test: `tests/test_daily_render.py` (4 tests)

`render_email(summary, trades, heartbeat_status, report_date) -> (subject, body)`. Composes the markdown email body per spec §4.4 layout. Inline f-strings (no Jinja2). Subject prefixed with "ALERTER DOWN" when heartbeat is stale.

- [ ] **Step 5.1: Write tests first**

Create `tests/test_daily_render.py`:

```python
"""Daily report rendering — render_email() composes subject + body."""
from __future__ import annotations

from datetime import date, datetime, timezone

from ops.daily_report.render import render_email


def _summary(**overrides) -> dict:
    """Builds a summary dict with sensible defaults; override per test."""
    base = {
        "trade_count": 4,
        "wins": 3,
        "losses": 1,
        "win_rate_pct": 75.0,
        "best_trade": {"symbol": "BTC/USDT", "pnl_usdt": 15.0, "direction": "LONG", "reason": "TP2"},
        "worst_trade": {"symbol": "ETH/USDT", "pnl_usdt": -8.0, "direction": "SHORT", "reason": "SL"},
        "equity_start": 2000.0,
        "equity_end": 2050.0,
        "equity_delta_usdt": 50.0,
        "equity_delta_pct": 2.5,
    }
    base.update(overrides)
    return base


def _trades(n: int = 2) -> list[dict]:
    return [
        {
            "symbol": "BTC/USDT", "direction": "LONG",
            "entry": 50000.0, "exit": 51000.0, "pnl_usdt": 10.0, "reason": "TP2",
            "closed_at": datetime(2026, 5, 7, 14, 0, tzinfo=timezone.utc),
        },
        {
            "symbol": "ETH/USDT", "direction": "SHORT",
            "entry": 3000.0, "exit": 3050.0, "pnl_usdt": -5.0, "reason": "SL",
            "closed_at": datetime(2026, 5, 7, 16, 0, tzinfo=timezone.utc),
        },
    ][:n]


def test_subject_includes_date_and_equity():
    summary = _summary(equity_end=2050.0, equity_delta_pct=2.5)
    subject, body = render_email(
        summary=summary,
        trades=_trades(2),
        heartbeat_stale=False,
        heartbeat_age_sec=120,
        report_date=date(2026, 5, 7),
    )
    assert "2026-05-07" in subject
    assert "2050" in subject  # equity in subject
    assert "+2.5" in subject or "2.5" in subject  # delta sign in subject


def test_body_contains_trade_list():
    summary = _summary()
    subject, body = render_email(
        summary=summary,
        trades=_trades(2),
        heartbeat_stale=False,
        heartbeat_age_sec=120,
        report_date=date(2026, 5, 7),
    )
    # Body has each trade's symbol
    assert "BTC/USDT" in body
    assert "ETH/USDT" in body
    # Body has win-rate
    assert "75" in body  # 75.0% as string
    # Body has equity delta
    assert "50.0" in body or "+50" in body


def test_alerter_down_prefix_when_stale():
    summary = _summary()
    subject, body = render_email(
        summary=summary,
        trades=_trades(2),
        heartbeat_stale=True,
        heartbeat_age_sec=10800,  # 3h
        report_date=date(2026, 5, 7),
    )
    # Subject prefixed
    assert subject.startswith("ALERTER DOWN") or "ALERTER DOWN" in subject
    # Body explains why
    assert "alerter" in body.lower()
    assert "10800" in body or "3h" in body.lower() or "stale" in body.lower()


def test_empty_trades_renders_no_trades_today():
    summary = _summary(
        trade_count=0, wins=0, losses=0, win_rate_pct=None,
        best_trade=None, worst_trade=None,
    )
    subject, body = render_email(
        summary=summary,
        trades=[],
        heartbeat_stale=False,
        heartbeat_age_sec=120,
        report_date=date(2026, 5, 7),
    )
    # Body says no trades — but doesn't crash on missing best/worst
    assert "no trades" in body.lower() or "0 trades" in body.lower()
```

- [ ] **Step 5.2: Run tests, expect FAIL**

```powershell
python -m pytest tests/test_daily_render.py -v 2>&1
```

Expected: ImportError. 4 tests fail at collection.

- [ ] **Step 5.3: Implement render.py**

Create `ops/daily_report/render.py`:

```python
"""Daily report markdown rendering. Inline f-strings (no Jinja2)."""
from __future__ import annotations

from datetime import date
from typing import Optional


def _fmt_pnl(value: Optional[float]) -> str:
    """Format a PnL number with sign + 2 decimals."""
    if value is None:
        return "-"
    return f"{value:+.2f}"


def _fmt_pct(value: Optional[float]) -> str:
    """Format a percentage with 1 decimal + sign."""
    if value is None:
        return "-"
    return f"{value:+.2f}%"


def _trade_row(t: dict) -> str:
    """One row of the trade table."""
    symbol = t.get("symbol", "?")
    direction = t.get("direction", "?")
    entry = t.get("entry") or 0.0
    exit_price = t.get("exit") or 0.0
    pnl = t.get("pnl_usdt") or 0.0
    reason = t.get("reason", "?")
    return f"| {symbol} | {direction} | {entry:.4f} | {exit_price:.4f} | ${pnl:+.2f} | {reason} |"


def render_email(
    summary: dict,
    trades: list[dict],
    heartbeat_stale: bool,
    heartbeat_age_sec: Optional[int],
    report_date: date,
) -> tuple[str, str]:
    """Render the daily report email — returns (subject, body).

    Args:
        summary: output of compute_summary().
        trades: raw trade dicts (last 24h, closed).
        heartbeat_stale: True if alerter heartbeat is older than 2h or missing.
        heartbeat_age_sec: age in seconds, or None if file missing.
        report_date: date the report covers (typically yesterday in UTC).

    Returns:
        (subject, body) — both strings.
    """
    # Subject — uses ASCII separators (NOT em-dash, charset safety)
    eq_end = summary.get("equity_end")
    eq_pct = summary.get("equity_delta_pct")
    if eq_end is None:
        equity_str = "no-equity-data"
    else:
        eq_pct_str = _fmt_pct(eq_pct) if eq_pct is not None else ""
        equity_str = f"equity ${eq_end:.2f} ({eq_pct_str})"
    subject = f"efloud-bot daily report - {report_date.isoformat()} - {equity_str}"
    if heartbeat_stale:
        subject = "ALERTER DOWN - " + subject

    # Body — markdown
    lines: list[str] = []
    lines.append(f"# efloud-bot daily report — {report_date.isoformat()}")
    lines.append("")

    # Heartbeat warning section (only when stale)
    if heartbeat_stale:
        lines.append("## ⚠️ ALERTER DOWN")
        if heartbeat_age_sec is None:
            lines.append("Alerter heartbeat file is missing — alerter never wrote it or file got removed.")
        else:
            hours = heartbeat_age_sec / 3600.0
            lines.append(
                f"Alerter heartbeat is stale ({heartbeat_age_sec}s ≈ {hours:.1f}h since last write). "
                f"This means the alerter sidecar may be down — Telegram alerts may not have fired."
            )
        lines.append("")

    # PnL summary
    lines.append("## PnL summary")
    if summary.get("equity_start") is not None and summary.get("equity_end") is not None:
        lines.append(
            f"- Equity: ${summary['equity_start']:.2f} → ${summary['equity_end']:.2f} "
            f"({_fmt_pct(summary.get('equity_delta_pct'))})"
        )
    else:
        lines.append("- Equity: no equity_history data available for this window")
    if summary["trade_count"] == 0:
        lines.append("- Trades: 0 trades today")
    else:
        wr = summary.get("win_rate_pct")
        wr_str = f"{wr:.1f}%" if wr is not None else "-"
        lines.append(
            f"- Trades: {summary['trade_count']} ({summary['wins']} wins, "
            f"{summary['losses']} losses, win rate {wr_str})"
        )
        if summary.get("best_trade"):
            bt = summary["best_trade"]
            lines.append(f"- Best trade: {bt['symbol']} {_fmt_pnl(bt.get('pnl_usdt'))}")
        if summary.get("worst_trade"):
            wt = summary["worst_trade"]
            lines.append(f"- Worst trade: {wt['symbol']} {_fmt_pnl(wt.get('pnl_usdt'))}")
    lines.append("")

    # Trade list table
    lines.append("## Trade list (last 24h)")
    if not trades:
        lines.append("No trades closed in this window.")
    else:
        lines.append("| Symbol | Side | Entry | Exit | PnL | Reason |")
        lines.append("|--------|------|-------|------|-----|--------|")
        for t in trades:
            lines.append(_trade_row(t))
    lines.append("")

    # Operational footer
    lines.append("## Operational")
    lines.append("- Breaker trips: see Telegram for detail (Step 5b will add count here)")
    lines.append("- Restarts: see Hetzner Docker logs (Step 5b will add count here)")
    lines.append("- Anomalies (alerter): see Telegram for per-event detail")
    if not heartbeat_stale and heartbeat_age_sec is not None:
        lines.append(f"- Alerter heartbeat: fresh ({heartbeat_age_sec}s old)")
    lines.append("")

    body = "\n".join(lines)
    return (subject, body)
```

- [ ] **Step 5.4: Run tests, expect PASS**

```powershell
python -m pytest tests/test_daily_render.py -v 2>&1 | Select-Object -Last 10
```

Expected: 4 tests pass.

- [ ] **Step 5.5: Commit**

```powershell
git add ops/daily_report/render.py tests/test_daily_render.py
git commit -m "feat(daily-report): render_email markdown body + ALERTER DOWN subject prefix"
```

---

## Main script + DB extension

### Task 6: Main report script + fetch_trades_since DB helper

**Files:**
- Modify: `backend/db.py` — add `fetch_trades_since` method
- Create: `ops/daily_report/report.py` — main entry, ties everything

The main script:
1. Reads SMTP env config + heartbeat path
2. Connects to DB via `Database.connect()`
3. Computes window: `now - 24h` to `now`
4. Calls `db.fetch_trades_since(since)` and `db.fetch_equity_history(days=2)` (filter to window)
5. Calls `compute_summary()`
6. Calls `check_alerter_heartbeat()`
7. Calls `render_email()`
8. Calls `send_email()`
9. Exits 0 on send success, 1 on failure (so cron wrapper triggers Telegram fallback)

No new test file in this task. Coverage comes from Task 9 E2E test.

- [ ] **Step 6.1: Add fetch_trades_since to backend/db.py**

Open `backend/db.py`. After `fetch_recent_trades` (~line 121), add:

```python
    async def fetch_trades_since(self, since_ts) -> list[dict[str, Any]]:
        """Fetch closed trades whose closed_at is >= since_ts.

        Args:
            since_ts: datetime (timezone-aware preferred).

        Returns: list of trade dicts (same shape as fetch_recent_trades).
        """
        if not self.pool:
            return []
        try:
            async with self.pool.acquire() as conn:
                rows = await conn.fetch(
                    """
                    SELECT id::text, symbol, direction, entry, exit, sl, tp1, tp2,
                           size, pnl_usdt, pnl_pct, reason, opened_at, closed_at,
                           confluence
                    FROM trades
                    WHERE closed_at IS NOT NULL AND closed_at >= $1
                    ORDER BY closed_at DESC
                    """,
                    since_ts,
                )
                return [dict(r) for r in rows]
        except Exception as e:
            log.warning(f"fetch_trades_since failed: {e}")
            return []
```

- [ ] **Step 6.2: Implement report.py main script**

Create `ops/daily_report/report.py`:

```python
"""Daily email report — main entry. Runs once and exits.

Cron-driven via Hetzner crontab: `docker compose run --rm daily-report`.

Reads SMTP + heartbeat config from env, queries Supabase for last-24h
trades + equity_history, composes markdown body, sends via SMTP.
Exits 0 on success, 1 on failure (cron wrapper pings Telegram on non-zero).

Run as: python -m ops.daily_report.report
"""
from __future__ import annotations

import asyncio
import logging
import os
import sys
from datetime import datetime, timedelta, timezone

logging.basicConfig(
    level=os.environ.get("LOG_LEVEL", "INFO"),
    format="%(asctime)s | %(name)-26s | %(levelname)-5s | %(message)s",
)
log = logging.getLogger("efloud.daily_report")

# Configurable env (defaults match docker-compose.prod.yml)
SMTP_HOST = os.environ.get("EFLOUD_SMTP_HOST", "smtp.gmail.com")
SMTP_PORT = int(os.environ.get("EFLOUD_SMTP_PORT", "587"))
SMTP_USERNAME = os.environ.get("EFLOUD_SMTP_USERNAME", "")
SMTP_PASSWORD = os.environ.get("EFLOUD_SMTP_PASSWORD", "")
SMTP_FROM = os.environ.get("EFLOUD_SMTP_FROM", SMTP_USERNAME)
SMTP_TO = os.environ.get("EFLOUD_SMTP_TO", "")
HEARTBEAT_FILE = os.environ.get(
    "EFLOUD_ALERTER_HEARTBEAT_FILE", "/app/state/alerter_heartbeat.json"
)


async def _run() -> int:
    """Async entry. Returns exit code."""
    log.info("daily report starting")
    if not SMTP_USERNAME or not SMTP_PASSWORD or not SMTP_TO:
        log.error("SMTP env not fully configured (EFLOUD_SMTP_USERNAME/PASSWORD/TO)")
        return 1

    # Local imports — keep top-of-module deps minimal so smoke import doesn't
    # require Database/asyncpg on the test box
    from backend.db import Database
    from ops.daily_report.aggregate import compute_summary
    from ops.daily_report.heartbeat import check_alerter_heartbeat
    from ops.daily_report.render import render_email
    from ops.daily_report.smtp_client import send_email

    # 24h window ending now
    now_utc = datetime.now(timezone.utc)
    since_utc = now_utc - timedelta(hours=24)
    report_date = now_utc.date()

    # DB queries
    db = Database()
    await db.connect()
    if db.pool is None:
        log.error("DB pool init failed — cannot generate report")
        return 1
    try:
        trades = await db.fetch_trades_since(since_utc)
        equity_history = await db.fetch_equity_history(days=2)  # filter below
        # Filter equity_history to last 24h window
        equity_history = [
            e for e in equity_history if e["ts"] >= since_utc
        ]
        log.info(f"fetched {len(trades)} trades + {len(equity_history)} equity points")
    finally:
        await db.close()

    # Heartbeat check
    stale, age = check_alerter_heartbeat(HEARTBEAT_FILE)
    if stale:
        log.warning(f"alerter heartbeat stale (age={age}s) — adding ALERTER DOWN prefix")

    # Aggregate + render
    summary = compute_summary(trades=trades, equity_history=equity_history)
    subject, body = render_email(
        summary=summary, trades=trades,
        heartbeat_stale=stale, heartbeat_age_sec=age,
        report_date=report_date,
    )

    # Send
    ok = send_email(
        host=SMTP_HOST, port=SMTP_PORT,
        username=SMTP_USERNAME, password=SMTP_PASSWORD,
        from_addr=SMTP_FROM, to_addr=SMTP_TO,
        subject=subject, body=body,
    )
    if ok:
        log.info(f"daily report sent: {subject!r}")
        return 0
    log.error("daily report send FAILED")
    return 1


def main() -> int:
    return asyncio.run(_run())


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 6.3: Smoke import the module**

```powershell
python -c "from ops.daily_report.report import main; print('OK')"
```

Expected: prints `OK`. If the import fails (typo, missing dep), fix before continuing.

- [ ] **Step 6.4: Run full suite for regression**

```powershell
python -m pytest tests/ -q 2>&1 | Select-Object -Last 5
```

Expected: baseline + 14 pass (no new tests in this task; backend/db.py change shouldn't break Step 1's db tests).

- [ ] **Step 6.5: Commit**

```powershell
git add backend/db.py ops/daily_report/report.py
git commit -m "feat(daily-report): main script (DB → aggregate → render → SMTP) + db.fetch_trades_since"
```

---

## Deploy

### Task 7: docker-compose service + crontab runbook

**Files:**
- Modify: `docker-compose.prod.yml` — add `daily-report` service
- Create: `docs/runbooks/daily-report-cron-setup.md`

The service has `profiles: [scheduled]` so it does NOT auto-start with `up -d`. Cron triggers it via `docker compose run --rm`.

- [ ] **Step 7.1: Read current docker-compose.prod.yml**

```powershell
Get-Content docker-compose.prod.yml
```

Confirm shape (efloud-bot, caddy, autoheal, alerter from Steps 1-4). The daily-report block goes after alerter.

- [ ] **Step 7.2: Add daily-report service block**

Add to `docker-compose.prod.yml` after the `alerter:` block:

```yaml
  daily-report:
    image: efloud-bot:latest          # reuse the bot's image (same as alerter)
    container_name: efloud-daily-report
    profiles: [scheduled]             # NOT started by `up -d`; cron triggers via `run`
    command: python -m ops.daily_report.report
    env_file:
      - .env.production
    environment:
      - EFLOUD_ALERTER_HEARTBEAT_FILE=/app/state/alerter_heartbeat.json
    volumes:
      - efloud_state:/app/state:ro    # read-only — only reads heartbeat file
    # No restart policy: this service runs once and exits.
    # No depends_on: it can run independently of bot/alerter (its only DB dep is Supabase).
    logging:
      driver: json-file
      options:
        max-size: "2m"
        max-file: "3"
```

`profiles: [scheduled]` is the key: `docker compose up -d` ignores it, but `docker compose run --rm daily-report` runs it on demand.

- [ ] **Step 7.3: Validate (skip if docker not installed locally)**

```powershell
docker compose -f docker-compose.prod.yml config 2>&1 | Select-Object -First 30
```

If docker not installed locally, SKIP — Hetzner-side will validate during deploy.

- [ ] **Step 7.4: Run full suite for regression (no test changes in this task)**

```powershell
python -m pytest tests/ -q 2>&1 | Select-Object -Last 5
```

Expected: baseline + 14 pass unchanged.

- [ ] **Step 7.5: Commit**

```powershell
git add docker-compose.prod.yml
git commit -m "feat(deploy): daily-report service (profiles=scheduled, on-demand only)"
```

---

### Task 8: Crontab runbook

**Files:**
- Create: `docs/runbooks/daily-report-cron-setup.md`

The cron entry + failure-to-send wrapper goes on the Hetzner host's crontab, NOT in any container or compose file. Runbook documents the one-time install procedure for the operator.

- [ ] **Step 8.1: Create the runbook**

Create `docs/runbooks/daily-report-cron-setup.md`:

```markdown
# Daily Report Cron — One-Time Hetzner Setup

This runbook installs the 08:00 UTC daily-report cron entry on Hetzner.

## Prerequisites

- Step 5 deployed: `docker-compose.prod.yml` has the `daily-report` service.
- `.env.production` has SMTP credentials:
  - `EFLOUD_SMTP_HOST` (default `smtp.gmail.com`)
  - `EFLOUD_SMTP_PORT` (default `587`)
  - `EFLOUD_SMTP_USERNAME` (e.g. `bot@yourdomain.com`)
  - `EFLOUD_SMTP_PASSWORD` (Gmail app password — see below)
  - `EFLOUD_SMTP_FROM` (default = USERNAME)
  - `EFLOUD_SMTP_TO` (operator's email)
- `EFLOUD_TELEGRAM_TOKEN` and `EFLOUD_TELEGRAM_CHAT_ID` already in env (Step 4).

## Gmail app password setup (one-time)

If using Gmail SMTP:
1. Sign in to the Gmail account that will SEND the report.
2. Visit https://myaccount.google.com/apppasswords (requires 2FA enabled).
3. Generate an app password named `efloud-bot daily-report`.
4. Copy the 16-character password into `.env.production` as `EFLOUD_SMTP_PASSWORD`.
5. Set `EFLOUD_SMTP_USERNAME` to the Gmail address.

## Manual smoke test (BEFORE adding cron)

Before automating, verify the report sends correctly when invoked manually:

\`\`\`bash
ssh efloud@178.104.122.91
cd /opt/efloud-bot
docker compose -f docker-compose.prod.yml --profile scheduled run --rm daily-report
\`\`\`

Expected: command exits 0, you receive an email at `EFLOUD_SMTP_TO` within ~30s.
If exit code is non-zero, check the container's stderr for the failure reason
(SMTP auth, DB connection, missing env var, etc.) before proceeding.

## Install crontab entry

Edit the `efloud` user's crontab:

\`\`\`bash
ssh efloud@178.104.122.91
crontab -e
\`\`\`

Add this line (single line in the file — no line breaks):

\`\`\`
0 8 * * * cd /opt/efloud-bot && (docker compose -f docker-compose.prod.yml --profile scheduled run --rm daily-report >> /var/log/efloud-daily-report.log 2>&1 || (TS=$(date -u +%Y-%m-%dT%H:%M:%SZ); echo "[$TS] daily-report FAILED" >> /var/log/efloud-cron-errors.log; source /opt/efloud-bot/.env.production; curl -s "https://api.telegram.org/bot${EFLOUD_TELEGRAM_TOKEN}/sendMessage" --data-urlencode "chat_id=${EFLOUD_TELEGRAM_CHAT_ID}" --data-urlencode "text=⚠️ daily-report cron FAILED at $TS — check /var/log/efloud-cron-errors.log on Hetzner" >> /var/log/efloud-cron-errors.log 2>&1))
\`\`\`

What this does:
1. At 08:00 UTC daily, run the daily-report container.
2. Log stdout+stderr to `/var/log/efloud-daily-report.log`.
3. If exit code is non-zero, append to `/var/log/efloud-cron-errors.log` AND ping Telegram with a WARNING message.

## Verify cron is active

\`\`\`bash
crontab -l | grep daily-report
\`\`\`

You should see the line above. The next 08:00 UTC run will fire automatically.

## Disable cron in an emergency

\`\`\`bash
crontab -e
\`\`\`

Delete the daily-report line (or comment it out with `#` at start). Save and exit.

## Logs to inspect after first run

- `/var/log/efloud-daily-report.log` — stdout/stderr of the most recent run
- `/var/log/efloud-cron-errors.log` — failure log; should be empty in healthy state
- Recipient inbox at `EFLOUD_SMTP_TO` — actual email

## Troubleshooting

**Email never arrives, no error in logs:**
- Check Gmail's "Sent" folder on the sending account
- Check recipient's spam folder
- Verify `EFLOUD_SMTP_TO` is correct (typo)

**SMTPAuthenticationError in log:**
- Re-generate Gmail app password (the existing one may have been revoked)
- Verify 2FA is still enabled on the sending account

**"DB pool init failed" in log:**
- Check Supabase pooler is reachable: `curl -s aws-1-eu-central-1.pooler.supabase.com:6543` (should connect)
- Check `DATABASE_URL` in `.env.production` is correct
```

- [ ] **Step 8.2: Commit**

```powershell
git add docs/runbooks/daily-report-cron-setup.md
git commit -m "docs(runbooks): daily-report cron + Gmail SMTP setup procedure"
```

---

## Verification

### Task 9: End-to-end integration test

**Files:**
- Test: `tests/test_daily_e2e.py` (1 test, ~80 lines)

Walks the full pipeline: synthetic trades + equity_history + heartbeat → render → mocked SMTP. Verifies subject + body content. Does NOT spin up real DB or SMTP.

- [ ] **Step 9.1: Write E2E test**

Create `tests/test_daily_e2e.py`:

```python
"""End-to-end: aggregate + render + send_email pipeline with mocked I/O.

No real DB / SMTP. Verifies the full data flow produces a sensible email.
"""
from __future__ import annotations

import json
import time
from datetime import date, datetime, timezone
from pathlib import Path
from unittest import mock


def test_full_report_cycle_with_mocked_db_and_smtp(tmp_path: Path):
    """End-to-end: stub DB → aggregate → render → mock SMTP send."""
    from ops.daily_report.aggregate import compute_summary
    from ops.daily_report.heartbeat import check_alerter_heartbeat
    from ops.daily_report.render import render_email
    from ops.daily_report.smtp_client import send_email

    # Synthetic trade rows (3 trades, mixed)
    trades = [
        {
            "symbol": "BTC/USDT", "direction": "LONG",
            "entry": 50000.0, "exit": 51000.0, "size": 0.001,
            "pnl_usdt": 10.0, "pnl_pct": 2.0, "reason": "TP2",
            "opened_at": datetime(2026, 5, 7, 10, 0, tzinfo=timezone.utc),
            "closed_at": datetime(2026, 5, 7, 14, 0, tzinfo=timezone.utc),
            "confluence": 80,
        },
        {
            "symbol": "ETH/USDT", "direction": "SHORT",
            "entry": 3000.0, "exit": 3050.0, "size": 0.01,
            "pnl_usdt": -5.0, "pnl_pct": -1.67, "reason": "SL",
            "opened_at": datetime(2026, 5, 7, 11, 0, tzinfo=timezone.utc),
            "closed_at": datetime(2026, 5, 7, 16, 0, tzinfo=timezone.utc),
            "confluence": 80,
        },
        {
            "symbol": "XRP/USDT", "direction": "LONG",
            "entry": 0.5, "exit": 0.51, "size": 100.0,
            "pnl_usdt": 1.0, "pnl_pct": 2.0, "reason": "TP1",
            "opened_at": datetime(2026, 5, 7, 12, 0, tzinfo=timezone.utc),
            "closed_at": datetime(2026, 5, 7, 15, 0, tzinfo=timezone.utc),
            "confluence": 85,
        },
    ]
    equity_history = [
        {"ts": datetime(2026, 5, 7, 8, 0, tzinfo=timezone.utc),
         "balance": 2000.0, "open_positions_count": 0},
        {"ts": datetime(2026, 5, 8, 8, 0, tzinfo=timezone.utc),
         "balance": 2006.0, "open_positions_count": 0},
    ]

    # Fresh heartbeat
    hb_path = tmp_path / "alerter_heartbeat.json"
    hb_path.write_text(json.dumps({"alerter_heartbeat_ts": int(time.time())}))

    # Pipeline
    summary = compute_summary(trades=trades, equity_history=equity_history)
    stale, age = check_alerter_heartbeat(str(hb_path))
    subject, body = render_email(
        summary=summary, trades=trades,
        heartbeat_stale=stale, heartbeat_age_sec=age,
        report_date=date(2026, 5, 8),
    )

    # Subject sanity
    assert "2026-05-08" in subject
    assert "ALERTER DOWN" not in subject  # heartbeat is fresh
    # Body sanity
    assert "BTC/USDT" in body
    assert "ETH/USDT" in body
    assert "XRP/USDT" in body
    assert "win rate" in body.lower() or "wins" in body.lower()
    assert "2000" in body or "2006" in body  # equity numbers somewhere

    # Send via mock SMTP
    with mock.patch("ops.daily_report.smtp_client.smtplib.SMTP") as smtp_cls:
        smtp_inst = smtp_cls.return_value.__enter__.return_value
        ok = send_email(
            host="smtp.example.com", port=587,
            username="bot@example.com", password="x",
            from_addr="bot@example.com", to_addr="ops@example.com",
            subject=subject, body=body,
        )
    assert ok is True
    # Verify EmailMessage was passed to send_message
    sent_msg = smtp_inst.send_message.call_args[0][0]
    assert sent_msg["Subject"] == subject
    # Body is the EmailMessage payload
    assert "BTC/USDT" in sent_msg.get_content()
```

- [ ] **Step 9.2: Run E2E test**

```powershell
python -m pytest tests/test_daily_e2e.py -v 2>&1 | Select-Object -Last 10
```

Expected: 1 test passes.

- [ ] **Step 9.3: Run full suite**

```powershell
python -m pytest tests/ -q 2>&1 | Select-Object -Last 5
```

Expected: baseline + **15** pass (FINAL TARGET — Task 9 completes the budget).

- [ ] **Step 9.4: Commit**

```powershell
git add tests/test_daily_e2e.py
git commit -m "test(daily-report): e2e — synthetic trades → aggregate → render → mock SMTP"
```

---

### Task 10: Final verification + push

**Files:** none modified (verification only).

- [ ] **Step 10.1: Full test suite final check**

```powershell
python -m pytest tests/ -q 2>&1 | Select-Object -Last 5
```

Expected: baseline + 15 new pass. Specifically:
- Task 2: 5 aggregate tests
- Task 3: 3 heartbeat tests
- Task 4: 2 SMTP tests
- Task 5: 4 render tests
- Task 9: 1 E2E test

Sum: 5+3+2+4+1 = 15.

- [ ] **Step 10.2: Smoke import all modules**

```powershell
python -c "from ops.daily_report.report import main; from ops.daily_report.aggregate import compute_summary; from ops.daily_report.heartbeat import check_alerter_heartbeat; from ops.daily_report.smtp_client import send_email; from ops.daily_report.render import render_email; print('all imports OK')"
```

Expected: prints `all imports OK`.

- [ ] **Step 10.3: Code review checklist (manual)**

- `aggregate.py`: pure function (no I/O), handles empty/None inputs gracefully
- `heartbeat.py`: returns sensible (True, None) when file missing/corrupt; never raises
- `smtp_client.py`: returns False on any error; STARTTLS used; never logs the password
- `render.py`: subject is ASCII-safe (no em-dash); ALERTER DOWN prefix only when stale
- `report.py`: env config validated upfront; DB pool closed on exit; exit code 0/1 per success
- `docker-compose.prod.yml`: `profiles: [scheduled]` set so default `up -d` does NOT start the service
- Runbook: cron line is one continuous line (no breaks); Telegram fallback uses `--data-urlencode` to handle special chars in the message

- [ ] **Step 10.4: Push branch (defer tag until merge)**

```powershell
git push origin feature/asama-2-step-5-daily-report
```

- [ ] **Step 10.5: Final report to owner**

Output:
- Branch: `feature/asama-2-step-5-daily-report`
- Commits: ~9 (Task 1 + Tasks 2-9)
- Tests added: 15
- New env vars (operator must add to `.env.production` BEFORE first cron run):
  - `EFLOUD_SMTP_HOST` (default `smtp.gmail.com`)
  - `EFLOUD_SMTP_PORT` (default `587`)
  - `EFLOUD_SMTP_USERNAME=<gmail-address>`
  - `EFLOUD_SMTP_PASSWORD=<gmail-app-password>` (NOT regular Gmail password)
  - `EFLOUD_SMTP_FROM` (default = USERNAME)
  - `EFLOUD_SMTP_TO=<operator-email>`
- New persistent files: none (state/runtime.json + state/alerter_heartbeat.json from Step 4 are reused)
- Rollback: revert branch + delete crontab line; existing Steps 1-4 untouched
- **Production deploy notes:**
  1. Operator: generate Gmail app password (see runbook §"Gmail app password setup")
  2. Add 6 SMTP env vars to `.env.production` on Hetzner
  3. Merge to master + push
  4. SSH to Hetzner: `cd /opt/efloud-bot && git pull origin master`
  5. Rebuild image: `docker compose -f docker-compose.prod.yml build efloud-bot` (daily-report reuses it)
  6. Manual smoke: `docker compose -f docker-compose.prod.yml --profile scheduled run --rm daily-report` — verify exit 0 + email arrived
  7. Install crontab line per `docs/runbooks/daily-report-cron-setup.md`
  8. (Optional) Wait for next 08:00 UTC to fire automatically; check `/var/log/efloud-daily-report.log` afterward

---

## What this plan does NOT cover

Per spec §11, deferred to follow-up plans:

- **Step 5b** (follow-up): breaker trips count, restart count, anomalies count in the email body — requires either a `breaker_events` DB table OR scanning logs OR querying alerter's SQLite dedup
- **Step 6**: Log rotation tuning (custom `GzipRotatingFileHandler`)

---

## Rollback (if anything goes bad)

1. **Revert the branch:** `git revert <merge-commit>` on master, redeploy. `docker-compose.prod.yml` loses the daily-report service; existing Steps 1-4 untouched. No data risk.
2. **Disable cron only:** `crontab -e` and delete/comment the line. Code stays deployed but no automated runs.
3. **Manual run anytime:** `docker compose -f docker-compose.prod.yml --profile scheduled run --rm daily-report` — sends a one-off email.

---

## Acceptance for Step 5

Step 5 is **DONE** when:
- All Task 0-10 checkboxes ticked
- All tests pass (count = baseline + exactly 15 new)
- Smoke import succeeds
- `docker compose config` validates
- Runbook exists at `docs/runbooks/daily-report-cron-setup.md`
- Branch pushed
- Owner has Gmail app password in `.env.production` ready
- Manual smoke run sends a real email to `EFLOUD_SMTP_TO`
- Owner reviews + approves before promoting to master and Hetzner

After acceptance → write Step 6 plan (log rotation).
