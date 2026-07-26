"""BT-22: real Wilder ATR(14) replaces the percentage-of-price proxy.

Context. `engine/smc_v2/sl_calc.py::calc_sl` documents its `atr_15m` argument
as "current 15m ATR(14)" and multiplies it by `sl_atr_buffer`, `min_sl_atr`
and `max_sl_atr`. `safe_orchestrator` never computed an ATR -- it passed
`max(entry_price * 1%, zone_width)`. Over 2026-05-15..06-01 the real 15m
Wilder ATR(14) median is 0.305% of price trade-weighted, so that proxy is
~3.3x too large -- which turns `safety.max_sl_atr: 5.0` from "at most 5 ATRs"
(~1.5% of price) into "at most 5% of price", a ceiling that never binds.

The live evidence is in state_1k/trade_journal.jsonl. For each of 336 closed
trades the symbol's real ATR(14) was read off the last closed 15m bar before
entry and the placed stop expressed in those units. Outcome is monotone in
that ratio -- 0-2 ATR: n=54, win 100%; 2-4: n=113, win 87.6%; 4-5: n=56, win
66.1%; 5-6: n=36, win 33.3%; >12: n=8, win 0%. Replaying a 5-ATR cap keeps 223
and drops 113, taking PnL +403.74 -> +595.66 USDT and win 66.7% -> 85.2%.

Both live entry paths share `_journal_record_entry`, which hardcodes its
provenance fields to empty, so the journal cannot attribute a trade to v1 or
v2. Read the numbers as "this bot", not "this code path".

These tests pin the calculator's contract. They deliberately do NOT assert on
live config values -- `engine.v2_use_real_atr` is default-OFF and the operator
owns the decision to enable it.
"""
import math

import numpy as np
import pandas as pd
import pytest

from engine.smc_v2.atr import wilder_atr


def _frame(highs, lows, closes):
    return pd.DataFrame({"high": highs, "low": lows, "close": closes})


def _reference_wilder(df, period=14):
    """Independent re-implementation, written from the textbook definition
    rather than by copying the module under test, so a bug in the module
    cannot be mirrored into its own expected value."""
    h = df["high"].tolist()
    l = df["low"].tolist()
    c = df["close"].tolist()
    trs = []
    for i in range(1, len(h)):
        trs.append(max(h[i] - l[i], abs(h[i] - c[i - 1]), abs(l[i] - c[i - 1])))
    atr = sum(trs[:period]) / period
    for x in trs[period:]:
        atr = (atr * (period - 1) + x) / period
    return atr


def test_matches_textbook_wilder_on_a_real_shaped_series():
    rng = np.random.default_rng(20260726)
    n = 200
    close = 100 + np.cumsum(rng.normal(0, 0.4, n))
    high = close + np.abs(rng.normal(0, 0.25, n))
    low = close - np.abs(rng.normal(0, 0.25, n))
    df = _frame(high, low, close)
    got = wilder_atr(df, period=14)
    assert got == pytest.approx(_reference_wilder(df, 14), rel=1e-12)


def test_is_wilder_not_a_simple_mean():
    """engine/intent.py::_atr averages the last `period` true ranges. That is a
    different estimator, and this test pins the exact size of the difference so
    nobody can "unify" the two without the suite going red -- doing so would
    silently change what min_sl_atr and max_sl_atr mean.

    The series is built so BOTH estimators have a closed form. 80 bars with a
    constant true range of 6.0, then 20 bars with a constant true range of 0.2.
    The simple mean over the last 14 TRs is therefore exactly 0.2, while Wilder
    decays the old regime by (13/14) per bar and still carries most of it:

        ATR = 6.0 * (13/14)**20 + 0.2 * (1 - (13/14)**20) ~= 1.517

    which is 7.6x the simple mean. That gap is the whole reason this module
    exists as a separate estimator instead of reusing intent._atr."""
    hi_bars, lo_bars, period = 80, 20, 14
    close = np.concatenate([np.linspace(100.0, 130.0, hi_bars), np.full(lo_bars, 130.0)])
    half_range = np.concatenate([np.full(hi_bars, 3.0), np.full(lo_bars, 0.1)])
    high, low = close + half_range, close - half_range
    df = _frame(high, low, close)

    wilder = wilder_atr(df, period)
    simple = float(np.mean([
        max(high[i] - low[i], abs(high[i] - close[i - 1]), abs(low[i] - close[i - 1]))
        for i in range(len(close) - period, len(close))
    ]))

    decay = (1.0 - 1.0 / period) ** lo_bars
    expected = 6.0 * decay + 0.2 * (1.0 - decay)

    assert simple == pytest.approx(0.2, rel=1e-12)
    assert wilder == pytest.approx(expected, rel=1e-12)
    # Wilder still carries the early high-volatility regime; the simple mean
    # has forgotten it entirely.
    assert wilder > simple * 5.0


