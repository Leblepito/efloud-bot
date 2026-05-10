"""Regression: ``log_audit`` serializes payload as JSON string with ``$2::jsonb`` cast.

Bug history (pre-PR #30): inserting a dict directly via asyncpg into a JSONB
column raised
``DataError: invalid input for query argument $2: dict not coercible to jsonb``.
Fix: ``backend/db.py`` serializes the payload via ``json.dumps(..., default=str)``
and casts the second arg as ``$2::jsonb`` in the INSERT.

Both halves of the contract are pinned here:
  1. The 2nd positional arg passed to asyncpg is a ``str`` (JSON-encoded), not a dict.
  2. The SQL contains ``$2::jsonb`` so Postgres parses the string into JSONB.
"""
from datetime import datetime, timezone
import json
from unittest.mock import AsyncMock, MagicMock

from backend.db import Database


def _make_pool(execute_side_effect=None):
    """Build an asyncpg-style pool with a recording connection."""
    conn = MagicMock()
    if execute_side_effect is None:
        conn.execute = AsyncMock(return_value="INSERT 0 1")
    else:
        conn.execute = AsyncMock(side_effect=execute_side_effect)

    class _Acquired:
        async def __aenter__(_self):
            return conn

        async def __aexit__(_self, *_exc):
            return None

    pool = MagicMock()
    pool.acquire = lambda: _Acquired()
    pool._conn = conn  # for test assertions
    return pool


async def test_log_audit_passes_json_string_with_jsonb_cast():
    """payload (dict) → JSON string; SQL contains ``$2::jsonb``."""
    db = Database()
    db.pool = _make_pool()
    payload = {"symbol": "BTC/USDT", "side": "LONG", "amount": 0.5}

    await db.log_audit("trade_open", payload)

    db.pool._conn.execute.assert_awaited_once()
    args, _ = db.pool._conn.execute.call_args
    sql, event, encoded_payload = args

    assert "$2::jsonb" in sql, "log_audit SQL must cast payload with ::jsonb"
    assert event == "trade_open"
    assert isinstance(encoded_payload, str), \
        "asyncpg must receive payload as str (not dict) for JSONB"
    assert json.loads(encoded_payload) == payload


async def test_log_audit_serializes_datetime_via_default_str():
    """Non-JSON-native types in payload (datetime) round-trip via default=str."""
    db = Database()
    db.pool = _make_pool()
    ts = datetime(2026, 5, 9, 12, 0, tzinfo=timezone.utc)
    payload = {"event_at": ts, "symbol": "ETH/USDT"}

    await db.log_audit("position_close", payload)

    args, _ = db.pool._conn.execute.call_args
    encoded = args[2]
    parsed = json.loads(encoded)
    assert parsed["symbol"] == "ETH/USDT"
    # default=str renders datetime via its str() (ISO-like, includes offset)
    assert parsed["event_at"] == str(ts)


async def test_log_audit_no_pool_is_no_op():
    """Without a DB pool, log_audit returns silently — bot keeps running."""
    db = Database()
    db.pool = None  # simulates missing/unreachable DATABASE_URL

    # Must not raise.
    await db.log_audit("anything", {"k": "v"})


async def test_log_audit_swallows_db_exception():
    """A failing DB call is caught and logged, never propagated."""
    db = Database()
    db.pool = _make_pool(execute_side_effect=Exception("connection lost"))

    # log_audit catches the Exception inside try/except and only warns.
    await db.log_audit("trade_open", {"k": "v"})

    db.pool._conn.execute.assert_awaited_once()
