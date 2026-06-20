"""Supabase Postgres client (asyncpg pool).

Lazy pool init — DATABASE_URL env yoksa veya unreachable ise pool None,
DB-yazan fonksiyonlar no-op olur (bot çalışmaya devam eder, sadece persistence yok).
"""
from __future__ import annotations

import logging
import os
import json
from datetime import datetime
from typing import Any, Optional

import asyncpg

log = logging.getLogger("efloud.db")


class Database:
    def __init__(self) -> None:
        self.pool: Optional[asyncpg.Pool] = None
        # Multi-instance persistence (migration 012): every write is tagged with
        # this instance id and every instance-scoped read/update filters by it,
        # so two bots (V1 mid + V2 long) can share one Supabase project without
        # cross-contaminating trades or the breaker_state row. Default 'v1' =
        # byte-identical behavior for the existing single bot.
        self.bot_id: str = os.environ.get("EFLOUD_BOT_ID", "v1")

    async def connect(self) -> None:
        url = os.environ.get("DATABASE_URL")
        if not url:
            log.warning("DATABASE_URL not set — running without persistence")
            return
        try:
            self.pool = await asyncpg.create_pool(
                dsn=url, min_size=1, max_size=5, command_timeout=10,
                statement_cache_size=0,
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
        tp1: float, tp2: Optional[float], size: float, confluence: Optional[int] = None,
        binance_order_id: Optional[str] = None,
        trace_id: Optional[str] = None,        # PR #57
        bar_ts_ms: Optional[int] = None,        # PR #57
        *,
        # SMC v2 telemetry (PR #S5) — keyword-only, default None so v1 callers
        # unaffected. Migration 007 added these as nullable columns.
        entry_setup_source: Optional[str] = None,
        tp1_target_type: Optional[str] = None,
        tp2_target_type: Optional[str] = None,
        bars_to_pullback: Optional[int] = None,
        initial_sl: Optional[float] = None,
        adx_value: Optional[float] = None,
        atr_value: Optional[float] = None,
        funding_rate: Optional[float] = None,
        confluence_details: Optional[dict] = None,
    ) -> Optional[str]:
        """Insert trade with no exit yet. Returns trade UUID."""
        if not self.pool:
            return None
        try:
            conf_json = json.dumps(confluence_details, default=str) if confluence_details is not None else None
            async with self.pool.acquire() as conn:
                # bot_id sits at $8 (right after `size`) so BOTH positional
                # contracts hold: tp2 stays $6 (start-relative) and the telemetry
                # block stays the trailing params (end-relative).
                row = await conn.fetchrow(
                    """
                    INSERT INTO trades (symbol, direction, entry, sl, tp1, tp2, size, bot_id,
                                        confluence, binance_order_id, trace_id, bar_ts_ms,
                                        entry_setup_source, tp1_target_type,
                                        tp2_target_type, bars_to_pullback,
                                        initial_sl, adx_value, atr_value,
                                        funding_rate, confluence_details)
                    VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12,
                            $13, $14, $15, $16, $17, $18, $19, $20, $21::jsonb)
                    RETURNING id::text
                    """,
                    symbol, direction, entry, sl, tp1, tp2, size, self.bot_id,
                    confluence, binance_order_id, trace_id, bar_ts_ms,
                    entry_setup_source, tp1_target_type,
                    tp2_target_type, bars_to_pullback,
                    initial_sl, adx_value, atr_value,
                    funding_rate, conf_json,
                )
                return row["id"] if row else None
        except Exception as e:
            log.warning(f"record_trade_open failed: {e}")
            return None

    async def record_trade_close(
        self, symbol: str, exit_price: float, pnl_usdt: float,
        pnl_pct: float, reason: str,
        trace_id: Optional[str] = None,       # NEW (informational; not used in WHERE)
        bar_ts_ms: Optional[int] = None,       # NEW (forward-compat; not yet used)
        *,
        mae_pct: Optional[float] = None,
        mfe_pct: Optional[float] = None,
    ) -> None:
        """Update most recent open trade for symbol with exit details."""
        if not self.pool:
            return
        try:
            async with self.pool.acquire() as conn:
                # C5: prefer trace_id when provided so the correct open row is
                # closed even when two same-symbol rows briefly coexist (reverse
                # flip / fast SL→re-entry). Falls back to symbol-only when
                # trace_id is NULL (older open-side rows). A duplicate close call
                # (reconcile double-write) then no-ops: the trace_id row is
                # already closed, so `closed_at IS NULL` excludes it.
                # bot_id ($9) is appended LAST so mae_pct/mfe_pct keep $6/$7.
                # It scopes the open-row subquery to THIS instance so V1's
                # reconcile can never close a V2 row (and vice versa).
                await conn.execute(
                    """
                    UPDATE trades
                    SET exit = $2, pnl_usdt = $3, pnl_pct = $4, reason = $5,
                        closed_at = NOW(),
                        mae_pct = COALESCE($6, mae_pct),
                        mfe_pct = COALESCE($7, mfe_pct)
                    WHERE id = (
                        SELECT id FROM trades
                        WHERE closed_at IS NULL
                          AND bot_id = $9
                          AND (($8::text IS NULL AND symbol = $1) OR trace_id = $8)
                        ORDER BY opened_at DESC LIMIT 1
                    )
                    """,
                    symbol, exit_price, pnl_usdt, pnl_pct, reason,
                    mae_pct, mfe_pct, trace_id, self.bot_id,
                )
        except Exception as e:
            log.warning(f"record_trade_close failed: {e}")

    async def update_trade_kronos_data(self, trade_id: str, comment: str, confidence: int) -> None:
        """Update a trade row with Kronos AI forecast commentary and confidence."""
        if not self.pool:
            return
        try:
            async with self.pool.acquire() as conn:
                await conn.execute(
                    """
                    UPDATE trades
                    SET kronos_comment = $2, kronos_confidence = $3
                    WHERE id = $1::uuid
                    """,
                    trade_id, comment, confidence
                )
        except Exception as e:
            log.warning(f"update_trade_kronos_data failed: {e}")

    async def fetch_recent_trades(self, limit: int = 50) -> list[dict[str, Any]]:
        if not self.pool:
            return []
        try:
            async with self.pool.acquire() as conn:
                rows = await conn.fetch(
                    """
                    SELECT id::text, symbol, direction, entry, exit, sl, tp1, tp2,
                           size, pnl_usdt, pnl_pct, reason, opened_at, closed_at,
                           confluence,
                           entry_setup_source, tp1_target_type,
                           tp2_target_type, bars_to_pullback,
                           mae_pct, mfe_pct, initial_sl, adx_value, atr_value,
                           funding_rate, confluence_details,
                           kronos_comment, kronos_confidence
                    FROM trades
                    WHERE bot_id = $1
                    ORDER BY opened_at DESC LIMIT $2
                    """,
                    self.bot_id, limit,
                )
                return [dict(r) for r in rows]
        except Exception as e:
            log.warning(f"fetch_recent_trades failed: {e}")
            return []

    async def fetch_trades_since(self, since_ts) -> list[dict[str, Any]]:
        """Fetch closed trades whose closed_at is >= since_ts.

        Args:
            since_ts: datetime (timezone-aware preferred).

        Returns: list of trade dicts (same shape as fetch_recent_trades).
        """
        if not self.pool:
            return []
        try:
            async with self.pool.acquire() as conn:
                rows = await conn.fetch(
                    """
                    SELECT id::text, symbol, direction, entry, exit, sl, tp1, tp2,
                           size, pnl_usdt, pnl_pct, reason, opened_at, closed_at,
                           confluence,
                           entry_setup_source, tp1_target_type,
                           tp2_target_type, bars_to_pullback,
                           mae_pct, mfe_pct, initial_sl, adx_value, atr_value,
                           funding_rate, confluence_details,
                           kronos_comment, kronos_confidence
                    FROM trades
                    WHERE bot_id = $1 AND closed_at IS NOT NULL AND closed_at >= $2
                    ORDER BY closed_at DESC
                    """,
                    self.bot_id, since_ts,
                )
                return [dict(r) for r in rows]
        except Exception as e:
            log.warning(f"fetch_trades_since failed: {e}")
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
                    "INSERT INTO equity_history (bot_id, balance, open_positions_count) "
                    "VALUES ($1, $2, $3)",
                    self.bot_id, balance, open_positions_count,
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
                    WHERE bot_id = $1 AND ts > NOW() - ($2 || ' days')::interval
                    ORDER BY ts ASC
                    """,
                    self.bot_id, str(days),
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
                # bot_id appended LAST so payload keeps its $2::jsonb cast.
                await conn.execute(
                    "INSERT INTO audit_log (event, payload, bot_id) VALUES ($1, $2::jsonb, $3)",
                    event, json.dumps(payload, default=str), self.bot_id,
                )
        except Exception as e:
            log.warning(f"log_audit failed: {e}")

    # ─────────────────────────────────────────────────────────────
    # Circuit-breaker state mirror (migration 010)
    # ─────────────────────────────────────────────────────────────
    # The file-based StateStore is the PRIMARY, full-fidelity breaker
    # persistence. This is a best-effort SUMMARY mirror in Supabase so the halt
    # status survives a total loss of the state volume (VPS rebuild, incident
    # 2026-05-15) and is queryable for observability. Per-instance row keyed on
    # bot_id (migration 012; was a constant id=1 singleton in migration 010).

    async def upsert_breaker_state(self, breaker: dict[str, Any]) -> None:
        """Mirror a CircuitBreaker.to_dict() payload into breaker_state.

        Best-effort: no-op without a pool, swallows errors so a DB hiccup never
        propagates into the trading cycle.
        """
        if not self.pool:
            return
        try:
            state = breaker.get("state", "OPEN")
            halted = state == "HALTED"
            # Reason is only meaningful while the breaker is not OPEN.
            halted_reason = breaker.get("reason") or None if state != "OPEN" else None
            halted_at = _parse_dt(breaker.get("tripped_at"))
            reset_at = _parse_dt(breaker.get("resume_at"))
            metrics = breaker.get("metrics") or {}
            daily_loss = metrics.get("daily_pct")
            weekly_loss = metrics.get("drawdown_pct")
            async with self.pool.acquire() as conn:
                # Keyed on bot_id (migration 012), NOT the old id=1 singleton —
                # so V1 and V2 each own a breaker_state row and never clobber.
                await conn.execute(
                    """
                    INSERT INTO breaker_state
                        (bot_id, daily_loss, weekly_loss, halted, halted_reason,
                         halted_at, reset_at, updated_at)
                    VALUES ($7, $1, $2, $3, $4, $5, $6, NOW())
                    ON CONFLICT (bot_id) DO UPDATE SET
                        daily_loss = EXCLUDED.daily_loss,
                        weekly_loss = EXCLUDED.weekly_loss,
                        halted = EXCLUDED.halted,
                        halted_reason = EXCLUDED.halted_reason,
                        halted_at = EXCLUDED.halted_at,
                        reset_at = EXCLUDED.reset_at,
                        updated_at = NOW()
                    """,
                    daily_loss, weekly_loss, halted, halted_reason,
                    halted_at, reset_at, self.bot_id,
                )
        except Exception as e:
            log.warning(f"upsert_breaker_state failed: {e}")

    async def load_breaker_state(self) -> Optional[dict[str, Any]]:
        """Read the mirrored breaker row, or None if absent / unavailable."""
        if not self.pool:
            return None
        try:
            async with self.pool.acquire() as conn:
                row = await conn.fetchrow(
                    """
                    SELECT daily_loss, weekly_loss, halted, halted_reason,
                           halted_at, reset_at, updated_at
                    FROM breaker_state WHERE bot_id = $1
                    """,
                    self.bot_id,
                )
                return dict(row) if row else None
        except Exception as e:
            log.warning(f"load_breaker_state failed: {e}")
            return None


def _parse_dt(value):
    """ISO-string → datetime; pass through datetime/None. Best-effort."""
    if value is None or isinstance(value, datetime):
        return value
    try:
        return datetime.fromisoformat(value)
    except (ValueError, TypeError):
        return None


# Module singleton
db = Database()
