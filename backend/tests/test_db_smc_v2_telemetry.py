"""SMC v2 telemetry DB writes (PR #S5).

Uses asyncpg pool mocking to verify SQL params shape without a real Postgres.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from backend.db import Database


def _mock_pool(fetchrow_return):
    """Build a MagicMock that quacks like asyncpg.Pool with one acquired conn."""
    conn = MagicMock()
    conn.fetchrow = AsyncMock(return_value=fetchrow_return)
    conn.execute = AsyncMock(return_value=None)
    acquire_ctx = MagicMock(
        __aenter__=AsyncMock(return_value=conn),
        __aexit__=AsyncMock(return_value=False),
    )
    pool = MagicMock()
    pool.acquire = MagicMock(return_value=acquire_ctx)
    return pool, conn


@pytest.mark.asyncio
async def test_record_trade_open_accepts_telemetry_kwargs():
    db = Database()
    pool, conn = _mock_pool({"id": "deadbeef"})
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

    sql = conn.fetchrow.call_args[0][0]
    assert "entry_setup_source" in sql
    assert "tp1_target_type" in sql
    assert "tp2_target_type" in sql
    assert "bars_to_pullback" in sql

    args = conn.fetchrow.call_args[0][1:]
    assert "FVG_PULLBACK" in args
    assert "LIQUIDITY" in args
    assert "FVG_FAR" in args
    assert 3 in args


@pytest.mark.asyncio
async def test_record_trade_open_telemetry_kwargs_default_none():
    """v1 path: omit telemetry kwargs, get NULL (None) bound to those params."""
    db = Database()
    pool, conn = _mock_pool({"id": "x"})
    db.pool = pool

    await db.record_trade_open(
        symbol="ETH/USDT", direction="LONG", entry=100.0, sl=95.0,
        tp1=110.0, tp2=120.0, size=1.0,
    )
    args = conn.fetchrow.call_args[0][1:]
    # The 4 telemetry args are the last 4 positional params (after $11=bar_ts_ms).
    # Tight position-based assertion catches off-by-one in the SQL VALUES tuple.
    assert args[-4:] == (None, None, None, None)


@pytest.mark.asyncio
async def test_record_trade_open_no_pool_returns_none():
    """No DATABASE_URL set: pool is None, return None instead of raising."""
    db = Database()
    db.pool = None
    rv = await db.record_trade_open(
        symbol="ETH/USDT", direction="LONG", entry=100.0, sl=95.0,
        tp1=110.0, tp2=120.0, size=1.0,
        entry_setup_source="FVG_PULLBACK",
    )
    assert rv is None
