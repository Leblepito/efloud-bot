"""Pure-function references for the indicator's display-only layers (spec §6.4)."""
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts import pine_lab_visuals as vis  # noqa: E402


def test_swept_pivots_requires_wick_after_confirmation_window():
    h = np.array([10, 11, 12, 11, 10, 10, 13, 10], dtype=float)
    l = h - 1
    # pivot high 12 at bar 2; swing_len 2 → sweep only counts from bar 5 on; bar 6 high 13 > 12 → swept
    assert vis.swept_pivots([(2, 12.0)], True, h, l, 2) == [True]
    assert vis.swept_pivots([(2, 14.0)], True, h, l, 2) == [False]


def test_volume_confirmed_rule():
    h = np.array([1, 2, 3, 4], dtype=float); l = h - 1
    v = np.array([5, 6, 7, 8], dtype=float); vma = np.array([7, 7, 7, 7], dtype=float)
    assert vis.volume_confirmed(3, True, h, l, v, vma) is True          # rising highs, rising vol, 8 > 7
    assert vis.volume_confirmed(2, True, h, l, v, vma) is False         # 7 > 7 fails
    assert vis.volume_confirmed(3, False, h, l, v, vma) is False        # lows are rising, not falling


def test_classify_flips_bb_vs_mb_on_bear_ob():
    # bear OB candle idx=5 top=20 bot=18, created at 7 (break), swing low pivot at bar 1 price 10 (ref A)
    from engine.smc_v2.luxalgo import LuxBreak, LuxOrderBlock
    ob = LuxOrderBlock(bar_high=20.0, bar_low=18.0, idx=5, ts="t5", bias="BEAR", internal=True, created_idx=7)
    brk = LuxBreak(kind="CHoCH", direction="BEAR", level=15.0, pivot_idx=4, idx=7, ts="t7", internal=True, order_block=ob)
    res = type("R", (), {})()
    res.breaks = [brk]; res.swing_low_pivots = [(1, 10.0)]; res.swing_high_pivots = []
    n = 12
    h = np.full(n, 19.0); l = np.full(n, 17.0); c = np.full(n, 18.5)
    l[8] = 9.0                                  # sweeps A=10 before the flip
    c[10] = 21.0                                # flip: close > top at bar 10
    out = vis.classify_flips(res, h, l, c, swing_len=1, window=750)
    assert out[0]["cls"] == "BB" and out[0]["flip"] == 10 and out[0]["dir"] == 1
    l[8] = 17.0                                 # no sweep → MB
    out = vis.classify_flips(res, h, l, c, swing_len=1, window=750)
    assert out[0]["cls"] == "MB"


def test_ote_range_direction_and_levels():
    from engine.smc_v2.luxalgo import LuxBreak, LuxOrderBlock
    ob = LuxOrderBlock(bar_high=104.0, bar_low=102.0, idx=3, ts="t3", bias="BULL", internal=False, created_idx=6)
    brk = LuxBreak(kind="BOS", direction="BULL", level=105.0, pivot_idx=2, idx=6, ts="t6", internal=False, order_block=ob)
    res = type("R", (), {})(); res.breaks = [brk]
    h = np.array([101, 102, 103, 104, 105, 106, 110, 108, 109], dtype=float)
    l = h - 2.0
    c = h - 1.0
    r = vis.ote_range(res, h, l, c)
    assert r["dir"] == 1 and r["h"] == 110.0 and r["l"] == 101.0       # L = min low over [pivot=2 .. break=6] = 103-2
    assert r["p705"] == pytest.approx(110 - 0.705 * 9)
    assert r["eq"] == pytest.approx(101 + 0.5 * 9)


def test_expected_visuals_keys():
    idx = pd.date_range("2026-01-01", periods=900, freq="15min")
    rng = np.random.default_rng(1)
    close = 100 + np.cumsum(rng.normal(0, 0.5, 900))
    df = pd.DataFrame({"open": close, "high": close + 0.3, "low": close - 0.3, "close": close, "volume": 1.0}, index=idx)
    cfg = {"smc_v2": {"luxalgo": {"swing_length": 50, "internal_length": 5, "eq_length": 3, "eq_threshold": 0.1,
                                  "ob_filter": "ATR", "ob_mitigation": "HIGHLOW", "fvg_auto_threshold": True}}}
    out = vis.expected_visuals(df, cfg, warmup=100)
    assert set(out) == {"ob_swing", "ob_internal", "fvg", "liquidity", "flips", "ote", "meta"}
