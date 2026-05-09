"""Binance public klines fetcher.

No auth needed — uses the public futures klines endpoint. Used by AuditEngine
to pull market context around a closed trade for scoring.

Failure isolation: every error returns an empty list rather than raising.
The audit engine MUST NOT propagate errors back into the trading loop.
"""
from __future__ import annotations

import logging
from typing import Any

import requests

log = logging.getLogger("efloud.audit.klines")

BINANCE_FUTURES_KLINES_URL = "https://fapi.binance.com/fapi/v1/klines"
TIMEOUT_SECONDS = 5
MAX_LIMIT = 1500  # Binance futures limit


def fetch_klines(
    symbol: str,
    interval: str,
    start_ms: int,
    end_ms: int,
    timeout: float = TIMEOUT_SECONDS,
) -> list[dict[str, Any]]:
    """Fetch klines from Binance futures public API.

    Args:
        symbol: Pure pair like "BTCUSDT" — no slash, no settlement suffix.
                Use symbol_to_binance() to convert from internal format.
        interval: Binance interval string ("1m", "5m", "15m", "1h", "4h", "1d").
        start_ms: Start time in Binance ms epoch (inclusive).
        end_ms: End time in Binance ms epoch (inclusive).
        timeout: Request timeout in seconds. Default 5s.

    Returns:
        List of {open_time, open, high, low, close, volume} dicts in chronological
        order. Empty list on any failure (HTTP error, network exception, JSON parse).

    Never raises.
    """
    params = {
        "symbol": symbol,
        "interval": interval,
        "startTime": start_ms,
        "endTime": end_ms,
        "limit": MAX_LIMIT,
    }
    try:
        resp = requests.get(BINANCE_FUTURES_KLINES_URL, params=params, timeout=timeout)
        if resp.status_code != 200:
            log.warning(
                "klines fetch failed: %s status=%s body=%s",
                symbol,
                resp.status_code,
                resp.text[:200] if hasattr(resp, "text") else "",
            )
            return []
        rows = resp.json()
    except Exception as e:
        log.warning("klines fetch exception %s: %s", symbol, e)
        return []

    return [
        {
            "open_time": int(r[0]),
            "open": float(r[1]),
            "high": float(r[2]),
            "low": float(r[3]),
            "close": float(r[4]),
            "volume": float(r[5]),
        }
        for r in rows
    ]


def symbol_to_binance(symbol: str) -> str:
    """Convert internal 'BTC/USDT' or 'BTC/USDT:USDT' to Binance 'BTCUSDT'."""
    return symbol.split(":")[0].replace("/", "")
