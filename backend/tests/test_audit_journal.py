"""Tests for backend.audit.journal.AuditEngine."""
import asyncio
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.audit.journal import AuditEngine, RECENT_CLOSE_WINDOW_SECONDS


# ─────────────────────────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────────────────────────


def _make_position(symbol="BTC/USDT:USDT", direction="LONG", entry=65000.0,
                   sl=64000.0, tp1=66000.0, tp2=67000.0,
                   trace_id="trace-abc", opened_at="2026-05-09T10:00:00+00:00"):
    return SimpleNamespace(
        symbol=symbol, direction=direction, entry=entry, sl=sl,
        tp1=tp1, tp2=tp2, size=0.1, trace_id=trace_id, opened_at=opened_at,
    )


def _make_trade_row(id_="trade-uuid-1", symbol="BTC/USDT", direction="LONG",
                    entry=65000.0, sl=64000.0, tp1=66000.0, tp2=67000.0,
                    reason="TP1", trace_id="trace-abc",
                    opened_at=None, closed_at=None):
    return {
        "id": id_,
        "symbol": symbol,
        "direction": direction,
        "entry": entry,
        "sl": sl,
        "tp1": tp1,
        "tp2": tp2,
        "size": 0.1,
        "reason": reason,
        "trace_id": trace_id,
        "opened_at": opened_at or datetime(2026, 5, 9, 10, 0, tzinfo=timezone.utc),
        "closed_at": closed_at or datetime(2026, 5, 9, 11, 0, tzinfo=timezone.utc),
    }


def _fake_candles(n=24, low=64000.0, high=66000.0):
    """Build n 1h candles with the given low/high range for ATR-meaningful data."""
    return [
        {
            "open_time": i * 3600 * 1000,
            "open": (low + high) / 2,
            "high": high,
            "low": low,
            "close": (low + high) / 2,
            "volume": 100.0,
        }
        for i in range(n)
    ]


def _make_pool(fetch_trade_result=None, persist_ok=True):
    """Build a MagicMock asyncpg-style pool with controllable fetchrow + execute."""
    conn = MagicMock()
    conn.fetchrow = AsyncMock(return_value=fetch_trade_result)
    conn.execute = AsyncMock(return_value="INSERT 0 1")

    # acquire() returns an async context manager yielding `conn`
    class _Acquired:
        async def __aenter__(self_inner):
            return conn

        async def __aexit__(self_inner, *_):
            return None

    pool = MagicMock()
    pool.acquire = lambda: _Acquired()
    pool._mock_conn = conn  # for assertions
    return pool


# ─────────────────────────────────────────────────────────────────────────────
# End-to-end happy path
# ─────────────────────────────────────────────────────────────────────────────


def test_score_closed_trade_e2e_happy_path():
    pool = _make_pool(fetch_trade_result=_make_trade_row())
    engine = AuditEngine(pool)
    position = _make_position()

    with patch("backend.audit.journal.fetch_klines", return_value=_fake_candles()):
        verdict = asyncio.run(engine.score_closed_trade(position))

    assert verdict is not None
    assert 0 <= verdict["entry_score"] <= 10
    assert 0 <= verdict["sl_score"] <= 10
    assert 0 <= verdict["rr_score"] <= 10
    assert 0 <= verdict["overall_score"] <= 10
    assert verdict["outcome"] == "TP1"
    assert verdict["trade_id"] == "trade-uuid-1"
    assert "atr_14h" in verdict["notes"]
    assert verdict["notes"]["candle_count"] == 24


def test_score_closed_trade_persist_called_with_correct_args():
    pool = _make_pool(fetch_trade_result=_make_trade_row())
    engine = AuditEngine(pool)
    position = _make_position()

    with patch("backend.audit.journal.fetch_klines", return_value=_fake_candles()):
        asyncio.run(engine.score_closed_trade(position))

    conn = pool._mock_conn
    # 2 calls expected: 1 fetchrow (tier-1 trace_id), 1 execute (insert audit)
    assert conn.execute.called
    args = conn.execute.call_args.args
    sql = args[0]
    assert "INSERT INTO trade_audits" in sql
    assert args[1] == "trade-uuid-1"  # trade_id


