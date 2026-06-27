"""Test that update_trade_audited_pnl correctly updates pnl_usdt and recalculates pnl_pct."""
import pytest
from unittest.mock import AsyncMock, MagicMock
from backend.db import Database

def _mock_pool():
    conn = MagicMock()
    conn.execute = AsyncMock()
    acquire_ctx = MagicMock(
        __aenter__=AsyncMock(return_value=conn),
        __aexit__=AsyncMock(return_value=False),
    )
    pool = MagicMock()
    pool.acquire = MagicMock(return_value=acquire_ctx)
    return pool, conn

@pytest.mark.asyncio
async def test_update_trade_audited_pnl_by_order_id():
    db = Database()
    pool, conn = _mock_pool()
    db.pool = pool

    await db.update_trade_audited_pnl(-5.20, order_id="order-123")
    conn.execute.assert_called_once()
    sql, pnl, order_id = conn.execute.call_args[0]
    assert "UPDATE trades" in sql
    assert "SET pnl_usdt = $1" in sql
    assert "pnl_pct = CASE WHEN" in sql
    assert "WHERE binance_order_id = $2" in sql
    assert pnl == -5.20
    assert order_id == "order-123"

@pytest.mark.asyncio
async def test_update_trade_audited_pnl_by_trace_id():
    db = Database()
    pool, conn = _mock_pool()
    db.pool = pool

    await db.update_trade_audited_pnl(12.50, trace_id="trace-abc")
    conn.execute.assert_called_once()
    sql, pnl, trace_id = conn.execute.call_args[0]
    assert "UPDATE trades" in sql
    assert "WHERE trace_id = $2" in sql
    assert pnl == 12.50
    assert trace_id == "trace-abc"

@pytest.mark.asyncio
async def test_update_trade_audited_pnl_by_symbol():
    db = Database()
    pool, conn = _mock_pool()
    db.pool = pool

    await db.update_trade_audited_pnl(-1.50, symbol="BTC/USDT")
    conn.execute.assert_called_once()
    sql, pnl, symbol = conn.execute.call_args[0]
    assert "UPDATE trades" in sql
    assert "WHERE symbol = $2 AND closed_at IS NOT NULL" in sql
    assert pnl == -1.50
    assert symbol == "BTC/USDT"
