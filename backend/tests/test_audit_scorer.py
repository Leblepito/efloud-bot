"""Tests for backend.audit.scorer."""
import pytest

from backend.audit.scorer import (
    score_entry_timing,
    score_sl_distance,
    score_rr,
    compose_overall,
    _atr,
    ENTRY_WEIGHT,
    SL_WEIGHT,
    RR_WEIGHT,
)


def _candles(highs, lows, closes=None):
    """Build minimal candle list from parallel highs/lows arrays."""
    if closes is None:
        closes = [(h + l) / 2 for h, l in zip(highs, lows)]
    return [
        {
            "open_time": i * 3600000,
            "open": (h + l) / 2,
            "high": h,
            "low": l,
            "close": c,
            "volume": 1.0,
        }
        for i, (h, l, c) in enumerate(zip(highs, lows, closes))
    ]


# ─────────────────────────────────────────────────────────────────────────────
# Entry timing
# ─────────────────────────────────────────────────────────────────────────────


def test_long_entered_at_recent_low_scores_high():
    candles = _candles(highs=[110] * 20, lows=[100] * 20)
    score = score_entry_timing("LONG", entry_price=100.5, prior_candles=candles)
    assert score >= 9.0, f"got {score}"


def test_long_entered_at_recent_high_scores_low():
    candles = _candles(highs=[110] * 20, lows=[100] * 20)
    score = score_entry_timing("LONG", entry_price=109.5, prior_candles=candles)
    assert score <= 1.0, f"got {score}"


def test_long_entered_mid_range_scores_around_5():
    candles = _candles(highs=[110] * 20, lows=[100] * 20)
    score = score_entry_timing("LONG", entry_price=105.0, prior_candles=candles)
    assert 4.5 <= score <= 5.5, f"got {score}"


def test_short_at_recent_high_scores_high():
    candles = _candles(highs=[110] * 20, lows=[100] * 20)
    score = score_entry_timing("SHORT", entry_price=109.5, prior_candles=candles)
    assert score >= 9.0, f"got {score}"


def test_short_at_recent_low_scores_low():
    candles = _candles(highs=[110] * 20, lows=[100] * 20)
    score = score_entry_timing("SHORT", entry_price=100.5, prior_candles=candles)
    assert score <= 1.0, f"got {score}"


def test_entry_no_candles_returns_neutral():
    assert score_entry_timing("LONG", 100.0, []) == 5.0


def test_entry_zero_range_returns_neutral():
    candles = _candles(highs=[100] * 20, lows=[100] * 20)
    assert score_entry_timing("LONG", 100.0, candles) == 5.0


def test_entry_unknown_direction_returns_neutral():
    candles = _candles(highs=[110] * 20, lows=[100] * 20)
    assert score_entry_timing("FLAT", 105.0, candles) == 5.0


def test_entry_below_recent_low_clamps_to_perfect():
    """Edge: entry below the recent-low (gap-down fill on LONG) — clamp not crash."""
    candles = _candles(highs=[110] * 20, lows=[100] * 20)
    score = score_entry_timing("LONG", entry_price=95.0, prior_candles=candles)
    assert score == 10.0


def test_entry_above_recent_high_clamps():
    candles = _candles(highs=[110] * 20, lows=[100] * 20)
    score = score_entry_timing("LONG", entry_price=120.0, prior_candles=candles)
    assert score == 0.0


# ─────────────────────────────────────────────────────────────────────────────
# SL distance
# ─────────────────────────────────────────────────────────────────────────────


def test_sl_in_sweet_spot_full_score():
    # ATR ~10 (range 100-110, no prev-close gaps), SL distance 10 → ratio=1.0 → 10.0
    candles = _candles(highs=[110] * 20, lows=[100] * 20, closes=[105] * 20)
    score = score_sl_distance(entry_price=105.0, sl_price=95.0, prior_candles=candles)
    assert score == 10.0, f"got {score}"


def test_sl_at_2x_atr_still_sweet_spot():
    candles = _candles(highs=[110] * 20, lows=[100] * 20, closes=[105] * 20)
    # ATR ~10, distance 20 → ratio 2.0 → still in sweet spot (10)
    score = score_sl_distance(entry_price=105.0, sl_price=85.0, prior_candles=candles)
    assert score == 10.0, f"got {score}"


