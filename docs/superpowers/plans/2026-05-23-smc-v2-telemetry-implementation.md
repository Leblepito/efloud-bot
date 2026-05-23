# SMC v2 Telemetry Implementation Plan (PR #S5)

**Goal:** Add 4 nullable telemetry fields to both Position dataclasses + DB schema + bot_runner wiring + single-target close branch.

**Architecture:** Additive forward-compatible changes; v1 path writes None throughout; single-target branch dormant in prod until v2 emits `tp2=None`.

**Tech Stack:** Python 3.14, asyncpg, Postgres.

## Task 1: lifecycle.Position telemetry fields + roundtrip

**Files:**
- Modify: `engine/lifecycle.py:58` (Position dataclass)
- Test: `backend/tests/test_lifecycle_telemetry.py` (new)

- [ ] **Step 1: Write failing tests**

```python
# backend/tests/test_lifecycle_telemetry.py
from engine.lifecycle import Position, PositionLifecycle


def test_position_telemetry_fields_default_none():
    p = Position(id="x", symbol="ETH/USDT", direction="LONG")
    assert p.entry_setup_source is None
    assert p.tp1_target_type is None
    assert p.tp2_target_type is None
    assert p.bars_to_pullback is None


def test_position_to_full_dict_roundtrip_with_telemetry():
    p = Position(id="x", symbol="ETH/USDT", direction="LONG",
                 entry_setup_source="FVG_PULLBACK", tp1_target_type="LIQUIDITY",
                 tp2_target_type="FVG_FAR", bars_to_pullback=3)
    d = p.to_full_dict()
    p2 = Position.from_full_dict(d)
    assert p2.entry_setup_source == "FVG_PULLBACK"
    assert p2.tp1_target_type == "LIQUIDITY"
    assert p2.tp2_target_type == "FVG_FAR"
    assert p2.bars_to_pullback == 3


def test_position_from_full_dict_missing_keys_default_none():
    """Backwards-compat: old state files lack telemetry keys."""
    d = {"id": "x", "symbol": "ETH/USDT", "direction": "LONG", "entries": [], "exits": []}
    p = Position.from_full_dict(d)
    assert p.entry_setup_source is None
    assert p.bars_to_pullback is None


def test_open_position_accepts_telemetry_kwargs():
    lc = PositionLifecycle()
    p = lc.open_position("ETH/USDT", "LONG", 100.0, 1.0, sl=95.0, tp1=110.0, tp2=120.0,
                         entry_setup_source="OTE_RETRACE", tp1_target_type="LIQUIDITY",
                         tp2_target_type="FIB_EXT", bars_to_pullback=5)
    assert p.entry_setup_source == "OTE_RETRACE"
    assert p.tp1_target_type == "LIQUIDITY"
    assert p.tp2_target_type == "FIB_EXT"
    assert p.bars_to_pullback == 5


def test_open_position_telemetry_kwargs_optional():
    """Existing call sites must not break."""
    lc = PositionLifecycle()
    p = lc.open_position("ETH/USDT", "LONG", 100.0, 1.0, sl=95.0, tp1=110.0, tp2=120.0)
    assert p.entry_setup_source is None
```

- [ ] **Step 2: Run tests (FAIL)** — Expected: AttributeError or TypeError
- [ ] **Step 3: Add 4 fields to Position dataclass**
- [ ] **Step 4: Update `to_full_dict` + `from_full_dict` + `open_position` kwargs**
- [ ] **Step 5: Tests PASS**
- [ ] **Step 6: Run existing lifecycle tests** — `pytest backend/tests/test_lifecycle.py -q`
- [ ] **Step 7: Commit** — `feat(lifecycle): add SMC v2 telemetry fields to Position`

## Task 2: Single-target close branch (lifecycle.partial_close)

**Files:**
- Modify: `engine/lifecycle.py` partial_close
- Test: `backend/tests/test_lifecycle_telemetry.py` (extend)

- [ ] **Step 1: Write failing tests**

```python
def test_partial_close_single_target_full_close_on_tp1():
    """Single-target mode: when tp2 is None, TP1 fill triggers full close."""
    lc = PositionLifecycle()
    p = lc.open_position("ETH/USDT", "LONG", 100.0, 1.0, sl=95.0, tp1=110.0, tp2=None)
    assert p.tp2 is None
    result = lc.partial_close(p, 110.0, 0.5, reason="TP1")
    assert result is True
    assert not p.is_open  # FULL closed, not partial
    assert p.tp1_hit is True
    # Only one exit (close_position), not a TP1 partial then BE
    assert len(p.exits) == 1
    assert p.exits[0].reason == "TP1"


def test_partial_close_two_target_unchanged():
    """Two-target mode (v1 default): TP1 partial, SL moves to BE — old behavior."""
    lc = PositionLifecycle()
    p = lc.open_position("ETH/USDT", "LONG", 100.0, 1.0, sl=95.0, tp1=110.0, tp2=120.0)
    assert p.tp2 == 120.0
    lc.partial_close(p, 110.0, 0.5, reason="TP1")
    assert p.is_open  # half remaining
    assert p.tp1_hit is True
    assert p.sl_moved_to_be is True
    assert p.sl == 100.0  # moved to entry
```

- [ ] **Step 2: Run tests (FAIL)** — Expected: first test fails because TP1 keeps position open
- [ ] **Step 3: Add `if reason == "TP1" and pos.tp2 is None: return self.close_position(pos, price, "TP1")` early branch**
- [ ] **Step 4: Tests PASS + existing partial_close tests still green**
- [ ] **Step 5: Commit** — `feat(lifecycle): single-target close branch for tp2=None (inert under v1)`