@pytest.mark.parametrize("n", [0, 1, 13, 14])
def test_returns_none_when_there_are_not_enough_bars(n):
    """period + 1 bars are required: the first true range needs a previous
    close, so 14 bars yield only 13 TRs and cannot seed a 14-period average."""
    df = _frame(np.full(n, 101.0), np.full(n, 99.0), np.full(n, 100.0))
    assert wilder_atr(df, period=14) is None


def test_fifteen_bars_is_exactly_enough():
    df = _frame(np.full(15, 101.0), np.full(15, 99.0), np.full(15, 100.0))
    assert wilder_atr(df, period=14) == pytest.approx(2.0)


def test_returns_none_not_zero_on_missing_or_degenerate_input():
    """None is the caller's 'fall back to previous behaviour' signal. A 0.0
    would be accepted by calc_sl as 'no volatility' and collapse the buffer and
    BOTH clamps to zero -- min_dist 0, max_dist 0 -- so every setup would raise
    SLTooFarError. Returning None instead of 0.0 is load-bearing, not stylistic."""
    assert wilder_atr(None) is None
    assert wilder_atr(pd.DataFrame({"open": range(50)})) is None          # no OHLC
    flat = _frame(np.full(50, 100.0), np.full(50, 100.0), np.full(50, 100.0))
    assert wilder_atr(flat) is None                                       # ATR == 0


def test_survives_nan_contamination_instead_of_propagating_it():
    """One NaN in the OHLC window would poison every subsequent step of the
    recursion and return NaN, which is_finite-checks nowhere downstream."""
    rng = np.random.default_rng(7)
    n = 100
    close = 100 + np.cumsum(rng.normal(0, 0.3, n))
    high, low = close + 0.5, close - 0.5
    high = high.astype(float).copy()
    high[10] = np.nan
    df = _frame(high, low, close)
    got = wilder_atr(df, 14)
    assert got is not None and math.isfinite(got) and got > 0


def test_the_proxy_it_replaces_is_materially_larger():
    """The whole point, expressed as a test: on a series with realistic 15m
    volatility (~0.35% ATR, the unweighted portfolio median over the journal
    window) the old proxy floor of 1% of price is ~3x too large, and therefore
    so is every distance derived from it."""
    rng = np.random.default_rng(11)
    n = 400
    price = 100.0
    # ~0.35% per-bar range, matching the measured portfolio median.
    close = price + np.cumsum(rng.normal(0, 0.13, n))
    high = close + np.abs(rng.normal(0, 0.13, n))
    low = close - np.abs(rng.normal(0, 0.13, n))
    real = wilder_atr(_frame(high, low, close), 14)
    proxy = float(np.mean(close)) * 1.0 / 100.0     # old: entry_price * 1%
    assert real is not None
    assert 0.2 <= real / float(np.mean(close)) * 100 <= 0.7   # sanity: it IS ~0.4%
    assert proxy > real * 1.8


def test_orchestrator_accepts_df_entry_and_defaults_it_to_none():
    """The four call sites now forward the entry frame. Any caller that does
    not (tests, future code paths) must still work -- the parameter defaults to
    None and wilder_atr(None) returns None, which restores the proxy."""
    import inspect
    from engine.safe_orchestrator import SafeOrchestrator
    sig = inspect.signature(SafeOrchestrator._place_v2_entry_order)
    assert "df_entry" in sig.parameters
    assert sig.parameters["df_entry"].default is None
