"""C5 regression: record_trade_close must key on trace_id when provided.

The close UPDATE matched the row by ``symbol = $1 AND closed_at IS NULL ORDER BY
opened_at DESC LIMIT 1`` — no trace_id. On rapid same-symbol churn (reverse-on-
profit flip, or fast SL→re-entry) two open rows can briefly coexist; the close
then stamped the MOST RECENT open row (the freshly-opened trade) with the old
trade's exit/PnL, leaving the actually-closed trade open forever. It also made
the reconcile double-write (two record_trade_close calls per close) corrupt a
second row instead of no-op'ing.

Fix: prefer trace_id in the WHERE — `($8 IS NULL AND symbol=$1) OR trace_id=$8`.
This closes the correct row, and a duplicate call no-ops (the trace_id row is
already closed → closed_at IS NULL excludes it).
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from backend.db import Database


def _mock_pool():
    conn = MagicMock()
    conn.execute = AsyncMock(return_value=None)
    acquire_ctx = MagicMock(
        __aenter__=AsyncMock(return_value=conn),
        __aexit__=AsyncMock(return_value=False),
    )
    pool = MagicMock()
    pool.acquire = MagicMock(return_value=acquire_ctx)
    return pool, conn


@pytest.mark.asyncio
async def test_close_keys_on_trace_id_when_provided():
    db = Database()
    pool, conn = _mock_pool()
    db.pool = pool
    await db.record_trade_close(
        symbol="ETH/USDT", exit_price=100.0, pnl_usdt=5.0, pnl_pct=1.0,
        reason="RECONCILED", trace_id="trace-abc",
    )
    sql, *params = conn.execute.call_args[0]
    assert "trace_id" in sql, "WHERE must select by trace_id, not symbol-only"
    assert "trace-abc" in params, "trace_id must be bound as a query param"


@pytest.mark.asyncio
async def test_close_falls_back_to_symbol_when_no_trace_id():
    db = Database()
    pool, conn = _mock_pool()
    db.pool = pool
    await db.record_trade_close(
        symbol="ETH/USDT", exit_price=100.0, pnl_usdt=5.0, pnl_pct=1.0,
        reason="TP1",
    )
    sql, *params = conn.execute.call_args[0]
    assert "symbol = $1" in sql, "symbol fallback must be preserved"
    assert "ETH/USDT" in params
