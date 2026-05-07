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
