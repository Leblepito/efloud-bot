"""Compare live bot trades against backtest output for reconciliation.

Two-layer reconciliation:
    A) Trade matching: pair live trades to backtest trades by (symbol, direction, time)
    B) PnL drift: compute drift_pct per matched pair, aggregate

Real execution requires:
    - DATABASE_URL env var (Supabase pooler URL)
    - BINANCE_API_KEY + BINANCE_API_SECRET env vars (read-only permissions sufficient)

For testing: pass `live_trades=` and `backtest_trades=` directly to `reconcile()`.
"""
from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

import statistics

from backtest.slippage import SlippageConfig


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _parse_dt(value) -> datetime:
    """Parse ISO string or datetime to UTC-aware datetime.

    Handles 'Z', '+00:00', and arbitrary offsets correctly.
    Naive inputs are assumed UTC (Supabase TIMESTAMPTZ comes through as tz-aware,
    but defensive against pre-processing that might strip tz).
    """
    if isinstance(value, datetime):
        return value.astimezone(timezone.utc) if value.tzinfo else value.replace(tzinfo=timezone.utc)
    # Python 3.11+ fromisoformat handles 'Z' natively; pre-3.11 needs the swap
    s_norm = str(value).replace("Z", "+00:00")
    dt = datetime.fromisoformat(s_norm)
    return dt.astimezone(timezone.utc) if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _get_pnl(trade: dict, *, is_live: bool) -> Optional[float]:
    """Read pnl with explicit presence check (don't conflate 0.0 with absent).

    Live trades use pnl_usdt (Supabase schema); backtest uses pnl. We try the
    type-appropriate key first, then fall back to the other for tolerance.
    """
    primary = "pnl_usdt" if is_live else "pnl"
    fallback = "pnl" if is_live else "pnl_usdt"
    if primary in trade and trade[primary] is not None:
        return float(trade[primary])
    if fallback in trade and trade[fallback] is not None:
        return float(trade[fallback])
    return None


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def reconcile(
    live_trades: list[dict],
    backtest_trades: list[dict],
    *,
    match_window_hours: float = 2.0,
    drift_threshold_pct: float = 5.0,
) -> dict[str, Any]:
    """Reconcile live trades against backtest trades.

    Args:
        live_trades: list of dicts with keys (symbol, direction, opened_at, pnl_usdt OR pnl, ...)
        backtest_trades: list of dicts from run_backtest's result["trades"]
        match_window_hours: max time gap between matched trades (default 2h)
        drift_threshold_pct: if mean drift exceeds this, emit calibration recommendation

    Returns: reconciliation dict (see module docstring).
    """
    window = timedelta(hours=match_window_hours)

    # Sort live trades by opened_at (greedy from earliest)
    sorted_live = sorted(live_trades, key=lambda t: _parse_dt(t["opened_at"]))

    # Build a pool of available (unmatched) backtest trades per (symbol, direction)
    bt_pool: dict[tuple[str, str], list[tuple[int, dict]]] = {}
    for idx, bt in enumerate(backtest_trades):
        key = (bt["symbol"], bt["direction"])
        bt_pool.setdefault(key, []).append((idx, bt))

    matched_pairs: list[tuple[dict, dict]] = []
    used_bt_indices: set[int] = set()
    unmatched_live: list[dict] = []

    for live in sorted_live:
        key = (live["symbol"], live["direction"])
        candidates = bt_pool.get(key, [])

        live_dt = _parse_dt(live["opened_at"])
        best_idx: Optional[int] = None
        best_bt: Optional[dict] = None
        best_gap: Optional[timedelta] = None

        for bt_idx, bt in candidates:
            if bt_idx in used_bt_indices:
                continue
            bt_dt = _parse_dt(bt["opened_at"])
            gap = abs(live_dt - bt_dt)
            if gap <= window:
                if best_gap is None or gap < best_gap:
                    best_gap = gap
                    best_idx = bt_idx
                    best_bt = bt

        if best_bt is not None:
            used_bt_indices.add(best_idx)
            matched_pairs.append((live, best_bt))
        else:
            unmatched_live.append(live)

    # All backtest trades not matched
    used_originals = {id(bt) for _, bt in matched_pairs}
    unmatched_backtest = [bt for bt in backtest_trades if id(bt) not in used_originals]

    # Layer B: PnL drift
    per_trade_drift: list[dict] = []
    drift_values: list[float] = []

    for live, bt in matched_pairs:
        live_pnl = _get_pnl(live, is_live=True)
        bt_pnl = _get_pnl(bt, is_live=False)

        if live_pnl is None or bt_pnl is None:
            continue
        if abs(bt_pnl) < 0.01:
            # Skip near-zero to avoid divide-by-zero
            continue

        drift_pct = (live_pnl - bt_pnl) / abs(bt_pnl) * 100
        drift_usdt = live_pnl - bt_pnl
        drift_values.append(drift_pct)
        per_trade_drift.append({
            "symbol": live["symbol"],
            "live_pnl": live_pnl,
            "backtest_pnl": bt_pnl,
            "drift_pct": drift_pct,
            "drift_usdt": drift_usdt,
        })

    # Aggregate drift stats
    if drift_values:
        drift_pct_mean = statistics.mean(drift_values)
        drift_pct_median = statistics.median(drift_values)
        drift_pct_max = max(drift_values, key=abs)
    else:
        drift_pct_mean = 0.0
        drift_pct_median = 0.0
        drift_pct_max = 0.0

    # Calibration recommendation
    calibration_recommendation: Optional[dict] = None
    if abs(drift_pct_mean) > drift_threshold_pct and drift_pct_mean < 0:
        # Live worse than backtest → increase modeled slippage to match reality.
        factor = 1 + abs(drift_pct_mean) / 100
        base = SlippageConfig()
        calibration_recommendation = {
            "entry_slip_pct": base.entry_slip_pct * factor,
            "sl_slip_pct": base.sl_slip_pct * factor,
            "exit_slip_pct": base.exit_slip_pct * factor,
        }
    # (Positive drift means backtest is over-pessimistic — no slippage adjustment;
    #  consider revisiting strategy assumptions instead.)

    return {
        "live_trade_count": len(live_trades),
        "backtest_trade_count": len(backtest_trades),
        "matched_pairs": len(matched_pairs),
        "unmatched_live": unmatched_live,
        "unmatched_backtest": unmatched_backtest,
        "drift_pct_mean": drift_pct_mean,
        "drift_pct_median": drift_pct_median,
        "drift_pct_max": drift_pct_max,
        "per_trade_drift": per_trade_drift,
        "calibration_recommendation": calibration_recommendation,
    }


