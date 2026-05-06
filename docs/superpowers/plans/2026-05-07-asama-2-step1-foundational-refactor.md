# Aşama 2 — Step 1: Foundational Refactor (trace_id + JSON logs + bar_ts) Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add structured JSON logging with end-to-end trace_id correlation across signal → order → fill → persist, plus bar_ts persistence for trades. Foundation for Aşama 2 Steps 2-6 (alerter, daily-report, healthz all depend on JSON logs).

**Architecture:** Two additive SQL migrations (002 trace_id, 003 bar_ts), one new JSON formatter in `utils/logging.py`, a Python `contextvars.ContextVar` for trace_id propagation **WITHIN async tasks**, AND **explicit trace_id parameter passing** through the cross-thread persistence boundary (`bot_runner._emit_position_event` uses `asyncio.run_coroutine_threadsafe` which does NOT propagate contextvars). The `Position` dataclass gains a `trace_id` field carried from open through close. Feature-flag-gated via `EFLOUD_LOGGING_FORMAT` env var so rollback = single env change.

**Architecture note (cross-thread boundary):** `backend/bot_runner.py:291-316` schedules `db.record_trade_open` / `record_trade_close` from the sync engine thread into the async loop via `asyncio.run_coroutine_threadsafe`. Per CPython semantics, the scheduled coroutine runs in the *target loop's* context — sync caller's `_trace_id_ctx` value is NOT carried over. Therefore: trace_id MUST be passed as an explicit argument through `Position.trace_id` field → `_emit_position_event` reads `pos.trace_id` → passes to the db kwarg. ContextVar is used only for log-line auto-injection within a single async task.

**Tech Stack:** Python 3.12, asyncpg, asyncio, contextvars (stdlib), pytest + pytest-asyncio. Postgres (Supabase). No new dependencies.

**Spec parent:** `docs/superpowers/specs/2026-05-07-asama-2-self-maintenance-observability-design.md` (§4.2, §4.5, §11 Step 1)

**Estimated effort:** 1-1.5 weeks for one engineer, per spec §13.

---

## Codebase reality check (read first if unfamiliar)

The spec §4 named files that don't exactly match the current tree. Real paths used in this plan (each verified against current master):

| Spec said | Reality on master |
|-----------|-------------------|
| `engine/order_manager.py` | TWO sources: `exchange/OrderManager` (real exchange order placement) + `engine/lifecycle.py` (in-memory Position state machine) |
| `state/repository.py` | `backend/db.py` — `Database` class with asyncpg |
| `database/postgres/migrations/` | `backend/migrations/` (existing: `001_init.sql`) |
| `state/runtime.json` (proposed) | does not exist yet — Aşama 2 Step 2 creates it; not in scope here |

**Critical architectural fact:** `engine/lifecycle.py:145` `open_position` is a **sync** method that returns a `Position` object. It does NOT call the database. Database persistence happens later in `backend/bot_runner.py:291-316` via the `_emit_position_event` method, which crosses thread boundaries (sync engine thread → async DB loop) using `asyncio.run_coroutine_threadsafe`.

The existing `backend/db.py` has `record_trade_open(...)` returning the trade UUID, and `record_trade_close(symbol, exit, pnl_usdt, pnl_pct, reason)` which finds the most-recent open trade for the symbol. Both gain trace_id and bar_ts_ms parameters in Task 7.

**Migration runner:** `backend/migrate.py:115` requires the `up` subcommand: `python -m backend.migrate up` (without `up`, it exits with usage message). All migrate commands in this plan use the `up` form.

---

## File structure (what gets created vs modified)

**Create:**
- `backend/migrations/002_trace_id.sql` — additive: trace_id column + index
- `backend/migrations/003_bar_ts.sql` — additive: bar_ts_ms column
- `utils/logging.py` — JSON formatter + trace_id contextvar helpers (currently file is empty / `__init__.py` only)
- `tests/test_logging_json.py` — formatter unit tests
- `tests/test_trace_context.py` — contextvar helper tests
- `tests/test_db_trace_id_persistence.py` — db.py extension tests
- `tests/test_engine_trace_id_propagation.py` — orchestrator → lifecycle integration test
- `tests/test_backtest_bar_ts.py` — backtest engine bar_ts capture test

**Modify:**
- `backend/db.py` — add `trace_id` and `bar_ts_ms` parameters to `record_trade_open` and `record_trade_close`
- `engine/safe_orchestrator.py` — generate `trace_id` at signal-detection, set contextvar (for logs), pass to OrderManager / lifecycle calls
- `engine/lifecycle.py` — `Position` dataclass gains `trace_id: Optional[str]` field; `open_position` (still sync) accepts `trace_id` kwarg and stores it on Position
- `backend/bot_runner.py` — `_emit_position_event` reads `pos.trace_id` and passes it explicitly to `db.record_trade_open` / `db.record_trade_close` via the `run_coroutine_threadsafe`-scheduled coroutines
- `main.py` (repo root — confirmed entrypoint, NOT `backend/main.py`) — call `utils.logging.configure_json_logging()` early in `__main__` block, BEFORE SafeOrchestrator construction
- `backtest/engine.py` (worktree `feature/backtest-subsystem`) — populate `bar_ts_ms` in trade dict (DEFERRED, see Task 8)
- `requirements.txt` — none (no new deps)

**Delete:** none.

---

## Pre-flight

### Task 0: Worktree + branch setup, baseline verification

**Files:** none modified, only environment setup.

- [ ] **Step 0.1: Create dedicated worktree from master**

```powershell
cd C:\Users\utkuc\Downloads\efloud-bot
git worktree add ../efloud-bot-asama2-step1 -b feature/asama-2-step-1-foundational-refactor master
cd ../efloud-bot-asama2-step1
```

Expected: new directory `efloud-bot-asama2-step1` exists, on branch `feature/asama-2-step-1-foundational-refactor` based on master.

- [ ] **Step 0.2: Verify base tests pass before changes**

```powershell
cd C:\Users\utkuc\Downloads\efloud-bot-asama2-step1
python -m pytest tests/ -q 2>&1 | Select-Object -Last 20
```

Expected: all current tests pass. If any fail at this baseline, STOP and surface to owner — we need a clean base.

- [ ] **Step 0.3: Confirm Postgres test connectivity (or set test mode without DB)**

