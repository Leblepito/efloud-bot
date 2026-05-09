"""AuditEngine — glue layer for the post-trade audit pipeline.

Responsibilities:
    1. On `position_closed`, fetch the corresponding `trades` row by trace_id.
    2. Pull 24h of 1h klines from Binance public API for context.
    3. Compute three scores + overall via backend.audit.scorer.
    4. Persist to `trade_audits` (UPSERT on trade_id).

Failure isolation contract:
    - Never raises into the caller. Any exception → log warning, return None.
    - Bot's trading loop must NEVER be blocked or affected by audit work.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from backend.audit.klines import fetch_klines, symbol_to_binance
from backend.audit.scorer import (
    score_entry_timing,
    score_sl_distance,
    score_rr,
    compose_overall,
    _atr,
)

log = logging.getLogger("efloud.audit.journal")

# How far back to pull klines for entry-context scoring (1h interval × 24 = 24h).
PRIOR_CANDLES_HOURS = 24

# Tier-2 fallback: if no trace_id match, accept "most recent closed for symbol"
# only when it closed within this many seconds. Prevents scoring stale trades.
RECENT_CLOSE_WINDOW_SECONDS = 300  # 5 minutes


class AuditEngine:
    """Score a closed trade and persist the verdict to trade_audits."""

    def __init__(self, pool):
        """
        Args:
            pool: asyncpg.Pool — same pool used by backend.db.
                  Pass None in tests / when DB unavailable; engine no-ops gracefully.
        """
        self.pool = pool

    async def score_closed_trade(self, position) -> Optional[dict[str, Any]]:
        """Score a Position that just closed. Fire-and-forget; never raises.

        Args:
            position: Position dataclass from exchange/__init__.py with at least
                      symbol, direction, entry, sl, tp1, trace_id, opened_at fields.

        Returns:
            Verdict dict on success, None on any failure.
        """
        if self.pool is None:
            log.debug("audit: no pool, skipping")
            return None

        try:
            return await self._score_closed_trade_impl(position)
        except Exception as e:
            symbol = getattr(position, "symbol", "?")
            trace = getattr(position, "trace_id", None)
            log.warning("audit: failed for %s (trace=%s): %s", symbol, trace, e)
            return None

    async def _score_closed_trade_impl(self, position) -> Optional[dict[str, Any]]:
        """Inner method — exceptions caught by score_closed_trade's wrapper."""
        # ─── 1. Locate the trade row ──────────────────────────────────────
        trade = await self._fetch_trade(position)
        if not trade:
            return None

        # ─── 2. Fetch klines covering 24h before entry ────────────────────
        symbol_b = symbol_to_binance(trade["symbol"])
        opened_at = trade["opened_at"]
        if isinstance(opened_at, str):
            # ISO string from Position; tolerate both with-Z and offset suffix
            opened_at = datetime.fromisoformat(opened_at.replace("Z", "+00:00"))
        if opened_at.tzinfo is None:
            opened_at = opened_at.replace(tzinfo=timezone.utc)

        entry_ms = int(opened_at.timestamp() * 1000)
        start_ms = entry_ms - PRIOR_CANDLES_HOURS * 3600 * 1000

        prior_candles = fetch_klines(symbol_b, "1h", start_ms, entry_ms)
        if not prior_candles:
            log.info("audit: no prior klines for %s, skipping", symbol_b)
            return None

        # ─── 3. Compute scores ────────────────────────────────────────────
        entry_score = score_entry_timing(
            trade["direction"], float(trade["entry"]), prior_candles
        )
        sl_score = score_sl_distance(
            float(trade["entry"]), float(trade["sl"]), prior_candles
        )
        rr_score = score_rr(
            float(trade["entry"]), float(trade["sl"]), float(trade["tp1"])
        )
        overall = compose_overall(entry_score, sl_score, rr_score)

        outcome = (trade.get("reason") or "OTHER").upper()

        notes = {
            "atr_14h": round(_atr(prior_candles, period=14), 6),
            "recent_low": min(c["low"] for c in prior_candles),
            "recent_high": max(c["high"] for c in prior_candles),
            "candle_count": len(prior_candles),
            "trace_id_used": position.trace_id is not None and trade.get("trace_id") == position.trace_id,
        }

        verdict = {
            "trade_id": str(trade["id"]),
            "entry_score": entry_score,
            "sl_score": sl_score,
            "rr_score": rr_score,
            "overall_score": overall,
            "outcome": outcome,
            "notes": notes,
        }

        # ─── 4. Persist ───────────────────────────────────────────────────
        persisted = await self._persist(verdict)
        if persisted:
            log.info(
                "audit: scored %s %s — overall=%.1f (entry=%.1f sl=%.1f rr=%.1f) outcome=%s",
                trade["symbol"],
                trade["direction"],
                overall,
                entry_score,
                sl_score,
                rr_score,
                outcome,
            )
        return verdict

    async def _fetch_trade(self, position) -> Optional[dict[str, Any]]:
        """3-tier strategy to locate the trade row matching this Position.

        Tier 1: trace_id direct match (preferred).
        Tier 2: most-recent closed for symbol within RECENT_CLOSE_WINDOW.
        Tier 3: give up silently (warn-only).
        """
        symbol = position.symbol
        trace_id = getattr(position, "trace_id", None)

        async with self.pool.acquire() as conn:
            # Tier 1
            if trace_id:
                row = await conn.fetchrow(
                    """
                    SELECT * FROM trades
                    WHERE trace_id = $1
                    ORDER BY closed_at DESC NULLS LAST
                    LIMIT 1
                    """,
                    trace_id,
                )
                if row:
                    return dict(row)

            # Tier 2
            row = await conn.fetchrow(
                """
                SELECT * FROM trades
                WHERE symbol = $1 AND closed_at IS NOT NULL
                ORDER BY closed_at DESC
                LIMIT 1
                """,
                symbol,
            )
            if row:
                closed_at = row["closed_at"]
                now = datetime.now(tz=closed_at.tzinfo) if closed_at.tzinfo else datetime.utcnow()
                age = (now - closed_at).total_seconds()
                if age < RECENT_CLOSE_WINDOW_SECONDS:
                    log.info(
                        "audit: tier-2 match for %s (no trace_id, recent close %.0fs ago)",
                        symbol,
                        age,
                    )
                    return dict(row)
                else:
                    log.warning(
                        "audit: tier-2 candidate too old for %s (%.0fs > %d) — giving up",
                        symbol,
                        age,
                        RECENT_CLOSE_WINDOW_SECONDS,
                    )

            log.warning(
                "audit: could not locate trade record for %s (trace_id=%s)",
                symbol,
                trace_id,
            )
            return None

    async def _persist(self, verdict: dict[str, Any]) -> bool:
        """Insert or update the audit row. Returns True on success."""
        try:
            async with self.pool.acquire() as conn:
                await conn.execute(
                    """
                    INSERT INTO trade_audits
                        (trade_id, entry_score, sl_score, rr_score, overall_score, outcome, notes)
                    VALUES ($1, $2, $3, $4, $5, $6, $7::jsonb)
                    ON CONFLICT (trade_id) DO UPDATE SET
                        entry_score = EXCLUDED.entry_score,
                        sl_score = EXCLUDED.sl_score,
                        rr_score = EXCLUDED.rr_score,
                        overall_score = EXCLUDED.overall_score,
                        outcome = EXCLUDED.outcome,
                        notes = EXCLUDED.notes,
                        audited_at = NOW()
                    """,
                    verdict["trade_id"],
                    verdict["entry_score"],
                    verdict["sl_score"],
                    verdict["rr_score"],
                    verdict["overall_score"],
                    verdict["outcome"],
                    json.dumps(verdict["notes"]),
                )
                return True
        except Exception as e:
            log.warning("audit: persist failed: %s", e)
            return False
