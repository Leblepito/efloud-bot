from __future__ import annotations

import re
from typing import Any

_MUTATION_RE = re.compile(r"\b(INSERT|UPDATE|DELETE|DROP|ALTER|TRUNCATE|CREATE|GRANT|REVOKE|COPY|MERGE|CALL)\b", re.IGNORECASE)


def assert_select_only(sql: str) -> None:
    """Fail closed unless SQL is a SELECT/CTE and contains no mutation verbs."""
    stripped = sql.strip()
    if not (stripped.upper().startswith("SELECT") or stripped.upper().startswith("WITH")):
        raise ValueError("Phase 0 evidence SQL must be SELECT-only")
    if _MUTATION_RE.search(stripped):
        raise ValueError("Mutation SQL is forbidden in Phase 0 evidence extraction")


def build_trade_query(since: str, symbols: list[str]) -> tuple[str, list[Any]]:
    """Build bound-parameter query for closed trades + optional trade_audits."""
    sql = """
    SELECT
        t.id::text AS trade_id,
        t.symbol,
        t.direction,
        t.entry,
        t.sl,
        t.exit,
        t.reason,
        t.pnl_usdt AS pnl,
        t.pnl_pct,
        t.size,
        t.opened_at,
        t.closed_at,
        a.entry_score,
        a.sl_score,
        a.rr_score,
        a.overall_score,
        a.outcome,
        a.notes,
        a.audited_at
    FROM trades t
    LEFT JOIN trade_audits a ON a.trade_id = t.id
    WHERE t.closed_at IS NOT NULL
      AND t.closed_at >= $1::timestamptz
      AND t.symbol = ANY($2::text[])
    ORDER BY t.closed_at ASC, t.id ASC
    """
    assert_select_only(sql)
    return sql, [since, symbols]


async def fetch_rows(database_url: str, since: str, symbols: list[str]) -> list[dict[str, Any]]:
    """Fetch evidence rows using asyncpg without ever echoing database_url."""
    import asyncpg

    sql, args = build_trade_query(since, symbols)
    conn = None
    try:
        conn = await asyncpg.connect(database_url)
        rows = await conn.fetch(sql, *args)
        return [dict(r) for r in rows]
    finally:
        if conn is not None:
            await conn.close()