# ─────────────────────────────────────────────────────────────────────────────
# Failure isolation: never raises
# ─────────────────────────────────────────────────────────────────────────────


def test_score_closed_trade_swallows_db_exception():
    """If fetchrow raises, score_closed_trade returns None — does not propagate."""
    conn = MagicMock()
    conn.fetchrow = AsyncMock(side_effect=Exception("DB connection lost"))

    class _Acquired:
        async def __aenter__(self_inner):
            return conn
        async def __aexit__(self_inner, *_):
            return None

    pool = MagicMock()
    pool.acquire = lambda: _Acquired()

    engine = AuditEngine(pool)
    result = asyncio.run(engine.score_closed_trade(_make_position()))
    assert result is None


def test_score_closed_trade_swallows_klines_exception():
    pool = _make_pool(fetch_trade_result=_make_trade_row())
    engine = AuditEngine(pool)

    with patch("backend.audit.journal.fetch_klines", side_effect=Exception("network")):
        result = asyncio.run(engine.score_closed_trade(_make_position()))

    assert result is None


def test_score_closed_trade_no_pool_returns_none():
    engine = AuditEngine(pool=None)
    result = asyncio.run(engine.score_closed_trade(_make_position()))
    assert result is None


def test_score_closed_trade_empty_klines_returns_none():
    pool = _make_pool(fetch_trade_result=_make_trade_row())
    engine = AuditEngine(pool)

    with patch("backend.audit.journal.fetch_klines", return_value=[]):
        result = asyncio.run(engine.score_closed_trade(_make_position()))

    # Returns None because we have no klines to score against
    assert result is None


# ─────────────────────────────────────────────────────────────────────────────
# Tier-1: trace_id match
# ─────────────────────────────────────────────────────────────────────────────


def test_fetch_trade_tier1_uses_trace_id():
    pool = _make_pool(fetch_trade_result=_make_trade_row())
    engine = AuditEngine(pool)

    with patch("backend.audit.journal.fetch_klines", return_value=_fake_candles()):
        asyncio.run(engine.score_closed_trade(_make_position(trace_id="my-trace")))

    # First fetchrow call is the trace_id query
    conn = pool._mock_conn
    first_call = conn.fetchrow.call_args_list[0]
    sql = first_call.args[0]
    assert "trace_id" in sql.lower()
    assert first_call.args[1] == "my-trace"


# ─────────────────────────────────────────────────────────────────────────────
# Tier-2: symbol fallback when no trace_id match
# ─────────────────────────────────────────────────────────────────────────────


def test_fetch_trade_tier2_recent_close_accepted():
    """No trace_id match, but symbol-recent match within window → accept."""
    recent_close = datetime.now(timezone.utc) - timedelta(seconds=60)
    trade = _make_trade_row(closed_at=recent_close, trace_id=None)

    conn = MagicMock()
    conn.fetchrow = AsyncMock(side_effect=[
        None,        # tier-1 trace_id miss
        trade,       # tier-2 symbol hit
    ])
    conn.execute = AsyncMock(return_value="INSERT 0 1")

    class _Acquired:
        async def __aenter__(self_inner): return conn
        async def __aexit__(self_inner, *_): return None

    pool = MagicMock()
    pool.acquire = lambda: _Acquired()

    engine = AuditEngine(pool)
    with patch("backend.audit.journal.fetch_klines", return_value=_fake_candles()):
        verdict = asyncio.run(engine.score_closed_trade(_make_position(trace_id="missing")))

    assert verdict is not None  # tier-2 accepted recent close


