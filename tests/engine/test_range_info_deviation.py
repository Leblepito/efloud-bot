"""range_info deviation detection must be REACHABLE (bug-hunt #5).

Pre-fix: range_info computed hi/lo over `df.iloc[-lb:]`, a window that INCLUDES the
current bar (df.iloc[-1]). Since lo = min over a set containing ll and hi = max over
a set containing lh, `ll < lo` and `lh > hi` were mathematically impossible, so
dev_bull / dev_bear were ALWAYS False — the entire range-deviation play (tight SL,
EQ-as-TP1, opposite-extreme TP2, +5 confluence) was dead code. Fix: exclude the
current bar from the range extremes so a recent bar can pierce-and-revert.
"""
import pandas as pd

from engine.smc import SMCEngine


def _eng():
    return SMCEngine()  # range_lb=50 default


def test_bear_deviation_detected_when_last_bar_sweeps_high_and_closes_inside():
    eng = _eng()
    # Prior 20 bars: range high 101 / low 99. Last bar spikes to 102 (sweep) and
    # closes back at 100 (inside the range, below the prior high).
    df = pd.DataFrame({
        "high":  [101.0] * 20 + [102.0],
        "low":   [99.0] * 20 + [99.5],
        "close": [100.0] * 20 + [100.0],
    })
    ri = eng.range_info(df)
    assert ri.hi == 101.0 and ri.lo == 99.0   # extremes from PRIOR bars only
    assert ri.dev_bear is True                 # lh 102 > hi 101 and lc 100 < hi 101
    assert ri.dev_bull is False


def test_bull_deviation_detected_when_last_bar_sweeps_low_and_closes_inside():
    eng = _eng()
    df = pd.DataFrame({
        "high":  [101.0] * 20 + [100.5],
        "low":   [99.0] * 20 + [98.0],   # last bar wicks below the prior low
        "close": [100.0] * 20 + [100.0], # closes back inside (above prior low)
    })
    ri = eng.range_info(df)
    assert ri.hi == 101.0 and ri.lo == 99.0
    assert ri.dev_bull is True                 # ll 98 < lo 99 and lc 100 > lo 99
    assert ri.dev_bear is False


def test_no_deviation_when_last_bar_stays_inside():
    eng = _eng()
    df = pd.DataFrame({
        "high":  [101.0] * 21,
        "low":   [99.0] * 21,
        "close": [100.0] * 21,
    })
    ri = eng.range_info(df)
    assert ri.dev_bull is False
    assert ri.dev_bear is False


def test_single_bar_df_does_not_crash_and_no_deviation():
    eng = _eng()
    df = pd.DataFrame({"high": [101.0], "low": [99.0], "close": [100.0]})
    ri = eng.range_info(df)   # must not raise
    assert ri.dev_bull is False
    assert ri.dev_bear is False
