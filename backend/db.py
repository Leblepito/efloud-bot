"""Supabase Postgres client (asyncpg pool).

Lazy pool init — DATABASE_URL env yoksa veya unreachable ise pool None,
DB-yazan fonksiyonlar no-op olur (bot çalışmaya devam eder, sadece persistence yok).
"""
from __future__ import annotations

import logging
import os
from typing import Any, Optional

import asyncpg

log = logging.getLogger("efloud.db")


class Database:
    def __init__(self) -> None:
        self.pool: Optional[asyncpg.Pool] = None

    async def connect(self) -> None:
        url = os.environ.get("DATABASE_URL")
        if not url:
            log.warning("DATABASE_URL not set — running without persistence")
            return
        try:
            self.pool = await asyncpg.create_pool(
                dsn=url, min_size=1, max_size=5, command_timeout=10,
            )
            log.info("✅ Postgres pool ready")
        except Exception as e:
            log.error(f"DB pool init failed: {e} — continuing without persistence")
            self.pool = None

    async def close(self) -> None:
        if self.pool:
            await self.pool.close()
            self.pool = None

    # ─────────────────────────────────────────────────────────────
    # Trade persistence
    # ─────────────────────────────────────────────────────────────

    async def record_trade_open(
        self, symbol: str, direction: str, entry: float, sl: float,
        tp1: float, tp2: float, size: float, confluence: Optional[int] = None,
        binance_order_id: Optional[str] = None,
    ) -> Optional[str]:
        """Insert trade with no exit yet. Returns trade UUID."""
        if not self.pool:
            return None
        try:
            async with self.pool.acquire() as conn:
                row = await conn.fetchrow(
                    """
                    INSERT INTO trades (symbol, direction, entry, sl, tp1, tp2, size,
                                        confluence, binance_order_id)
                    VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
                    RETURNING id::text
                    """,
                    symbol, direction, entry, sl, tp1, tp2, size,
                    confluence, binance_order_id,
                )
                return row["id"] if row else None
        except Exception as e:
            log.warning(f"record_trade_open failed: {e}")
            return None

    async def record_trade_close(
        self, symbol: str, exit_price: float, pnl_usdt: float,
        pnl_pct: float, reason: str,
    ) -> None:
        """Update most recent open trade for symbol with exit details."""
        if not self.pool:
            return
        try:
            async with self.pool.acquire() as conn:
                await conn.execute(
                    """
                    UPDATE trades
                    SET exit = $2, pnl_usdt = $3, pnl_pct = $4, reason = $5,
                        closed_at = NOW()
                    WHERE id = (
                        SELECT id FROM trades
                        WHERE symbol = $1 AND closed_at IS NULL
                        ORDER BY opened_at DESC LIMIT 1
                    )
                    """,
                    symbol, exit_price, pnl_usdt, pnl_pct, reason,
                )
        except Exception as e:
            log.warning(f"record_trade_close failed: {e}")

    async def fetch_recent_trades(self, limit: int = 50) -> list[dict[str, Any]]:
        if not self.pool:
            return []
        try:
            async with self.pool.acquire() as conn:
                rows = await conn.fetch(
                    """
                    SELECT id::text, symbol, direction, entry, exit, sl, tp1, tp2,
                           size, pnl_usdt, pnl_pct, reason, opened_at, closed_at,
                           confluence
                    FROM trades
                    ORDER BY opened_at DESC LIMIT $1
                    """,
                    limit,
                )
                return [dict(r) for r in rows]
        except Exception as e:
            log.warning(f"fetch_recent_trades failed: {e}")
            return []

    # ─────────────────────────────────────────────────────────────
    # Equity tracking
    # ─────────────────────────────────────────────────────────────

    async def record_equity_snapshot(
        self, balance: float, open_positions_count: int,
    ) -> None:
        if not self.pool:
            return
        try:
            async with self.pool.acquire() as conn:
                await conn.execute(
                    "INSERT INTO equity_history (balance, open_positions_count) VALUES ($1, $2)",
                    balance, open_positions_count,
                )
        except Exception as e:
            log.warning(f"record_equity_snapshot failed: {e}")

    async def fetch_equity_history(self, days: int = 7) -> list[dict[str, Any]]:
        if not self.pool:
            return []
        try:
            async with self.pool.acquire() as conn:
                rows = await conn.fetch(
                    """
                    SELECT ts, balance, open_positions_count
                    FROM equity_history
                    WHERE ts > NOW() - ($1 || ' days')::interval
                    ORDER BY ts ASC
                    """,
                    str(days),
                )
                return [dict(r) for r in rows]
        except Exception as e:
            log.warning(f"fetch_equity_history failed: {e}")
            return []

    # ─────────────────────────────────────────────────────────────
    # Audit log
    # ─────────────────────────────────────────────────────────────

    async def log_audit(self, event: str, payload: dict[str, Any]) -> None:
        if not self.pool:
            return
        try:
            async with self.pool.acquire() as conn:
                await conn.execute(
                    "INSERT INTO audit_log (event, payload) VALUES ($1, $2)",
                    event, payload,
                )
        except Exception as e:
            log.warning(f"log_audit failed: {e}")


# Module singleton
db = Database()
