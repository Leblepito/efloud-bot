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
