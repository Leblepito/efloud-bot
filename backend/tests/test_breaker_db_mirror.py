"""Database.upsert_breaker_state / load_breaker_state — best-effort DB mirror.

The file-based StateStore is the primary, full-fidelity persistence path for the
circuit breaker (see test_breaker_state_roundtrip.py). This DB mirror is a
secondary, summary-level copy in the Supabase breaker_state table (migration
010) so the halt status survives a total loss of the state volume (VPS rebuild,
2026-05-15 incident) and is queryable for observability.

Contract:
  - pool is None (no DATABASE_URL) → every method is a silent no-op. The bot
    must keep running without persistence, exactly like every other db.py method.
  - upsert is best-effort: a DB error is logged and swallowed, never raised into
    the trading cycle.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from backend.db import Database
from engine.safety.breaker import CircuitBreaker


class _FakeConn:
    def __init__(self, fetch_row=None, raise_on=None):
        self.executed: list[tuple] = []
        self.fetched: list[tuple] = []
        self._fetch_row = fetch_row
        self._raise_on = raise_on

    async def execute(self, sql, *args):
        if self._raise_on == "execute":
            raise RuntimeError("simulated DB failure")
        self.executed.append((sql, args))

    async def fetchrow(self, sql, *args):
        if self._raise_on == "fetchrow":
            raise RuntimeError("simulated DB failure")
        self.fetched.append((sql, args))
        return self._fetch_row


class _FakeAcquireCtx:
    def __init__(self, conn):
        self._conn = conn

    async def __aenter__(self):
        return self._conn

    async def __aexit__(self, *exc):
        return False


class _FakePool:
    def __init__(self, conn):
        self._conn = conn

    def acquire(self):
        return _FakeAcquireCtx(self._conn)


def _db_with(conn) -> Database:
    db = Database()
    db.pool = _FakePool(conn)
    return db


# ── no-op when no pool ────────────────────────────────────────────

async def test_upsert_noop_when_pool_none():
    db = Database()  # pool stays None
    breaker = CircuitBreaker(starting_balance=2000.0)
    # Must not raise even with no pool configured.
    await db.upsert_breaker_state(breaker.to_dict())


async def test_load_returns_none_when_pool_none():
    db = Database()
    assert await db.load_breaker_state() is None


# ── upsert maps breaker state → columns ───────────────────────────

async def test_upsert_halted_breaker_sets_halted_true_and_reason():
    conn = _FakeConn()
    db = _db_with(conn)

    breaker = CircuitBreaker(starting_balance=2000.0)
    breaker._halt("Weekly drawdown 31.00% reached limit 30%")

    await db.upsert_breaker_state(breaker.to_dict())

    assert len(conn.executed) == 1
    sql, args = conn.executed[0]
    assert "breaker_state" in sql
    # halted bool True and reason carried through somewhere in the args
    assert True in args
    assert any("Weekly drawdown" in str(a) for a in args)


async def test_upsert_open_breaker_sets_halted_false():
    conn = _FakeConn()
    db = _db_with(conn)

    breaker = CircuitBreaker(starting_balance=2000.0)
    breaker.check()  # OPEN with metrics

    await db.upsert_breaker_state(breaker.to_dict())

    sql, args = conn.executed[0]
    assert False in args
    # An OPEN breaker has no halt reason
    assert None in args


async def test_upsert_tripped_breaker_carries_reset_at():
    conn = _FakeConn()
    db = _db_with(conn)

    breaker = CircuitBreaker(starting_balance=2000.0)
    resume = datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(minutes=120)
    breaker._trip("3 consecutive losses", resume_at=resume)

    await db.upsert_breaker_state(breaker.to_dict())

    sql, args = conn.executed[0]
    # reset_at (resume timestamp) passed as a datetime arg
    assert any(isinstance(a, datetime) for a in args)


async def test_upsert_swallows_db_error():
    """Best-effort: a failing DB execute must not propagate into the caller."""
    conn = _FakeConn(raise_on="execute")
    db = _db_with(conn)
    breaker = CircuitBreaker(starting_balance=2000.0)
    # Should not raise.
    await db.upsert_breaker_state(breaker.to_dict())


# ── load returns row as dict ──────────────────────────────────────

async def test_load_returns_row_dict_when_present():
    row = {
        "halted": True,
        "halted_reason": "Weekly drawdown 31% reached limit 30%",
        "halted_at": datetime(2026, 5, 14, 10, 0, 0),
        "reset_at": None,
        "daily_loss": -2.5,
        "weekly_loss": 31.0,
        "updated_at": datetime(2026, 5, 14, 10, 0, 1),
    }
    conn = _FakeConn(fetch_row=row)
    db = _db_with(conn)

    result = await db.load_breaker_state()

    assert result is not None
    assert result["halted"] is True
    assert "Weekly drawdown" in result["halted_reason"]


async def test_load_returns_none_when_no_row():
    conn = _FakeConn(fetch_row=None)
    db = _db_with(conn)
    assert await db.load_breaker_state() is None


async def test_load_swallows_db_error_returns_none():
    conn = _FakeConn(raise_on="fetchrow")
    db = _db_with(conn)
    assert await db.load_breaker_state() is None