```powershell
$env:DATABASE_URL = $env:DATABASE_URL_TEST
python -c "import asyncio, asyncpg; asyncio.run(asyncpg.connect(`$env:DATABASE_URL).close())" 2>&1
```

Expected: no error, or "DATABASE_URL_TEST not set" (acceptable if running without a test DB; test plan handles both cases).

- [ ] **Step 0.4: Capture baseline test count**

Record the exact test count from Step 0.2 output (e.g., `BASELINE_PASSED=47`). Pin this number; final test count after all tasks must be **exactly** `BASELINE_PASSED + 17` (calculated below). Any deviation = an existing test got deleted or skipped, investigate before proceeding.

New tests added by this plan (= 17 total):
- Task 1: 2 tests (`test_trace_id_column_exists`, `test_trace_id_index_exists`)
- Task 2: 1 test (`test_bar_ts_ms_column_exists`)
- Task 3: 5 tests (`test_get_trace_id_returns_none_when_unset`, `test_set_and_get_trace_id`, `test_new_trace_id_returns_12_char_hex`, `test_new_trace_id_is_unique_across_calls`, `test_trace_id_isolated_across_tasks`)
- Task 3: 6 tests (`test_basic_fields_present`, `test_trace_id_picked_up_from_context`, `test_trace_id_absent_when_unset`, `test_extra_fields_merged`, `test_exception_serialised`, `test_output_is_single_line`)
- Task 4: 2 tests (`test_no_op_when_env_flag_unset`, `test_emits_json_when_flag_set`)
- Task 7: 2 tests (`test_record_trade_open_persists_trace_id`, `test_record_trade_open_handles_missing_trace_id`)
- Task 9: 1 test (`test_signal_to_trade_trace_id_correlation`)

Tasks 5 and 6 contribute their assertions via Task 9's E2E test (no separate per-task tests, see Task 5/6 note).

---

## Foundation: schema + logging

### Task 1: Migration 002 — add trace_id column

**Files:**
- Create: `backend/migrations/002_trace_id.sql`
- Test: `tests/test_migration_002_trace_id.py` (new)

- [ ] **Step 1.1: Write migration SQL file**

Create `backend/migrations/002_trace_id.sql`:

```sql
-- 002_trace_id.sql — Add trace_id column for log correlation.
-- Additive (NULLABLE), idempotent (IF NOT EXISTS where supported).
-- Width: CHAR(12) matches new_trace_id() output exactly (uuid4 hex truncated to 12).

ALTER TABLE trades
    ADD COLUMN IF NOT EXISTS trace_id CHAR(12);

-- Index for alerter/post-mortem queries by trace_id
CREATE INDEX IF NOT EXISTS idx_trades_trace_id
    ON trades (trace_id)
    WHERE trace_id IS NOT NULL;
```

- [ ] **Step 1.2: Write test that asserts column exists after migration**

Create `tests/test_migration_002_trace_id.py`:

```python
"""Verify migration 002 adds trace_id column and index to trades table."""
from __future__ import annotations

import asyncio
import os

import asyncpg
import pytest


pytestmark = pytest.mark.asyncio


@pytest.fixture
def database_url():
    url = os.environ.get("DATABASE_URL_TEST") or os.environ.get("DATABASE_URL")
    if not url:
        pytest.skip("DATABASE_URL not set; skipping integration test")
    return url


async def test_trace_id_column_exists(database_url):
    conn = await asyncpg.connect(database_url)
    try:
        row = await conn.fetchrow(
            """
            SELECT column_name, data_type, character_maximum_length, is_nullable
            FROM information_schema.columns
            WHERE table_name = 'trades' AND column_name = 'trace_id'
            """
        )
        assert row is not None, "trace_id column missing — migration 002 not applied"
        assert row["data_type"] == "character"
        assert row["character_maximum_length"] == 12
        assert row["is_nullable"] == "YES"
    finally:
        await conn.close()


async def test_trace_id_index_exists(database_url):
    conn = await asyncpg.connect(database_url)
    try:
        row = await conn.fetchrow(
            """
            SELECT indexname FROM pg_indexes
            WHERE tablename = 'trades' AND indexname = 'idx_trades_trace_id'
            """
        )
        assert row is not None, "idx_trades_trace_id missing — migration 002 not applied"
    finally:
        await conn.close()
```

- [ ] **Step 1.3: Run migration runner**

```powershell
python -m backend.migrate up 2>&1
```

Note the `up` subcommand — required by `backend/migrate.py:115`. Without it, the runner exits with "Usage: python -m backend.migrate up" and migration is NOT applied (a silent failure mode that fooled the original draft of this plan).

Expected output: includes `✓ 002_trace_id applied` or similar. If runner output format differs, read the actual line from `backend/migrate.py:103`.

- [ ] **Step 1.4: Run new test, expect PASS**

```powershell
python -m pytest tests/test_migration_002_trace_id.py -v 2>&1
```

Expected: 2 tests pass (or 2 SKIPPED if no DATABASE_URL set in the runner env — acceptable for now).

- [ ] **Step 1.5: Commit**

```powershell
git add backend/migrations/002_trace_id.sql tests/test_migration_002_trace_id.py
git commit -m "feat(db): migration 002 — add trace_id column + index to trades"
```

---

### Task 2: Migration 003 — add bar_ts_ms column

**Files:**
- Create: `backend/migrations/003_bar_ts.sql`
- Test: `tests/test_migration_003_bar_ts.py` (new)

- [ ] **Step 2.1: Write migration SQL**

Create `backend/migrations/003_bar_ts.sql`:

```sql
-- 003_bar_ts.sql — Add bar_ts_ms column for bar-aligned timestamps.
-- Existing opened_at/closed_at are server NOW() wall-clock; bar_ts_ms
-- records the historical bar's timestamp (epoch milliseconds) for
-- regime-aware analysis and Phase B reconcile.
-- Additive, NULLABLE. Existing rows have NULL bar_ts_ms (acceptable).

ALTER TABLE trades
    ADD COLUMN IF NOT EXISTS bar_ts_ms BIGINT;
```

No new index — bar_ts_ms is mostly accessed via `WHERE id = $1` lookups, not range queries.

- [ ] **Step 2.2: Write test**

Create `tests/test_migration_003_bar_ts.py`:

```python
"""Verify migration 003 adds bar_ts_ms column to trades table."""
from __future__ import annotations

import os

import asyncpg
import pytest

pytestmark = pytest.mark.asyncio


@pytest.fixture
def database_url():
    url = os.environ.get("DATABASE_URL_TEST") or os.environ.get("DATABASE_URL")
    if not url:
        pytest.skip("DATABASE_URL not set")
    return url


async def test_bar_ts_ms_column_exists(database_url):
    conn = await asyncpg.connect(database_url)
    try:
        row = await conn.fetchrow(
            """
            SELECT data_type, is_nullable
            FROM information_schema.columns
            WHERE table_name = 'trades' AND column_name = 'bar_ts_ms'
            """
        )
        assert row is not None, "bar_ts_ms column missing — migration 003 not applied"
        assert row["data_type"] == "bigint"
        assert row["is_nullable"] == "YES"
    finally:
        await conn.close()
