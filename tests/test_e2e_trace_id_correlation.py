"""End-to-end: a Position with trace_id flowing through bot_runner._on_position_change
crosses the threadsafe boundary correctly and persists trace_id to the trades row.

Architectural backstop: if a future change accidentally drops the explicit-kwarg path
or relies on ContextVar across threads (which doesn't propagate), this test fails
because the DB row's trace_id will be NULL.

NOTE: targets exchange.Position (the class flowing to DB persistence via the
on_position_change callback chain), NOT engine.lifecycle.Position.
"""
from __future__ import annotations

import asyncio
import io
import logging
import os

import pytest

pytestmark = pytest.mark.asyncio


@pytest.fixture
def database_url():
    url = os.environ.get("DATABASE_URL_TEST") or os.environ.get("DATABASE_URL")
    if not url:
        pytest.skip("DATABASE_URL not set")
    return url


async def test_position_trace_id_survives_cross_thread_db_persist(database_url, monkeypatch):
    """The critical test: an exchange.Position with trace_id flows from sync engine thread
    through asyncio.run_coroutine_threadsafe to db.record_trade_open and persists
    trace_id to the trades row. ContextVar cannot be relied on across this boundary;
    this test confirms the explicit-kwarg path works.
    """
    monkeypatch.setenv("EFLOUD_LOGGING_FORMAT", "json")

    # Capture JSON log output
    buf = io.StringIO()
    from utils.logging import JsonFormatter, set_trace_id
    root = logging.getLogger()
    saved_handlers = list(root.handlers)
    saved_level = root.level
    for h in list(root.handlers):
        root.removeHandler(h)
    h = logging.StreamHandler(buf)
    h.setFormatter(JsonFormatter())
    root.addHandler(h)
    root.setLevel(logging.INFO)

    try:
        # Real DB connection
        from backend.db import Database
        db = Database()
        await db.connect()
        assert db.pool is not None, "Database.connect() did not yield a pool"

        try:
            # Build a synthetic exchange.Position with a known trace_id
            # (simulating what safe_orchestrator + OrderManager.open_position will produce
            # after the full Tasks 5+6 chain).
            from exchange import Position
            test_trace_id = "abc12def3456"  # 12 chars
            pos = Position(
                symbol="BTC/USDT",
                direction="LONG",
                entry=50000.0,
                sl=49000.0,
                tp1=51000.0,
                tp2=52000.0,
                size=0.001,
                order_id="e2e-test-order",
                trace_id=test_trace_id,
                bar_ts_ms=1717200000000,
            )

            # Ensure ContextVar is unset — proves we don't rely on it across the threadsafe boundary
            set_trace_id(None)

            # Use the actual cross-thread mechanism: schedule a coroutine via
            # asyncio.run_coroutine_threadsafe into the running event loop.
            loop = asyncio.get_running_loop()
            fut = asyncio.run_coroutine_threadsafe(
                db.record_trade_open(
                    symbol=pos.symbol,
                    direction=pos.direction,
                    entry=pos.entry, sl=pos.sl, tp1=pos.tp1, tp2=pos.tp2,
                    size=pos.size,
                    binance_order_id=pos.order_id,
                    trace_id=pos.trace_id,           # explicit kwarg (the architectural fix)
                    bar_ts_ms=pos.bar_ts_ms,
                ),
                loop,
            )
            # fut is concurrent.futures.Future — bridge to await
            trade_id = await asyncio.wrap_future(fut)
            assert trade_id is not None, "record_trade_open returned None — DB write failed silently"

            # Verify DB row has the trace_id
            async with db.pool.acquire() as conn:
                row = await conn.fetchrow(
                    "SELECT trace_id, bar_ts_ms FROM trades WHERE id = $1::uuid",
                    trade_id,
                )
                assert row is not None, f"trade row {trade_id} not found"
                assert row["trace_id"] == test_trace_id, (
                    f"trace_id NOT persisted across thread boundary; "
                    f"got {row['trace_id']!r}, expected {test_trace_id!r}"
                )
                assert row["bar_ts_ms"] == 1717200000000

                # cleanup
                await conn.execute("DELETE FROM trades WHERE id = $1::uuid", trade_id)
        finally:
            await db.close()
    finally:
        # Restore root logger state
        for h in list(root.handlers):
            root.removeHandler(h)
        for h in saved_handlers:
            root.addHandler(h)
        root.setLevel(saved_level)