def test_sl_too_tight_low_score():
    candles = _candles(highs=[110] * 20, lows=[100] * 20, closes=[105] * 20)
    # ATR ~10, distance 1 → ratio 0.1 → 0.6
    score = score_sl_distance(entry_price=105.0, sl_price=104.0, prior_candles=candles)
    assert score <= 1.0, f"got {score}"


def test_sl_too_wide_low_score():
    candles = _candles(highs=[110] * 20, lows=[100] * 20, closes=[105] * 20)
    # ATR ~10, distance 50 → ratio 5.0 → max(0, 3-1) = 2
    score = score_sl_distance(entry_price=105.0, sl_price=55.0, prior_candles=candles)
    assert score <= 3.0, f"got {score}"


def test_sl_no_candles_neutral():
    assert score_sl_distance(105.0, 95.0, []) == 5.0


def test_sl_zero_atr_neutral():
    """Flat candles → ATR = 0 → neutral score."""
    candles = _candles(highs=[100] * 20, lows=[100] * 20, closes=[100] * 20)
    assert score_sl_distance(100.0, 99.0, candles) == 5.0


def test_sl_extreme_wide_floor_at_zero():
    candles = _candles(highs=[110] * 20, lows=[100] * 20, closes=[105] * 20)
    # ATR ~10, distance 200 → ratio 20 → 3 - 16 = -13 → clamped to 0
    score = score_sl_distance(entry_price=105.0, sl_price=-95.0, prior_candles=candles)
    assert score == 0.0


# ─────────────────────────────────────────────────────────────────────────────
# R:R score
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("rr,expected", [
    (0.5, 0),
    (0.79, 0),
    (0.8, 3),
    (0.9, 3),
    (1.0, 6),
    (1.4, 6),
    (1.5, 8),
    (1.9, 8),
    (2.0, 10),
    (3.5, 10),
])
def test_rr_buckets(rr, expected):
    # entry 100, SL 90 (risk=10), TP1 = 100 + 10*rr (LONG)
    sl = 90.0
    tp1 = 100.0 + 10.0 * rr
    assert score_rr(100.0, sl, tp1) == expected


def test_rr_zero_risk_returns_zero():
    assert score_rr(100.0, 100.0, 110.0) == 0.0


def test_rr_short_direction_uses_abs_distance():
    # SHORT at 100, SL 110 (risk 10), TP1 90 (reward 10) → rr=1.0 → 6
    assert score_rr(100.0, 110.0, 90.0) == 6.0


# ─────────────────────────────────────────────────────────────────────────────
# Overall composer
# ─────────────────────────────────────────────────────────────────────────────


def test_overall_weighted_average():
    # 8*0.4 + 10*0.3 + 6*0.3 = 3.2 + 3.0 + 1.8 = 8.0
    assert compose_overall(8.0, 10.0, 6.0) == 8.0


def test_overall_all_zeros_clamps_to_zero():
    assert compose_overall(0, 0, 0) == 0.0


def test_overall_all_max_clamps_to_ten():
    assert compose_overall(10, 10, 10) == 10.0


def test_overall_weights_sum_to_one():
    """Sanity: if any weight drifts, overall can exceed 10."""
    assert abs((ENTRY_WEIGHT + SL_WEIGHT + RR_WEIGHT) - 1.0) < 1e-9


# ─────────────────────────────────────────────────────────────────────────────
# ATR helper (internal but tested)
# ─────────────────────────────────────────────────────────────────────────────


def test_atr_insufficient_candles_returns_zero():
    candles = _candles(highs=[110] * 5, lows=[100] * 5, closes=[105] * 5)
    assert _atr(candles, period=14) == 0.0


def test_atr_basic_computation():
    """20 candles all with high-low=10, no gaps → ATR should be ~10."""
    candles = _candles(highs=[110] * 20, lows=[100] * 20, closes=[105] * 20)
    atr = _atr(candles, period=14)
    assert abs(atr - 10.0) < 0.01


def test_atr_with_gaps_uses_max_of_three():
    """When prev_close is outside the bar range, TR uses the gap distance."""
    # Two candles: first close at 100, second has high=110 low=108 (gap up)
    candles = [
        {"open_time": 0, "open": 99, "high": 102, "low": 98, "close": 100, "volume": 1},
        {"open_time": 1, "open": 109, "high": 110, "low": 108, "close": 109, "volume": 1},
    ]
    # candle 2 TR = max(110-108, |110-100|, |108-100|) = max(2, 10, 8) = 10
    assert _atr(candles, period=1) == 10.0