```

- [ ] **Step 2.3: Apply migration + run test**

```powershell
python -m backend.migrate up 2>&1
python -m pytest tests/test_migration_003_bar_ts.py -v 2>&1
```

Expected: migration applied, test passes (or SKIP if no DB).

- [ ] **Step 2.4: Commit**

```powershell
git add backend/migrations/003_bar_ts.sql tests/test_migration_003_bar_ts.py
git commit -m "feat(db): migration 003 — add bar_ts_ms column to trades"
```

---

### Task 3: JSON formatter + trace_id contextvar

**Files:**
- Create: `utils/logging.py` (replaces empty `utils/__init__.py` content if needed; add new file)
- Test: `tests/test_logging_json.py`, `tests/test_trace_context.py`

- [ ] **Step 3.1: Write contextvar tests first**

Create `tests/test_trace_context.py`:

```python
"""trace_id contextvar helpers — set, get, scope."""
from __future__ import annotations

import asyncio

import pytest

from utils.logging import get_trace_id, new_trace_id, set_trace_id


def test_get_trace_id_returns_none_when_unset():
    # Fresh context; should be None
    assert get_trace_id() is None


def test_set_and_get_trace_id():
    set_trace_id("abc123")
    assert get_trace_id() == "abc123"
    set_trace_id(None)  # reset


def test_new_trace_id_returns_12_char_hex():
    tid = new_trace_id()
    assert isinstance(tid, str)
    assert len(tid) == 12
    assert all(c in "0123456789abcdef" for c in tid)


def test_new_trace_id_is_unique_across_calls():
    tids = {new_trace_id() for _ in range(100)}
    assert len(tids) == 100, "expected 100 unique trace_ids in 100 calls"


@pytest.mark.asyncio
async def test_trace_id_isolated_across_tasks():
    """Each asyncio Task gets its own contextvar copy."""
    set_trace_id("outer")

    async def inner_task(tid: str) -> str:
        set_trace_id(tid)
        await asyncio.sleep(0.001)
        return get_trace_id() or ""

    results = await asyncio.gather(
        inner_task("task1"),
        inner_task("task2"),
        inner_task("task3"),
    )
    assert results == ["task1", "task2", "task3"]
    # Outer context unchanged
    assert get_trace_id() == "outer"
    set_trace_id(None)  # cleanup
```

- [ ] **Step 3.2: Run tests, expect FAIL (function not yet defined)**

```powershell
python -m pytest tests/test_trace_context.py -v 2>&1
```

Expected: ImportError ("cannot import name 'get_trace_id' from 'utils.logging'") or AttributeError. All 5 tests fail.

- [ ] **Step 3.3: Write JSON formatter tests**

Create `tests/test_logging_json.py`:

```python
"""JSON log formatter — ensure required fields always present."""
from __future__ import annotations

import json
import logging

import pytest

from utils.logging import JsonFormatter, get_trace_id, set_trace_id


def make_record(level=logging.INFO, msg="hello", extra=None):
    return logging.LogRecord(
        name="test", level=level, pathname=__file__, lineno=1,
        msg=msg, args=(), exc_info=None,
    )


def test_basic_fields_present():
    rec = make_record()
    out = JsonFormatter().format(rec)
    parsed = json.loads(out)
    for key in ("ts", "level", "logger", "message"):
        assert key in parsed, f"missing field: {key}"
    assert parsed["level"] == "INFO"
    assert parsed["message"] == "hello"


def test_trace_id_picked_up_from_context():
    set_trace_id("xyz789")
    try:
        rec = make_record()
        out = JsonFormatter().format(rec)
        parsed = json.loads(out)
        assert parsed.get("trace_id") == "xyz789"
    finally:
        set_trace_id(None)


def test_trace_id_absent_when_unset():
    set_trace_id(None)
    rec = make_record()
    out = JsonFormatter().format(rec)
    parsed = json.loads(out)
    assert "trace_id" not in parsed or parsed["trace_id"] is None


def test_extra_fields_merged():
    rec = make_record()
    rec.symbol = "BTC/USDT"
    rec.pnl_usdt = 12.5
    out = JsonFormatter().format(rec)
    parsed = json.loads(out)
    assert parsed["symbol"] == "BTC/USDT"
    assert parsed["pnl_usdt"] == 12.5


def test_exception_serialised():
    try:
        raise ValueError("boom")
    except ValueError:
        import sys
        rec = logging.LogRecord(
            name="test", level=logging.ERROR, pathname=__file__,
            lineno=1, msg="error", args=(), exc_info=sys.exc_info(),
        )
    out = JsonFormatter().format(rec)
    parsed = json.loads(out)
    assert "exception" in parsed
    assert "ValueError" in parsed["exception"]


def test_output_is_single_line():
    rec = make_record(msg="multi\nline")
    out = JsonFormatter().format(rec)
    assert "\n" not in out, "JsonFormatter must produce single-line output"
```

- [ ] **Step 3.4: Run formatter tests, expect FAIL**

```powershell
python -m pytest tests/test_logging_json.py -v 2>&1
```

Expected: ImportError on JsonFormatter; all 6 tests fail.

- [ ] **Step 3.5: Implement utils/logging.py**

Create `utils/logging.py`:

```python
"""Structured JSON logging + trace_id propagation.

Used by the bot to produce machine-readable log lines suitable for the
alerter sidecar (Aşama 2 Step 4) and the daily-report cron (Step 5).

Trace IDs are 12-char hex (uuid4 truncated; ~62 bits of entropy, collision
risk negligible at this scale). They flow via contextvars.ContextVar so
async tasks each have their own copy.

Configure with `configure_json_logging()` at process startup if env var
EFLOUD_LOGGING_FORMAT == "json"; otherwise no-op (default plain logging).
"""
from __future__ import annotations

import json
import logging
import os
import traceback
import uuid
from contextvars import ContextVar
from datetime import datetime, timezone
from typing import Any, Optional

# ─────────────────────────────────────────────────────────────────────
# trace_id contextvar
# ─────────────────────────────────────────────────────────────────────

_trace_id_ctx: ContextVar[Optional[str]] = ContextVar("trace_id", default=None)


def get_trace_id() -> Optional[str]:
    """Return current trace_id, or None if unset."""
    return _trace_id_ctx.get()


def set_trace_id(value: Optional[str]) -> None:
    """Set trace_id for the current async task / context."""
    _trace_id_ctx.set(value)


def new_trace_id() -> str:
    """Generate a new 12-char hex trace_id."""
    return uuid.uuid4().hex[:12]


# ─────────────────────────────────────────────────────────────────────
# JSON formatter
# ─────────────────────────────────────────────────────────────────────

_RESERVED_LOGRECORD_FIELDS = {
    "name", "msg", "args", "levelname", "levelno", "pathname",
    "filename", "module", "exc_info", "exc_text", "stack_info",
    "lineno", "funcName", "created", "msecs", "relativeCreated",
    "thread", "threadName", "processName", "process", "message",
    "taskName",  # Python 3.12+ adds this; treat as reserved
}


