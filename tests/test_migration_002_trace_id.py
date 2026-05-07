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