def test_fetch_trade_tier2_stale_close_rejected():
    """Symbol match but closed too long ago → reject."""
    stale_close = datetime.now(timezone.utc) - timedelta(seconds=RECENT_CLOSE_WINDOW_SECONDS + 100)
    trade = _make_trade_row(closed_at=stale_close, trace_id=None)

    conn = MagicMock()
    conn.fetchrow = AsyncMock(side_effect=[None, trade])
    conn.execute = AsyncMock()

    class _Acquired:
        async def __aenter__(self_inner): return conn
        async def __aexit__(self_inner, *_): return None

    pool = MagicMock()
    pool.acquire = lambda: _Acquired()

    engine = AuditEngine(pool)
    with patch("backend.audit.journal.fetch_klines", return_value=_fake_candles()):
        result = asyncio.run(engine.score_closed_trade(_make_position(trace_id="missing")))

    assert result is None
    assert not conn.execute.called  # never reached persist


def test_fetch_trade_tier3_no_matches_returns_none():
    pool = _make_pool(fetch_trade_result=None)  # both queries return None
    engine = AuditEngine(pool)

    result = asyncio.run(engine.score_closed_trade(_make_position(trace_id=None)))
    assert result is None


# ─────────────────────────────────────────────────────────────────────────────
# Outcome / notes
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("reason,expected_outcome", [
    ("TP1", "TP1"),
    ("tp2", "TP2"),  # uppercased
    ("SL", "SL"),
    ("WEAKNESS", "WEAKNESS"),
    (None, "OTHER"),
    ("", "OTHER"),
])
def test_outcome_normalized_uppercase(reason, expected_outcome):
    pool = _make_pool(fetch_trade_result=_make_trade_row(reason=reason))
    engine = AuditEngine(pool)

    with patch("backend.audit.journal.fetch_klines", return_value=_fake_candles()):
        verdict = asyncio.run(engine.score_closed_trade(_make_position()))

    assert verdict["outcome"] == expected_outcome


def test_notes_payload_includes_market_context():
    pool = _make_pool(fetch_trade_result=_make_trade_row())
    engine = AuditEngine(pool)

    with patch("backend.audit.journal.fetch_klines", return_value=_fake_candles()):
        verdict = asyncio.run(engine.score_closed_trade(_make_position()))

    notes = verdict["notes"]
    assert "atr_14h" in notes
    assert "recent_low" in notes
    assert "recent_high" in notes
    assert "candle_count" in notes
    assert "trace_id_used" in notes
    assert notes["trace_id_used"] is True


# ─────────────────────────────────────────────────────────────────────────────
# Persist UPSERT semantics
# ─────────────────────────────────────────────────────────────────────────────


def test_persist_uses_upsert_on_trade_id():
    pool = _make_pool(fetch_trade_result=_make_trade_row())
    engine = AuditEngine(pool)

    with patch("backend.audit.journal.fetch_klines", return_value=_fake_candles()):
        asyncio.run(engine.score_closed_trade(_make_position()))

    sql = pool._mock_conn.execute.call_args.args[0]
    assert "ON CONFLICT (trade_id)" in sql
    assert "DO UPDATE" in sql


# ── B-10 (2026-07-17): fetch_klines event loop'u bloklamaz ──────────────────

def test_fetch_klines_runs_off_the_event_loop():
    """Senkron requests.get loop üzerinde koşunca her kapanışta 5-10 sn tüm
    FastAPI/WS/healthz donuyordu — artık executor thread'inde koşmalı."""
    import threading

    pool = _make_pool(fetch_trade_result=_make_trade_row())
    engine = AuditEngine(pool)
    position = _make_position()
    seen = {}

    def spy_klines(*a, **k):
        seen["thread"] = threading.get_ident()
        return _fake_candles()

    with patch("backend.audit.journal.fetch_klines", side_effect=spy_klines):
        async def scenario():
            loop_thread = threading.get_ident()
            verdict = await engine.score_closed_trade(position)
            return loop_thread, verdict
        loop_thread, verdict = asyncio.run(scenario())

    assert verdict is not None
    assert seen.get("thread") is not None
    assert seen["thread"] != loop_thread, "fetch_klines hâlâ loop thread'inde"