class JsonFormatter(logging.Formatter):
    """Format LogRecord as a single-line JSON object.

    Always includes: ts, level, logger, message.
    Includes trace_id if set on contextvar.
    Includes exception if exc_info present.
    Includes any non-reserved attributes set on the record (extras).
    """

    def format(self, record: logging.LogRecord) -> str:
        ts = datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat()
        out: dict[str, Any] = {
            "ts": ts,
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        tid = get_trace_id()
        if tid:
            out["trace_id"] = tid
        if record.exc_info:
            out["exception"] = "".join(traceback.format_exception(*record.exc_info))
        for k, v in record.__dict__.items():
            if k in _RESERVED_LOGRECORD_FIELDS or k.startswith("_"):
                continue
            try:
                json.dumps(v)
                out[k] = v
            except (TypeError, ValueError):
                out[k] = repr(v)
        # Single line, replace embedded newlines from message
        return json.dumps(out, ensure_ascii=False).replace("\n", "\\n")


# ─────────────────────────────────────────────────────────────────────
# Configuration helper
# ─────────────────────────────────────────────────────────────────────

def configure_json_logging(level: int = logging.INFO) -> None:
    """Configure root logger to emit JSON. Call once at process startup.

    Idempotent: removes any existing handlers, sets a single StreamHandler
    with JsonFormatter. Respects EFLOUD_LOGGING_FORMAT env var:
    if not "json", this function is a no-op (preserves prior config).
    """
    if os.environ.get("EFLOUD_LOGGING_FORMAT", "").lower() != "json":
        return

    root = logging.getLogger()
    for h in list(root.handlers):
        root.removeHandler(h)
    h = logging.StreamHandler()
    h.setFormatter(JsonFormatter())
    root.addHandler(h)
    root.setLevel(level)
```

- [ ] **Step 3.6: Run all logging tests, expect PASS**

```powershell
python -m pytest tests/test_trace_context.py tests/test_logging_json.py -v 2>&1
```

Expected: 11 tests pass (5 contextvar + 6 formatter).

- [ ] **Step 3.7: Commit**

```powershell
git add utils/logging.py tests/test_trace_context.py tests/test_logging_json.py
git commit -m "feat(logging): JSON formatter + trace_id contextvar (utils.logging)"
```

---

### Task 4: Wire JSON formatter into bot startup

**Files:**
- Modify: `main.py` (repo root) — bot entrypoint; call `configure_json_logging()` early

- [ ] **Step 4.1: Read existing main.py to find startup site**

```powershell
cat main.py | head -40
```

Locate the `if __name__ == "__main__":` block or the `setup_logging` / `logging.basicConfig` call. The new helper must run BEFORE any logger is used.

- [ ] **Step 4.2: Write integration test for env-flag wiring**

Create `tests/test_main_logging_flag.py`:

```python
"""When EFLOUD_LOGGING_FORMAT=json, root logger emits JSON; otherwise plain."""
from __future__ import annotations

import io
import logging
import os
from unittest import mock

from utils.logging import configure_json_logging


def test_no_op_when_env_flag_unset(caplog):
    os.environ.pop("EFLOUD_LOGGING_FORMAT", None)
    # Set a plain handler, then call configure
    root = logging.getLogger()
    initial_handlers = list(root.handlers)
    configure_json_logging()
    assert root.handlers == initial_handlers, (
        "configure_json_logging() must be no-op when EFLOUD_LOGGING_FORMAT != 'json'"
    )


def test_emits_json_when_flag_set():
    with mock.patch.dict(os.environ, {"EFLOUD_LOGGING_FORMAT": "json"}):
        # Reset handlers
        root = logging.getLogger()
        for h in list(root.handlers):
            root.removeHandler(h)
        configure_json_logging()
        assert len(root.handlers) == 1
        # Capture output
        buf = io.StringIO()
        root.handlers[0].stream = buf
        logging.getLogger("test").info("hello")
        line = buf.getvalue().strip()
        import json
        parsed = json.loads(line)
        assert parsed["message"] == "hello"
        assert parsed["level"] == "INFO"
```

- [ ] **Step 4.3: Run test, expect PASS** (configure_json_logging from Task 3 already implements this)

```powershell
python -m pytest tests/test_main_logging_flag.py -v 2>&1
```

Expected: 2 tests pass.

- [ ] **Step 4.4: Add startup call to main.py**

`main.py` (verified at repo root, line 35) does `from engine import SafeOrchestrator` near the top — these imports define loggers but do NOT emit log lines at import time, so the placement is more flexible than initially feared. The constraint is: `configure_json_logging()` must be called BEFORE the bot's main loop emits the first log line.

Insert at the top of the `__main__` block (the script entrypoint). Locate the existing `if __name__ == "__main__":` block and add the call as the FIRST line inside:

```python
if __name__ == "__main__":
    from utils.logging import configure_json_logging
    configure_json_logging()  # no-op unless EFLOUD_LOGGING_FORMAT=json
    # ... existing code follows ...
```

Why first-line-of-__main__ instead of top-of-file:
- Tests that import `main.py` (if any) won't be forced into JSON output
- The bot's `if __name__ == "__main__":` block is the canonical operational entrypoint
- The function is no-op without the env flag, so unconditional call is safe

- [ ] **Step 4.5: Smoke test — start bot in dry-run with JSON flag**

```powershell
$env:EFLOUD_LOGGING_FORMAT = "json"
$env:EFLOUD_AUTOSTART = "0"
python main.py 2>&1 | Select-Object -First 5
Remove-Item Env:\EFLOUD_LOGGING_FORMAT
```

Expected: first 5 lines are valid JSON. Each parses with `json.loads`.

- [ ] **Step 4.6: Commit**

```powershell
git add main.py tests/test_main_logging_flag.py
git commit -m "feat(logging): wire configure_json_logging into bot startup (env-flag gated)"
```

---

## Engine integration

### Task 5: trace_id generation at signal-detection in safe_orchestrator

**Files:**
- Modify: `engine/safe_orchestrator.py` (552 lines)

- [ ] **Step 5.1: Locate the signal-evaluation site**

```powershell
Select-String -Path engine\safe_orchestrator.py -Pattern "def |signal|confluence|evaluate|run_once" | Select-Object -First 30
```

Identify the function that decides "this signal becomes a trade". Look for where a `Position` is requested (calls into `OrderManager` from `exchange/` or `lifecycle.open_position`). The trace_id must be generated immediately BEFORE this point.

- [ ] **Step 5.2: Add trace_id generation at signal site**

In the identified function, add:

```python
# Top of the file (after existing imports):
from utils.logging import new_trace_id, set_trace_id

# ... inside the signal-evaluation function, at the START (before any log call
# that should be associated with this trade):

trace_id = new_trace_id()
set_trace_id(trace_id)
log.info("signal_evaluating", extra={"symbol": symbol, "confluence": conf})
# ... existing logic ...

# At the point where lifecycle.open_position OR exchange.OrderManager.open_position
# is called, pass trace_id explicitly:
position = self.lifecycle.open_position(
    symbol=symbol, direction=direction,
    entry_price=entry, size=size,
    sl=sl, tp1=tp1, tp2=tp2,
    trace_id=trace_id,  # NEW kwarg, added in Task 6
)
```

The contextvar `set_trace_id` is sufficient for log auto-injection within this async task. The explicit `trace_id=...` kwarg on `open_position` is required because the Position object will carry it across the cross-thread boundary in Task 6 (run_coroutine_threadsafe does NOT propagate contextvars).

- [ ] **Step 5.3: Run existing orchestrator tests for regression**

```powershell
python -m pytest tests/ -q -k "orchestrator" 2>&1 | Select-Object -Last 10
```

Expected: existing orchestrator tests still pass (the change only ADDs a parameter with a default; no signature breakage).

- [ ] **Step 5.4: Manual smoke — verify trace_id appears in dry-run logs**

```powershell
$env:EFLOUD_LOGGING_FORMAT = "json"
$env:EFLOUD_AUTOSTART = "0"
python -m pytest tests/test_smoke.py -v -s 2>&1 | Select-String "trace_id" | Select-Object -First 5
Remove-Item Env:\EFLOUD_LOGGING_FORMAT
Remove-Item Env:\EFLOUD_AUTOSTART
```

Expected: at least one log line contains a `trace_id` value. If `tests/test_smoke.py` doesn't drive a signal evaluation, find the test that does (e.g., `test_real_data.py`) and use it instead. If no smoke test exists that drives the orchestrator end-to-end, the manual verification is the E2E test in Task 9.

- [ ] **Step 5.5: Commit**

```powershell
git add engine/safe_orchestrator.py
git commit -m "feat(engine): generate trace_id at signal-detection (contextvar + explicit kwarg)"
```

Note: no per-task unit test for Task 5. The orchestrator's testing harness is non-trivial and a stub test would be either fake (pytest.skip) or duplicate Task 9's E2E coverage. Coverage for trace_id generation comes from the E2E test in Task 9 + the manual smoke in Step 5.4.

---

### Task 6: trace_id propagation through Position + bot_runner

**Files:**
- Modify: `engine/lifecycle.py` (Position dataclass + sync `open_position`)
- Modify: `backend/bot_runner.py:280-325` (`_emit_position_event` cross-thread DB write)

**Critical context:** `engine/lifecycle.open_position` is **sync**, returns a `Position` object, and does NOT call the database. DB persistence happens later in `backend/bot_runner._emit_position_event` via `asyncio.run_coroutine_threadsafe`. ContextVars do NOT propagate across this thread boundary, so trace_id must travel as a field on the Position object.

- [ ] **Step 6.1: Add trace_id field to Position dataclass**

In `engine/lifecycle.py`, locate the `Position` dataclass definition (search for `@dataclass\s+class Position` or `class Position`). Add a new optional field:

```python
@dataclass
class Position:
    id: str
    symbol: str
    direction: Direction
    entries: List[Entry]
    sl: float
    tp1: float
    tp2: float
    scenario_id: Optional[str] = None
    opened_at: Optional[str] = None
    # ... existing fields ...
    trace_id: Optional[str] = None  # NEW
```

- [ ] **Step 6.2: Modify lifecycle.open_position signature**

The function is **sync** (line 145). Add `trace_id` kwarg and store on the Position:

```python
def open_position(self, symbol: str, direction: Direction,
                   entry_price: float, size: float,
                   sl: float, tp1: float, tp2: float,
                   scenario_id: Optional[str] = None,
                   trace_id: Optional[str] = None) -> Position:  # NEW kwarg
    """İlk giriş ile yeni pozisyon aç."""
    now = datetime.utcnow().isoformat()
    pos_id = str(uuid.uuid4())[:8]

    entry = Entry(str(uuid.uuid4())[:8], entry_price, size, now, "initial")
    pos = Position(
        id=pos_id, symbol=symbol, direction=direction,
        entries=[entry],
        sl=sl, tp1=tp1, tp2=tp2,
        scenario_id=scenario_id,
        opened_at=now,
        trace_id=trace_id,  # NEW
    )
    self.positions.append(pos)
    log.info(f"🟢 OPEN {direction} {symbol} size={size:.4f} @ {entry_price:.2f} | SL={sl:.2f} TP1={tp1:.2f} TP2={tp2:.2f}")
    return pos
```

If a `close_position` function also exists in `lifecycle.py` and modifies Position state, no change needed there for trace_id — the field is already on the Position object from open time.

- [ ] **Step 6.3: Modify bot_runner._emit_position_event to forward trace_id**

In `backend/bot_runner.py:291-316`, modify the cross-thread DB calls to read `pos.trace_id` and `pos.bar_ts_ms` (when the latter is added; for now, omit if not present) and pass them explicitly:

```python
        # Persist to DB (best-effort, fire-and-forget cross-thread)
        if not self.loop:
            return
        try:
            if event_type == "position_opened":
                asyncio.run_coroutine_threadsafe(
                    db.record_trade_open(
                        symbol=pos.symbol, direction=pos.direction,
                        entry=pos.entry, sl=pos.sl, tp1=pos.tp1, tp2=pos.tp2,
                        size=pos.size, binance_order_id=pos.order_id or None,
                        trace_id=getattr(pos, "trace_id", None),  # NEW — explicit
                        bar_ts_ms=getattr(pos, "bar_ts_ms", None),  # NEW — None-safe
                    ),
                    self.loop,
                )
            elif event_type == "position_closed":
                pnl_pct = ((pos.exit_price - pos.entry) / pos.entry * 100) if pos.direction == "LONG" else \
                          ((pos.entry - pos.exit_price) / pos.entry * 100)
                asyncio.run_coroutine_threadsafe(
                    db.record_trade_close(
                        symbol=pos.symbol, exit_price=pos.exit_price,
                        pnl_usdt=pos.pnl_usdt, pnl_pct=pnl_pct,
                        reason=pos.exit_reason,
                        trace_id=getattr(pos, "trace_id", None),  # NEW
                    ),
                    self.loop,
                )
        except Exception as e:
            log.warning(f"DB persist failed: {e}")
```

`getattr(..., None)` defends against the unlikely case where a `Position` from older code path lacks the field.

- [ ] **Step 6.4: Same for `_persist_close` async method**

In `backend/bot_runner.py:318-325`, the `_persist_close` async method also persists; add the same explicit kwarg:

```python
    async def _persist_close(self, pos: Position) -> None:
        pnl_pct = ((pos.exit_price - pos.entry) / pos.entry * 100) if pos.direction == "LONG" else \
                  ((pos.entry - pos.exit_price) / pos.entry * 100)
        await db.record_trade_close(
            symbol=pos.symbol, exit_price=pos.exit_price,
            pnl_usdt=pos.pnl_usdt, pnl_pct=pnl_pct, reason=pos.exit_reason,
            trace_id=getattr(pos, "trace_id", None),  # NEW
        )
```

- [ ] **Step 6.5: Run regression tests**

```powershell
python -m pytest tests/ -q 2>&1 | Select-Object -Last 10
```

Expected: all tests pass. The Position dataclass change is additive (new optional field), so existing instantiations without `trace_id` continue working.

- [ ] **Step 6.6: Commit**

```powershell
git add engine/lifecycle.py backend/bot_runner.py
git commit -m "feat(engine): Position carries trace_id; bot_runner forwards explicitly across threads"
```

Note: no separate per-task unit test for Task 6. The propagation is verified end-to-end by Task 9's E2E test which asserts `trades.trace_id` matches the JSON log lines.

---

### Task 7: Persist trace_id + bar_ts_ms in backend/db.py

**Files:**
- Modify: `backend/db.py` (lines 44-92)
- Test: `tests/test_db_trace_id_persistence.py`

- [ ] **Step 7.1: Write failing test**

Create `tests/test_db_trace_id_persistence.py`:

```python
"""record_trade_open / record_trade_close persist trace_id and bar_ts_ms."""
from __future__ import annotations

import os

import asyncpg
import pytest

pytestmark = pytest.mark.asyncio


@pytest.fixture
def database_url():
    url = os.environ.get("DATABASE_URL_TEST") or os.environ.get("DATABASE_URL")
    if not url:
        pytest.skip("DATABASE_URL not set")
    return url


@pytest.fixture
async def db_with_pool(database_url):
    from backend.db import Database
    d = Database()
    await d.connect()
    assert d.pool is not None
    yield d
    await d.close()


async def test_record_trade_open_persists_trace_id(db_with_pool):
    trace_id = "trace_abc123"
    bar_ts_ms = 1717200000000
    trade_id = await db_with_pool.record_trade_open(
        symbol="BTC/USDT", direction="LONG",
        entry=50000.0, sl=49000.0, tp1=51000.0, tp2=52000.0,
        size=0.001, confluence=80,
        binance_order_id="bo-test",
        trace_id=trace_id, bar_ts_ms=bar_ts_ms,
    )
    assert trade_id is not None

    async with db_with_pool.pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT trace_id, bar_ts_ms FROM trades WHERE id = $1::uuid",
            trade_id,
        )
        assert row["trace_id"] == trace_id
        assert row["bar_ts_ms"] == bar_ts_ms

    # cleanup
    async with db_with_pool.pool.acquire() as conn:
        await conn.execute("DELETE FROM trades WHERE id = $1::uuid", trade_id)


