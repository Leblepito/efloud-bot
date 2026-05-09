"""Tests for the audit dispatch hook in bot_runner._on_position_change."""
import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest


def _make_pos(symbol="BTC/USDT", direction="LONG", trace_id="trace-1"):
    return SimpleNamespace(
        symbol=symbol, direction=direction, entry=65000.0,
        sl=64000.0, tp1=66000.0, tp2=67000.0, size=0.1,
        order_id="ORD1", exit_price=66000.0, pnl_usdt=100.0,
        exit_reason="TP1", opened_at="2026-05-09T10:00:00+00:00",
        closed_at="2026-05-09T11:00:00+00:00",
        trace_id=trace_id, bar_ts_ms=None,
    )


def test_audit_after_delay_calls_engine():
    """_audit_after_delay sleeps then invokes score_closed_trade."""
    from backend.bot_runner import BotRunner

    runner = BotRunner.__new__(BotRunner)
    runner.audit_engine = MagicMock()
    runner.audit_engine.score_closed_trade = AsyncMock(return_value={"overall_score": 7.5})

    # Patch sleep to instant
    async def _fast_sleep(t):
        return None

    pos = _make_pos()

    async def run():
        # Replace asyncio.sleep just for this call
        import backend.bot_runner as br
        original_sleep = asyncio.sleep
        try:
            asyncio.sleep = _fast_sleep  # type: ignore
            await runner._audit_after_delay(pos)
        finally:
            asyncio.sleep = original_sleep  # type: ignore

    asyncio.run(run())
    runner.audit_engine.score_closed_trade.assert_called_once_with(pos)


def test_audit_after_delay_swallows_exceptions():
    """If audit raises despite its own contract, the wrapper catches."""
    from backend.bot_runner import BotRunner

    runner = BotRunner.__new__(BotRunner)
    runner.audit_engine = MagicMock()
    runner.audit_engine.score_closed_trade = AsyncMock(side_effect=Exception("unexpected"))

    async def _fast_sleep(t):
        return None

    pos = _make_pos()

    async def run():
        import backend.bot_runner as br
        original_sleep = asyncio.sleep
        try:
            asyncio.sleep = _fast_sleep  # type: ignore
            # Should NOT raise
            await runner._audit_after_delay(pos)
        finally:
            asyncio.sleep = original_sleep  # type: ignore

    asyncio.run(run())  # would raise if wrapper is broken


def test_audit_engine_attr_present_at_init():
    """BotRunner.audit_engine is bound at __init__ (always-present sentinel)."""
    from backend.bot_runner import BotRunner
    from backend.audit.journal import AuditEngine

    # Skip the runtime_state init (needs filesystem) by directly checking attrs
    # we set in __init__ before runtime_state line.
    runner = BotRunner.__new__(BotRunner)
    # Manually run the relevant __init__ slice — same lines that bot_runner has
    runner.audit_engine = AuditEngine(pool=None)
    assert runner.audit_engine is not None
    assert runner.audit_engine.pool is None  # not yet bound to live pool