# ---------------------------------------------------------------------------
# Real-data fetchers (lazy imports — safe to import module without these deps)
# ---------------------------------------------------------------------------

async def fetch_live_trades(start_iso: str, end_iso: str) -> list[dict]:
    """Fetch live trades from Supabase. Requires DATABASE_URL env var."""
    import asyncpg  # Lazy import — module should be importable without asyncpg installed
    conn = await asyncpg.connect(os.environ["DATABASE_URL"])
    try:
        rows = await conn.fetch(
            "SELECT * FROM trades WHERE opened_at >= $1 AND opened_at <= $2 ORDER BY opened_at",
            datetime.fromisoformat(start_iso), datetime.fromisoformat(end_iso),
        )
        return [dict(r) for r in rows]
    finally:
        await conn.close()


def fetch_my_binance_trades(symbol: str, since_ms: int) -> list[dict]:
    """Fetch user's actual fills from Binance via CCXT.

    Requires BINANCE_API_KEY and BINANCE_API_SECRET env vars. Read-only permission is sufficient.
    """
    import ccxt  # Lazy import
    ex = ccxt.binance({
        "apiKey": os.environ["BINANCE_API_KEY"],
        "secret": os.environ["BINANCE_API_SECRET"],
        "options": {"defaultType": "future"},
    })
    return ex.fetch_my_trades(symbol, since=since_ms)


def fetch_binance_funding(symbol: str, since_ms: int) -> list[dict]:
    """Fetch funding rate history. Requires same env vars as fetch_my_binance_trades."""
    import ccxt  # Lazy import
    ex = ccxt.binance({
        "apiKey": os.environ["BINANCE_API_KEY"],
        "secret": os.environ["BINANCE_API_SECRET"],
        "options": {"defaultType": "future"},
    })
    return ex.fetch_funding_history(symbol, since=since_ms)
