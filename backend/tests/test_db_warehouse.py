"""Phase 3.2 Trade Warehouse — DB layer unit tests.

Verifies that the new warehouse telemetry columns
(mae_pct, mfe_pct, initial_sl, adx_value, atr_value, funding_rate,
confluence_details) are correctly wired through record_trade_open and
record_trade_close without breaking v1 callers that omit them.

Uses asyncpg pool mocking so no real Postgres connection is required.
"""
from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, call

import pytest

from backend.db import Database


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _mock_pool(fetchrow_return=None, execute_return=None):
    """Build a MagicMock asyncpg.Pool with one acquired conn."""
    conn = MagicMock()
    conn.fetchrow = AsyncMock(return_value=fetchrow_return)
    conn.execute = AsyncMock(return_value=execute_return)
    acquire_ctx = MagicMock(
        __aenter__=AsyncMock(return_value=conn),
        __aexit__=AsyncMock(return_value=False),
    )
    pool = MagicMock()
    pool.acquire = MagicMock(return_value=acquire_ctx)
    return pool, conn


# ─────────────────────────────────────────────────────────────────────────────
# record_trade_open — warehouse telemetry columns
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_record_trade_open_warehouse_telemetry_all_params():
    """All warehouse telemetry kwargs flow into the SQL INSERT."""
    db = Database()
    pool, conn = _mock_pool(fetchrow_return={"id": "warehouse-uuid"})
    db.pool = pool

    conf = {"score": 7, "reasons": ["FVG", "HTF_BULL"], "htf_bias": "BULL"}
    rv = await db.record_trade_open(
        symbol="BTC/USDT", direction="LONG", entry=50000.0, sl=49000.0,
        tp1=52000.0, tp2=55000.0, size=0.01,
        initial_sl=49000.0,
        adx_value=28.5,
        atr_value=1250.0,
        funding_rate=0.0001,
        confluence_details=conf,
    )
    assert rv == "warehouse-uuid"

    sql = conn.fetchrow.call_args[0][0]
    assert "initial_sl" in sql
    assert "adx_value" in sql
    assert "atr_value" in sql
    assert "funding_rate" in sql
    assert "confluence_details" in sql

    args = conn.fetchrow.call_args[0][1:]
    assert 28.5 in args
    assert 1250.0 in args
    assert 0.0001 in args
    # confluence_details is JSON-serialised before being passed as string param
    assert any("FVG" in str(a) for a in args), (
        "confluence_details JSON string not found in SQL args"
    )


@pytest.mark.asyncio
async def test_record_trade_open_warehouse_defaults_to_none():
    """v1 callers that omit warehouse kwargs get NULL bound to those params."""
    db = Database()
    pool, conn = _mock_pool(fetchrow_return={"id": "v1-uuid"})
    db.pool = pool

    await db.record_trade_open(
        symbol="ETH/USDT", direction="SHORT", entry=3000.0, sl=3100.0,
        tp1=2800.0, tp2=2600.0, size=0.1,
    )
    args = conn.fetchrow.call_args[0][1:]
    # Last 5 positional params should be None (initial_sl..confluence_details)
    assert args[-5:] == (None, None, None, None, None)


@pytest.mark.asyncio
async def test_record_trade_open_confluence_details_serialised_as_json():
    """confluence_details dict is JSON-serialised before DB insert."""
    db = Database()
    pool, conn = _mock_pool(fetchrow_return={"id": "json-test"})
    db.pool = pool

    nested = {"score": 5, "reasons": ["OTE"], "htf_bias": "BEAR", "nested": {"x": 1}}
    await db.record_trade_open(
        symbol="SOL/USDT", direction="SHORT", entry=150.0, sl=155.0,
        tp1=140.0, tp2=None, size=5.0,
        confluence_details=nested,
    )
    args = conn.fetchrow.call_args[0][1:]
    conf_arg = args[-1]  # last param = confluence_details
    # Should be a JSON string (or None if null — but here it's not None)
    assert isinstance(conf_arg, str)
    parsed = json.loads(conf_arg)
    assert parsed["score"] == 5
    assert "OTE" in parsed["reasons"]


@pytest.mark.asyncio
async def test_record_trade_open_confluence_details_none_passes_none():
    """None confluence_details stays None (not serialised)."""
    db = Database()
    pool, conn = _mock_pool(fetchrow_return={"id": "null-conf"})
    db.pool = pool

    await db.record_trade_open(
        symbol="ADA/USDT", direction="LONG", entry=0.5, sl=0.48,
        tp1=0.55, tp2=0.60, size=1000.0,
        confluence_details=None,
    )
    args = conn.fetchrow.call_args[0][1:]
    assert args[-1] is None


# ─────────────────────────────────────────────────────────────────────────────
# record_trade_close — MAE/MFE columns
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_record_trade_close_with_mae_mfe():
    """mae_pct and mfe_pct are passed as positional params to UPDATE."""
    db = Database()
    pool, conn = _mock_pool()
    db.pool = pool

    await db.record_trade_close(
        symbol="BTC/USDT", exit_price=51000.0, pnl_usdt=10.0,
        pnl_pct=2.0, reason="TP1",
        mae_pct=0.5,
        mfe_pct=2.5,
    )
    conn.execute.assert_called_once()
    sql = conn.execute.call_args[0][0]
    assert "mae_pct" in sql
    assert "mfe_pct" in sql

    args = conn.execute.call_args[0][1:]
    assert 0.5 in args  # mae_pct
    assert 2.5 in args  # mfe_pct


@pytest.mark.asyncio
async def test_record_trade_close_mae_mfe_defaults_to_none():
    """Omitting mae_pct/mfe_pct binds None (COALESCE keeps existing DB value)."""
    db = Database()
    pool, conn = _mock_pool()
    db.pool = pool

    await db.record_trade_close(
        symbol="ETH/USDT", exit_price=3100.0, pnl_usdt=-5.0,
        pnl_pct=-1.67, reason="SL",
    )
    args = conn.execute.call_args[0][1:]
    # $6=mae_pct, $7=mfe_pct — both None means COALESCE preserves existing value
    assert args[5] is None  # mae_pct ($6)
    assert args[6] is None  # mfe_pct ($7)


# ─────────────────────────────────────────────────────────────────────────────
# No-pool graceful degradation
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_record_trade_open_no_pool_returns_none_with_warehouse_kwargs():
    """No pool: warehouse kwargs accepted at API boundary, returns None (no raise)."""
    db = Database()
    db.pool = None

    rv = await db.record_trade_open(
        symbol="SOL/USDT", direction="LONG", entry=100.0, sl=95.0,
        tp1=110.0, tp2=None, size=10.0,
        adx_value=31.2, atr_value=4.5, funding_rate=0.00005,
        confluence_details={"score": 9},
    )
    assert rv is None


@pytest.mark.asyncio
async def test_record_trade_close_no_pool_noop_with_mae_mfe():
    """No pool: mae_pct/mfe_pct accepted, function is a no-op (no raise)."""
    db = Database()
    db.pool = None

    # Must not raise
    await db.record_trade_close(
        symbol="SOL/USDT", exit_price=105.0, pnl_usdt=5.0,
        pnl_pct=5.0, reason="TP1",
        mae_pct=0.3, mfe_pct=5.2,
    )