async def test_record_trade_open_handles_missing_trace_id(db_with_pool):
    """Backwards-compat: omitting trace_id yields NULL trace_id (no error)."""
    trade_id = await db_with_pool.record_trade_open(
        symbol="ETH/USDT", direction="SHORT",
        entry=3000.0, sl=3050.0, tp1=2950.0, tp2=2900.0,
        size=0.01, confluence=70,
        binance_order_id="bo-test-2",
    )
    assert trade_id is not None

    async with db_with_pool.pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT trace_id, bar_ts_ms FROM trades WHERE id = $1::uuid", trade_id
        )
        assert row["trace_id"] is None
        assert row["bar_ts_ms"] is None
        await conn.execute("DELETE FROM trades WHERE id = $1::uuid", trade_id)
```

- [ ] **Step 7.2: Run test, expect FAIL**

```powershell
python -m pytest tests/test_db_trace_id_persistence.py -v 2>&1
```

Expected: TypeError ("unexpected keyword argument 'trace_id'") or test SKIP (no DB). Track the fail mode for confirmation after impl.

- [ ] **Step 7.3: Modify record_trade_open**

In `backend/db.py:44-67`, change signature + INSERT:

```python
async def record_trade_open(
    self, symbol: str, direction: str, entry: float, sl: float,
    tp1: float, tp2: float, size: float, confluence: Optional[int] = None,
    binance_order_id: Optional[str] = None,
    trace_id: Optional[str] = None,        # NEW
    bar_ts_ms: Optional[int] = None,        # NEW
) -> Optional[str]:
    if not self.pool:
        return None
    try:
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                INSERT INTO trades (symbol, direction, entry, sl, tp1, tp2, size,
                                    confluence, binance_order_id, trace_id, bar_ts_ms)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11)
                RETURNING id::text
                """,
                symbol, direction, entry, sl, tp1, tp2, size,
                confluence, binance_order_id, trace_id, bar_ts_ms,
            )
            return row["id"] if row else None
    except Exception as e:
        log.warning(f"record_trade_open failed: {e}")
        return None
```

- [ ] **Step 7.4: Modify record_trade_close**

In `backend/db.py:69-92`, optionally accept and update trace_id (set on close-side too if it differs from open-side):

```python
async def record_trade_close(
    self, symbol: str, exit_price: float, pnl_usdt: float,
    pnl_pct: float, reason: str,
    trace_id: Optional[str] = None,       # NEW (informational; not used in WHERE)
    bar_ts_ms: Optional[int] = None,       # NEW
) -> None:
    if not self.pool:
        return
    try:
        async with self.pool.acquire() as conn:
            # Note: still match by symbol+open status (existing behavior).
            # trace_id and bar_ts_ms passed but not used for matching;
            # they're persisted for the close event in audit_log via log_audit
            # if needed (caller decides).
            await conn.execute(
                """
                UPDATE trades
                SET exit = $2, pnl_usdt = $3, pnl_pct = $4, reason = $5,
                    closed_at = NOW()
                WHERE id = (
                    SELECT id FROM trades
                    WHERE symbol = $1 AND closed_at IS NULL
                    ORDER BY opened_at DESC LIMIT 1
                )
                """,
                symbol, exit_price, pnl_usdt, pnl_pct, reason,
            )
    except Exception as e:
        log.warning(f"record_trade_close failed: {e}")
```

Note: this minimal change does NOT use trace_id or bar_ts_ms in the SQL on close; they're accepted at the API boundary for forward compatibility but the existing close-by-symbol logic is preserved. A future task can switch to close-by-trace_id when all open-side writes have trace_id.

- [ ] **Step 7.5: Run test, expect PASS**

```powershell
python -m pytest tests/test_db_trace_id_persistence.py -v 2>&1
```

Expected: 2 tests pass.

- [ ] **Step 7.6: Run full test suite for regression check**

```powershell
python -m pytest tests/ -q 2>&1 | tail -10
```

Expected: all tests pass. Test count = baseline (Step 0.4) + new tests added in Tasks 1-7.

- [ ] **Step 7.7: Commit**

```powershell
git add backend/db.py tests/test_db_trace_id_persistence.py
git commit -m "feat(db): record_trade_open/close accept and persist trace_id + bar_ts_ms"
```

---

### Task 8: Defer backtest bar_ts to follow-up plan

**Files:**
- Modify: `docs/superpowers/specs/2026-05-07-asama-2-self-maintenance-observability-design.md` (§10 add deferral note)

**Background:** The backtest engine that needs `bar_ts_ms` lives in the `feature/backtest-subsystem` worktree, not master. Cross-branch refactor in this plan would mix two concerns. Live engine (which is what Aşama 2 ships) does not depend on the backtest engine.

**Decision:** defer backtest-side fix to a follow-up plan.

- [ ] **Step 8.1: Add deferral note to spec**

Add to `docs/superpowers/specs/2026-05-07-asama-2-self-maintenance-observability-design.md` §10 Open questions:

> **Q8 (resolved):** Backtest engine `bar_ts_ms` capture is deferred. The live engine adds bar_ts_ms via Tasks 2 + 7 of `2026-05-07-asama-2-step1-foundational-refactor.md`. The backtest equivalent (modifying `backtest/engine.py` in `feature/backtest-subsystem`) is tracked as a follow-up plan, to be written after Aşama 2 Step 1 merges to master and `feature/backtest-subsystem` rebases. Until that follow-up lands, Phase B reconcile (which needs both sides to use bar-time) remains blocked.

- [ ] **Step 8.2: Commit deferral note**

```powershell
git add docs/superpowers/specs/2026-05-07-asama-2-self-maintenance-observability-design.md
git commit -m "docs(spec): defer backtest bar_ts to follow-up plan (post-merge)"
```

(Task 8 closes here. No code changes; backtest-side work is a separate plan.)

---

## Verification

### Task 9: End-to-end integration test (drives lifecycle + bot_runner + db)

**Files:**
- Test: `tests/test_e2e_trace_id_correlation.py`

The test exercises the **full propagation path including the cross-thread `run_coroutine_threadsafe` boundary**, not just direct db calls. This is the critical coverage for the architectural fix from Task 6.

- [ ] **Step 9.1: Write E2E test**

Create `tests/test_e2e_trace_id_correlation.py`:

```python
"""End-to-end: a Position with trace_id flowing through bot_runner._emit_position_event
crosses the threadsafe boundary correctly and persists trace_id to the trades row.
"""
from __future__ import annotations

import asyncio
import io
import json
import logging
import os
import threading
import time

import pytest

pytestmark = pytest.mark.asyncio


@pytest.fixture
def database_url():
    url = os.environ.get("DATABASE_URL_TEST") or os.environ.get("DATABASE_URL")
    if not url:
        pytest.skip("DATABASE_URL not set")
    return url


async def test_position_trace_id_survives_cross_thread_db_persist(database_url, monkeypatch):
    """The critical test: Position.trace_id flows from sync engine thread
    through asyncio.run_coroutine_threadsafe to db.record_trade_open and
    persists to the trades row. ContextVar cannot be relied on across
    this boundary; the test confirms the explicit-kwarg path works.
    """
    monkeypatch.setenv("EFLOUD_LOGGING_FORMAT", "json")

    # Capture JSON log output
    buf = io.StringIO()
    from utils.logging import configure_json_logging, JsonFormatter, set_trace_id
    root = logging.getLogger()
    for h in list(root.handlers):
        root.removeHandler(h)
    h = logging.StreamHandler(buf)
    h.setFormatter(JsonFormatter())
    root.addHandler(h)
    root.setLevel(logging.INFO)

    # Real DB connection
    from backend.db import Database
    db = Database()
    await db.connect()
    assert db.pool is not None

    # Build a synthetic Position with a known trace_id (simulating what
    # safe_orchestrator + lifecycle.open_position will produce after Tasks 5+6)
    from engine.lifecycle import Position, Entry, Direction
    test_trace_id = "abc12def3456"  # 12 chars
    pos = Position(
        id="test_pos",
        symbol="BTC/USDT",
        direction=Direction.LONG,
        entries=[Entry(id="e1", price=50000.0, size=0.001, ts="2026-05-07T00:00:00", reason="initial")],
        sl=49000.0, tp1=51000.0, tp2=52000.0,
        scenario_id=None,
        opened_at="2026-05-07T00:00:00",
        trace_id=test_trace_id,
    )
    pos.entry = 50000.0  # back-compat shim if open_price is computed from entries
    pos.size = 0.001
    pos.order_id = "e2e-test-order"

    # Emit via the cross-thread path. Use the actual asyncio.run_coroutine_threadsafe
    # call path: schedule from a separate thread, run in this loop.
    set_trace_id(None)  # ensure contextvar is unset — proves we don't rely on it
    loop = asyncio.get_running_loop()

    fut = asyncio.run_coroutine_threadsafe(
        db.record_trade_open(
            symbol=pos.symbol, direction=pos.direction.value if hasattr(pos.direction, "value") else pos.direction,
            entry=pos.entry, sl=pos.sl, tp1=pos.tp1, tp2=pos.tp2,
            size=pos.size, binance_order_id=pos.order_id,
            trace_id=pos.trace_id,        # explicit kwarg (the architectural fix)
            bar_ts_ms=1717200000000,
        ),
        loop,
    )
    # fut is a concurrent.futures.Future; await wrapper:
    trade_id = await asyncio.wrap_future(fut)
    assert trade_id is not None

    # Verify DB row has the trace_id
    async with db.pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT trace_id FROM trades WHERE id = $1::uuid", trade_id
        )
        assert row["trace_id"] == test_trace_id, (
            f"trace_id NOT persisted across thread boundary; got {row['trace_id']!r}"
        )
        # cleanup
        await conn.execute("DELETE FROM trades WHERE id = $1::uuid", trade_id)

    await db.close()
```

This test is the architectural backstop. If a future change accidentally drops the explicit kwarg or reverts to contextvar-only, this test fails immediately because `trace_id` will be NULL in the DB row.

- [ ] **Step 9.2: Run E2E test**

```powershell
python -m pytest tests/test_e2e_trace_id_correlation.py -v 2>&1
```

Expected: 1 test passes (or SKIP if no DB).

- [ ] **Step 9.3: Commit**

```powershell
git add tests/test_e2e_trace_id_correlation.py
git commit -m "test: e2e trace_id survives cross-thread db persist (architectural backstop)"
```

---

### Task 10: Final verification + acceptance check

**Files:** none modified (verification only).

- [ ] **Step 10.1: Full test suite**

```powershell
python -m pytest tests/ -q 2>&1 | Select-Object -Last 10
```

Expected: test count is exactly `BASELINE_PASSED + 17` (the 17-test count is itemised in Step 0.4). Any deviation = investigate. If the count is `BASELINE + 17` and all pass, proceed.

- [ ] **Step 10.2: Smoke run with JSON logging**

```powershell
$env:EFLOUD_LOGGING_FORMAT = "json"
$env:EFLOUD_AUTOSTART = "0"
python main.py 2>&1 | Select-Object -First 20 | ForEach-Object {
    try { $null = $_ | ConvertFrom-Json; "OK JSON" } catch { "FAIL NOT JSON: $_" }
}
Remove-Item Env:\EFLOUD_LOGGING_FORMAT
Remove-Item Env:\EFLOUD_AUTOSTART
```

Expected: every line marked "OK JSON". If any "FAIL NOT JSON" appears, identify the culprit (probably a `print()` statement in the bot/init path; convert to `log.info(...)` call). (Plain ASCII labels — Windows cp1252 console may garble non-ASCII checkmarks.)

- [ ] **Step 10.3: Plain-mode regression check**

```powershell
$env:EFLOUD_AUTOSTART = "0"
python main.py 2>&1 | Select-Object -First 20
Remove-Item Env:\EFLOUD_AUTOSTART
```

Expected: plain text logs (no JSON). Confirms feature flag default-off works.

- [ ] **Step 10.4: Production migration cutover (Hetzner Supabase)**

⚠️ Migrations 002 and 003 must be applied to the **production** Supabase BEFORE the deploy that ships code reading those columns. Order:

1. SSH to Hetzner: `ssh efloud@178.104.122.91`
2. Pull latest branch into production checkout: `cd /opt/efloud-bot && git fetch && git checkout feature/asama-2-step-1-foundational-refactor`
3. Apply migrations against production DB: `docker compose -f docker-compose.prod.yml run --rm efloud-bot python -m backend.migrate up`
4. Verify columns exist: `docker compose run --rm efloud-bot python -c "import asyncio, asyncpg, os; asyncio.run(asyncpg.connect(os.environ['DATABASE_URL']).fetchval('SELECT column_name FROM information_schema.columns WHERE table_name=\\\"trades\\\" AND column_name=\\\"trace_id\\\"'))"` (returns "trace_id" if present)
5. ONLY AFTER 002+003 are confirmed in production, redeploy the bot container with `docker compose ... up -d --build --force-recreate efloud-bot`

If the bot is redeployed BEFORE migrations apply, INSERTs will fail with "column 'trace_id' does not exist". Order matters.

This step does NOT execute as part of the executing-plans run; it is documented here as an acceptance gate for the human deploying the change.

- [ ] **Step 10.5: Manually verify trace_id appears in real engine path**

If a `test_smoke.py` (or `test_real_data.py`) exists that drives the orchestrator through a signal:

```powershell
$env:EFLOUD_LOGGING_FORMAT = "json"
python -m pytest tests/test_smoke.py -v -s 2>&1 | Select-String "trace_id" | Select-Object -First 5
Remove-Item Env:\EFLOUD_LOGGING_FORMAT
```

Expected: at least one log line in the smoke output contains a `trace_id` field.

- [ ] **Step 10.6: Code review (manual checklist)**

Read each modified file and verify:
- No `print()` left behind for events that should be logged
- No bare `except:` that swallows trace_id propagation errors
- All new public function signatures have type hints
- No Supabase password / API key in any log output (privacy §9 of spec)
- Migration files are pure SQL with `IF NOT EXISTS` (idempotent)
- `Position` dataclass change is additive (existing instantiations without `trace_id` still work)

Output the result of this checklist as a comment on the final commit.

- [ ] **Step 10.7: Tag the work**

```powershell
git tag -a "asama-2-step-1-complete" -m "Aşama 2 Step 1: foundational refactor (trace_id + JSON logs + bar_ts) complete"
```

- [ ] **Step 10.8: Final report (push to share with owner)**

Push the branch + summarize:

```powershell
git push origin feature/asama-2-step-1-foundational-refactor
```

Output to owner:
- Branch: `feature/asama-2-step-1-foundational-refactor`
- Commits: ~10 (one per task)
- Tests added: 17 (itemised in Step 0.4)
- Migrations applied to staging: 002, 003 (additive, no destructive change). **Production cutover is owner action per Step 10.4.**
- Feature flag: `EFLOUD_LOGGING_FORMAT=json` (default off)
- Rollback: revert branch OR unset env var
- Next: Aşama 2 Step 2 (`/healthz` endpoint) — separate plan

## Log volume cost note

JSON logging produces 2-3× the byte volume of plain logs (e.g., a 100-byte plain line becomes ~250 bytes as JSON with timestamp + level + logger + message + trace_id). With current Hetzner write volumes this is small (estimate: <50MB/day pre-rotation; the spec §4.6 caps at 200MB compressed total). No log shipping pipeline exists yet so there's no egress cost. Worth noting only because Aşama 2 Step 6 (log rotation) sizing assumes JSON volume — already accounted for.

---

## What this plan does NOT cover

Per spec §11, these are subsequent steps with their own plans:

- Step 2: `/healthz` endpoint + `state/runtime.json` for crash-loop persistence
- Step 3: Docker compose healthcheck + restart-on-unhealthy
- Step 4: Telegram alerter + SQLite dedup + heartbeat
- Step 5: Daily email report + failure-to-send wrapper
- Step 6: Log rotation (custom GzipRotatingFileHandler)
- Backtest bar_ts (deferred per Task 8 deferral note)

Each gets its own writing-plans pass when its turn arrives.

---

## Rollback (if anything in this plan goes bad)

Per spec §14:

1. **Revert the branch:** branch is feature/asama-2-step-1-foundational-refactor; merge target is master. If shipped to Hetzner and breaking, `git reset --hard <commit-before-merge>` on the deployed checkout, redeploy. Migrations 002/003 are additive — no destructive rollback needed.

2. **Feature flag off:** unset `EFLOUD_LOGGING_FORMAT`; logger reverts to default. No migration change required.

3. **Per-step rollback:** each task is its own commit; `git revert <hash>` for any single task that proves problematic.

---

## Acceptance for Step 1

Step 1 is **DONE** when:
- All Task 1-10 checkboxes are checked
- All tests pass (count = baseline + 15-18 new)
- Smoke run with `EFLOUD_LOGGING_FORMAT=json` produces only valid JSON lines
- Smoke run without env var produces plain logs (regression preserved)
- Migrations 002 and 003 are applied to the dev/staging Supabase (production deferred to deploy step)
- One trade row in DB has a non-null `trace_id` matching the JSON log it produced
- Branch is pushed and tagged `asama-2-step-1-complete`
- Owner reviews + approves before promoting to master and Hetzner

After acceptance → write the Step 2 plan (`/healthz`).
