"""Multi-instance persistence — EFLOUD_BOT_ID isolation (migration 012).

Two bots (V1 profile mid + V2 profile long) may share one Supabase project. Every
write must be tagged with the bot's instance id, and every instance-scoped read/
update must filter by it — otherwise V1's reconcile could close a V2 trade row and
the breaker_state singleton (migration 010, id=1) would clobber across bots.

Contract:
  - Database.bot_id = EFLOUD_BOT_ID env, default 'v1' (byte-identical for current bot).
  - record_trade_open: INSERT carries bot_id.
  - record_trade_close: UPDATE's open-row subquery filters bot_id (no cross-bot close).
  - record_equity_snapshot / log_audit: INSERT carries bot_id.
  - upsert_breaker_state: keyed on bot_id (ON CONFLICT bot_id), NOT the id=1 singleton.
  - load_breaker_state: filters bot_id.
  - fetch_recent_trades: filters bot_id (per-bot dashboard).

Uses asyncpg pool mocking (no real Postgres), matching test_db_warehouse.py.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from backend.db import Database


def _mock_pool(fetchrow_return=None, fetch_return=None):
    conn = MagicMock()
    conn.fetchrow = AsyncMock(return_value=fetchrow_return)
    conn.fetch = AsyncMock(return_value=fetch_return or [])
    conn.execute = AsyncMock(return_value=None)
    acquire_ctx = MagicMock(
        __aenter__=AsyncMock(return_value=conn),
        __aexit__=AsyncMock(return_value=False),
    )
    pool = MagicMock()
    pool.acquire = MagicMock(return_value=acquire_ctx)
    return pool, conn


# ── bot_id resolution from env ────────────────────────────────────

def test_bot_id_defaults_to_v1(monkeypatch):
    monkeypatch.delenv("EFLOUD_BOT_ID", raising=False)
    assert Database().bot_id == "v1"


def test_bot_id_from_env(monkeypatch):
    monkeypatch.setenv("EFLOUD_BOT_ID", "v2-long")
    assert Database().bot_id == "v2-long"


# ── writes carry bot_id ───────────────────────────────────────────

@pytest.mark.asyncio
async def test_record_trade_open_includes_bot_id(monkeypatch):
    monkeypatch.setenv("EFLOUD_BOT_ID", "v2-long")
    db = Database()
    pool, conn = _mock_pool(fetchrow_return={"id": "uuid"})
    db.pool = pool

    await db.record_trade_open(
        symbol="BTC/USDT", direction="LONG", entry=50000.0, sl=49000.0,
        tp1=52000.0, tp2=55000.0, size=0.01,
    )
    sql = conn.fetchrow.call_args[0][0]
    args = conn.fetchrow.call_args[0][1:]
    assert "bot_id" in sql
    assert "v2-long" in args


@pytest.mark.asyncio
async def test_record_trade_open_warehouse_telemetry_still_last5(monkeypatch):
    """Regression: bot_id must NOT displace the trailing telemetry params."""
    monkeypatch.setenv("EFLOUD_BOT_ID", "v2-long")
    db = Database()
    pool, conn = _mock_pool(fetchrow_return={"id": "uuid"})
    db.pool = pool
    await db.record_trade_open(
        symbol="ETH/USDT", direction="SHORT", entry=3000.0, sl=3100.0,
        tp1=2800.0, tp2=2600.0, size=0.1,
    )
    args = conn.fetchrow.call_args[0][1:]
    assert args[-5:] == (None, None, None, None, None)


@pytest.mark.asyncio
async def test_record_trade_close_filters_by_bot_id(monkeypatch):
    monkeypatch.setenv("EFLOUD_BOT_ID", "v2-long")
    db = Database()
    pool, conn = _mock_pool()
    db.pool = pool

    await db.record_trade_close(
        symbol="BTC/USDT", exit_price=51000.0, pnl_usdt=10.0,
        pnl_pct=2.0, reason="TP1",
    )
    sql = conn.execute.call_args[0][0]
    args = conn.execute.call_args[0][1:]
    assert "bot_id" in sql
    assert "v2-long" in args


@pytest.mark.asyncio
async def test_record_trade_close_mae_mfe_positions_unchanged(monkeypatch):
    """Regression: mae_pct/mfe_pct stay at positional $6/$7 (args[5]/args[6])."""
    monkeypatch.setenv("EFLOUD_BOT_ID", "v2-long")
    db = Database()
    pool, conn = _mock_pool()
    db.pool = pool
    await db.record_trade_close(
        symbol="ETH/USDT", exit_price=3100.0, pnl_usdt=-5.0,
        pnl_pct=-1.67, reason="SL",
    )
    args = conn.execute.call_args[0][1:]
    assert args[5] is None  # mae_pct ($6)
    assert args[6] is None  # mfe_pct ($7)


@pytest.mark.asyncio
async def test_record_equity_snapshot_includes_bot_id(monkeypatch):
    monkeypatch.setenv("EFLOUD_BOT_ID", "v2-long")
    db = Database()
    pool, conn = _mock_pool()
    db.pool = pool
    await db.record_equity_snapshot(balance=1035.0, open_positions_count=2)
    sql = conn.execute.call_args[0][0]
    args = conn.execute.call_args[0][1:]
    assert "bot_id" in sql
    assert "v2-long" in args


@pytest.mark.asyncio
async def test_log_audit_includes_bot_id(monkeypatch):
    monkeypatch.setenv("EFLOUD_BOT_ID", "v2-long")
    db = Database()
    pool, conn = _mock_pool()
    db.pool = pool
    await db.log_audit("startup", {"k": "v"})
    sql = conn.execute.call_args[0][0]
    args = conn.execute.call_args[0][1:]
    assert "bot_id" in sql
    assert "v2-long" in args


# ── breaker_state keyed on bot_id (not the id=1 singleton) ─────────

@pytest.mark.asyncio
async def test_upsert_breaker_state_keyed_on_bot_id(monkeypatch):
    monkeypatch.setenv("EFLOUD_BOT_ID", "v2-long")
    db = Database()
    pool, conn = _mock_pool()
    db.pool = pool
    from engine.safety.breaker import CircuitBreaker
    breaker = CircuitBreaker(starting_balance=1035.0)
    breaker.check()

    await db.upsert_breaker_state(breaker.to_dict())
    sql = conn.execute.call_args[0][0]
    args = conn.execute.call_args[0][1:]
    assert "ON CONFLICT (bot_id)" in sql
    assert "v2-long" in args


@pytest.mark.asyncio
async def test_load_breaker_state_filters_by_bot_id(monkeypatch):
    monkeypatch.setenv("EFLOUD_BOT_ID", "v2-long")
    db = Database()
    pool, conn = _mock_pool(fetchrow_return={"halted": False})
    db.pool = pool
    await db.load_breaker_state()
    sql = conn.fetchrow.call_args[0][0]
    args = conn.fetchrow.call_args[0][1:]
    assert "bot_id" in sql
    assert "v2-long" in args


# ── reads scoped to the instance ──────────────────────────────────

@pytest.mark.asyncio
async def test_fetch_recent_trades_filters_by_bot_id(monkeypatch):
    monkeypatch.setenv("EFLOUD_BOT_ID", "v2-long")
    db = Database()
    pool, conn = _mock_pool(fetch_return=[])
    db.pool = pool
    await db.fetch_recent_trades(limit=10)
    sql = conn.fetch.call_args[0][0]
    args = conn.fetch.call_args[0][1:]
    assert "bot_id" in sql
    assert "v2-long" in args


@pytest.mark.asyncio
async def test_fetch_trades_since_filters_by_bot_id(monkeypatch):
    from datetime import datetime, timezone
    monkeypatch.setenv("EFLOUD_BOT_ID", "v2-long")
    db = Database()
    pool, conn = _mock_pool(fetch_return=[])
    db.pool = pool
    await db.fetch_trades_since(datetime(2026, 6, 1, tzinfo=timezone.utc))
    sql = conn.fetch.call_args[0][0]
    args = conn.fetch.call_args[0][1:]
    assert "bot_id" in sql
    assert "v2-long" in args


@pytest.mark.asyncio
async def test_fetch_equity_history_filters_by_bot_id(monkeypatch):
    monkeypatch.setenv("EFLOUD_BOT_ID", "v2-long")
    db = Database()
    pool, conn = _mock_pool(fetch_return=[])
    db.pool = pool
    await db.fetch_equity_history(days=7)
    sql = conn.fetch.call_args[0][0]
    args = conn.fetch.call_args[0][1:]
    assert "bot_id" in sql
    assert "v2-long" in args