## Task 3: exchange.Position telemetry fields

**Files:**
- Modify: `exchange/__init__.py:200 Position` dataclass
- Modify: `exchange/__init__.py OrderManager.open_position` signature
- Test: `backend/tests/test_lifecycle_telemetry.py` (extend) OR new `test_exchange_position_telemetry.py`

- [ ] **Step 1: Write failing tests**
- [ ] **Step 2: Add 4 fields to dataclass**
- [ ] **Step 3: Add 4 optional kwargs to `OrderManager.open_position`, thread to Position constructor**
- [ ] **Step 4: Tests PASS + existing exchange tests still green**
- [ ] **Step 5: Commit** — `feat(exchange): add SMC v2 telemetry fields to Position + open_position`

## Task 4: Migration 007 + db.py

**Files:**
- Create: `backend/migrations/007_smc_v2_telemetry.sql`
- Modify: `backend/db.py:46 record_trade_open` + SELECT lists in fetch helpers
- Test: `backend/tests/test_db_smc_v2_telemetry.py` (new)

- [ ] **Step 1: Write failing test (mocked pool, capture SQL args)**

```python
# backend/tests/test_db_smc_v2_telemetry.py
import pytest
from unittest.mock import AsyncMock, MagicMock
from backend.db import Database


@pytest.mark.asyncio
async def test_record_trade_open_accepts_telemetry_kwargs():
    db = Database()
    pool = MagicMock()
    conn = MagicMock()
    conn.fetchrow = AsyncMock(return_value={"id": "deadbeef"})
    pool.acquire = MagicMock(return_value=MagicMock(
        __aenter__=AsyncMock(return_value=conn),
        __aexit__=AsyncMock(return_value=False),
    ))
    db.pool = pool
    rv = await db.record_trade_open(
        symbol="ETH/USDT", direction="LONG", entry=100.0, sl=95.0,
        tp1=110.0, tp2=120.0, size=1.0,
        entry_setup_source="FVG_PULLBACK",
        tp1_target_type="LIQUIDITY",
        tp2_target_type="FVG_FAR",
        bars_to_pullback=3,
    )
    assert rv == "deadbeef"
    call_args = conn.fetchrow.call_args
    sql = call_args[0][0]
    assert "entry_setup_source" in sql
    assert "tp1_target_type" in sql
    assert "tp2_target_type" in sql
    assert "bars_to_pullback" in sql
    # Telemetry args at the end of positional list
    args = call_args[0][1:]
    assert "FVG_PULLBACK" in args
    assert "LIQUIDITY" in args
    assert "FVG_FAR" in args
    assert 3 in args


@pytest.mark.asyncio
async def test_record_trade_open_telemetry_kwargs_default_none():
    """v1 path: omit telemetry kwargs, get NULL in DB."""
    db = Database()
    pool = MagicMock()
    conn = MagicMock()
    conn.fetchrow = AsyncMock(return_value={"id": "x"})
    pool.acquire = MagicMock(return_value=MagicMock(
        __aenter__=AsyncMock(return_value=conn),
        __aexit__=AsyncMock(return_value=False),
    ))
    db.pool = pool
    await db.record_trade_open(
        symbol="ETH/USDT", direction="LONG", entry=100.0, sl=95.0,
        tp1=110.0, tp2=120.0, size=1.0,
    )
    args = conn.fetchrow.call_args[0][1:]
    # The 4 telemetry args should all be None
    assert args.count(None) >= 4
```

- [ ] **Step 2: Run tests (FAIL)** — TypeError on unknown kwargs
- [ ] **Step 3: Write migration 007 SQL file**
- [ ] **Step 4: Extend `record_trade_open` signature + INSERT statement**
- [ ] **Step 5: Extend `fetch_recent_trades` + `fetch_trades_since` SELECT columns**
- [ ] **Step 6: Tests PASS**
- [ ] **Step 7: Commit** — `feat(db): migration 007 + record_trade_open telemetry kwargs`

## Task 5: bot_runner.py wiring

**Files:**
- Modify: `backend/bot_runner.py:380` `position_opened` branch
- Test: `backend/tests/test_lifecycle_telemetry.py` (extend with a tiny shape check OR new file)

- [ ] **Step 1: Add 4 `getattr(pos, "...", None)` lines to record_trade_open call**
- [ ] **Step 2: Smoke test — `pytest backend/tests/test_bot_runner*.py -q`**
- [ ] **Step 3: Commit** — `feat(bot_runner): wire SMC v2 telemetry fields to DB persist`

## Task 6: orchestrator wiring (v2 entry path)

**Files:**
- Modify: `engine/safe_orchestrator.py:_place_v2_entry_order` (PR #71)
- Test: extend `backend/tests/smc_v2/test_entry_order_placement.py`

- [ ] **Step 1: Add telemetry derivation to `_place_v2_entry_order`**
- [ ] **Step 2: Add test asserting OrderManager.open_position receives telemetry kwargs**
- [ ] **Step 3: Tests PASS + PR #71 test regression check**
- [ ] **Step 4: Commit** — `feat(orchestrator): pass v2 telemetry to OrderManager.open_position`

## Task 7: Full suite + risk-ops review + push/merge

- [ ] **Step 1: Full backend suite** — expect 626 + ~12 new = 638 green
- [ ] **Step 2: Run efloud-code-reviewer agent**
- [ ] **Step 3: Run efloud-risk-ops-reviewer agent** (REQUIRED — exchange/ + migration)
- [ ] **Step 4: Apply review findings**
- [ ] **Step 5: Push branch + create PR**
- [ ] **Step 6: Self-approve merge (Hermes mode)**
- [ ] **Step 7: Update memory file**
