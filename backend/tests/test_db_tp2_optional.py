"""record_trade_open accepts tp2=None (PR #S5.5 task 5).

Migration 008 drops the NOT NULL constraint on trades.tp2.
db.py signature widened: tp2: float → tp2: Optional[float].
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from backend.db import Database


def _mock_pool(fetchrow_return):
    conn = MagicMock()
    conn.fetchrow = AsyncMock(return_value=fetchrow_return)
    acquire_ctx = MagicMock(
        __aenter__=AsyncMock(return_value=conn),
        __aexit__=AsyncMock(return_value=False),
    )
    pool = MagicMock()
    pool.acquire = MagicMock(return_value=acquire_ctx)
    return pool, conn


@pytest.mark.asyncio
async def test_record_trade_open_accepts_tp2_none():
    """tp2=None must bind as NULL into the INSERT, not crash."""
    db = Database()
    pool, conn = _mock_pool({"id": "x"})
    db.pool = pool
    rv = await db.record_trade_open(
        symbol="ETH/USDT", direction="LONG", entry=100.0, sl=95.0,
        tp1=110.0, tp2=None, size=1.0,
    )
    assert rv == "x"
    # tp2 is the 6th positional bound param ($6)
    args = conn.fetchrow.call_args[0][1:]
    assert args[5] is None  # tp2


@pytest.mark.asyncio
async def test_record_trade_open_tp2_numeric_unchanged():
    """Regression: numeric tp2 still binds correctly."""
    db = Database()
    pool, conn = _mock_pool({"id": "x"})
    db.pool = pool
    await db.record_trade_open(
        symbol="ETH/USDT", direction="LONG", entry=100.0, sl=95.0,
        tp1=110.0, tp2=120.0, size=1.0,
    )
    args = conn.fetchrow.call_args[0][1:]
    assert args[5] == 120.0


def test_migration_008_file_exists_and_is_idempotent_format():
    """Migration 008 must exist and use ALTER COLUMN DROP NOT NULL."""
    from pathlib import Path
    migration = Path(__file__).resolve().parents[2] / "backend" / "migrations" / "008_tp2_nullable.sql"
    assert migration.exists(), f"Missing: {migration}"
    body = migration.read_text(encoding="utf-8")
    assert "ALTER TABLE trades ALTER COLUMN tp2 DROP NOT NULL" in body
