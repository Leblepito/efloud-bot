"""Deterministic trade-quality scorers.

Pure functions, zero I/O. All scorers return float in [0, 10].

Three primary scorers:
    score_entry_timing(direction, entry_price, prior_candles)
    score_sl_distance(entry_price, sl_price, prior_candles)
    score_rr(entry_price, sl_price, tp1_price)

And a composer:
    compose_overall(entry, sl, rr) → weighted average

Helper:
    _atr(candles, period=14) — Average True Range. Internal but exported for
    AuditEngine notes payload re-use.
"""
from __future__ import annotations

from typing import Any

# ─────────────────────────────────────────────────────────────────────────────
# Score weights for the overall composite
# Tunable later if data shows different weights are more predictive of outcome.
# ─────────────────────────────────────────────────────────────────────────────
ENTRY_WEIGHT = 0.4
SL_WEIGHT = 0.3
RR_WEIGHT = 0.3


def score_entry_timing(
    direction: str,
    entry_price: float,
    prior_candles: list[dict[str, Any]],
) -> float:
    """Score 0-10 based on entry position within recent range.

    LONG entered near recent low → high score.
    SHORT entered near recent high → high score.
    Mid-range entries score ~5.

    Args:
        direction: "LONG" or "SHORT". Anything else → neutral 5.0.
        entry_price: Filled entry price.
        prior_candles: List of kline dicts (from fetch_klines), chronological,
                       covering ~20 candles BEFORE entry. Empty list → neutral 5.0.

    Returns:
        Float in [0.0, 10.0], rounded to 2 decimals.
    """
    if not prior_candles:
        return 5.0
    recent_low = min(c["low"] for c in prior_candles)
    recent_high = max(c["high"] for c in prior_candles)
    range_ = recent_high - recent_low
    if range_ <= 0:
        return 5.0
    pos = (entry_price - recent_low) / range_  # 0 = at low, 1 = at high
    pos = max(0.0, min(1.0, pos))  # clamp (entry could be outside range due to gap)
    if direction == "LONG":
        return round((1.0 - pos) * 10.0, 2)
    elif direction == "SHORT":
        return round(pos * 10.0, 2)
    else:
        return 5.0


def score_sl_distance(
    entry_price: float,
    sl_price: float,
    prior_candles: list[dict[str, Any]],
) -> float:
    """Score 0-10 based on SL distance / 14-period ATR ratio.

    Sweet spot: 1.0-2.5x ATR → 10. Too tight (<0.5x) or too wide (>4x) → 0-3.

    Curve (linear interpolation):
        ratio < 0.5         → ratio * 6                  (0 → 3)
        0.5 ≤ ratio < 1.0   → 3 + (ratio - 0.5) * 14     (3 → 10)
        1.0 ≤ ratio ≤ 2.5   → 10                          (sweet spot)
        2.5 < ratio ≤ 4.0   → 10 - (ratio - 2.5) * 4.67  (10 → 3)
        ratio > 4.0         → max(0, 3 - (ratio - 4.0))   (declining to 0)

    Args:
        entry_price: Filled entry price.
        sl_price: Stop-loss price.
        prior_candles: ≥15 candles before entry for ATR-14 computation.

    Returns:
        Float in [0.0, 10.0], rounded to 2 decimals. 5.0 if insufficient data.
    """
    if not prior_candles:
        return 5.0
    atr = _atr(prior_candles, period=14)
    if atr <= 0:
        return 5.0
    distance = abs(entry_price - sl_price)
    ratio = distance / atr

    if ratio < 0.5:
        return round(ratio * 6.0, 2)
    elif ratio < 1.0:
        return round(3.0 + (ratio - 0.5) * 14.0, 2)
    elif ratio <= 2.5:
        return 10.0
    elif ratio <= 4.0:
        return round(10.0 - (ratio - 2.5) * 4.67, 2)
    else:
        return round(max(0.0, 3.0 - (ratio - 4.0)), 2)


def score_rr(
    entry_price: float,
    sl_price: float,
    tp1_price: float,
) -> float:
    """Score 0-10 based on TP1 risk-reward ratio.

    Bucket curve:
        rr < 0.8           → 0
        0.8 ≤ rr < 1.0     → 3
        1.0 ≤ rr < 1.5     → 6
        1.5 ≤ rr < 2.0     → 8
        rr ≥ 2.0           → 10

    Args:
        entry_price: Filled entry price.
        sl_price: Stop-loss price.
        tp1_price: First take-profit price.

    Returns:
        Float in [0.0, 10.0]. Returns 0 if risk is zero (degenerate).
    """
    risk = abs(entry_price - sl_price)
    if risk <= 0:
        return 0.0
    reward = abs(tp1_price - entry_price)
    rr = reward / risk
    if rr < 0.8:
        return 0.0
    elif rr < 1.0:
        return 3.0
    elif rr < 1.5:
        return 6.0
    elif rr < 2.0:
        return 8.0
    else:
        return 10.0


def compose_overall(entry: float, sl: float, rr: float) -> float:
    """Weighted average of the three component scores.

    Default weights: entry 0.4, sl 0.3, rr 0.3.
    Result is clamped to [0, 10] and rounded to 2 decimals.
    """
    overall = entry * ENTRY_WEIGHT + sl * SL_WEIGHT + rr * RR_WEIGHT
    return round(max(0.0, min(10.0, overall)), 2)


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────


def _atr(candles: list[dict[str, Any]], period: int = 14) -> float:
    """Average True Range over the last `period` candles.

    True Range = max(
        high - low,
        |high - prev_close|,
        |low - prev_close|,
    )

    Returns 0.0 if insufficient data (need period+1 candles for period TR values).
    """
    if len(candles) < period + 1:
        return 0.0
    trs: list[float] = []
    for i in range(1, len(candles)):
        prev_close = candles[i - 1]["close"]
        h = candles[i]["high"]
        l = candles[i]["low"]
        tr = max(h - l, abs(h - prev_close), abs(l - prev_close))
        trs.append(tr)
    return sum(trs[-period:]) / period
