"""S7: break the regime-ML circularity with forward-realized labels.

build_features_and_labels labels each sample with the RULE detector's own output
(y = detector.analyze(...).regime), so the ML can only learn to reproduce the
rules — zero independent signal. S7 adds an opt-in path that labels each sample
by the regime that ACTUALLY materialised over the next `horizon` bars, so the ML
learns to PREDICT regime from current features. The rule-based default is
unchanged (live model untouched until validated).
"""
import numpy as np
import pandas as pd

from engine.regimes.train import (
    _forward_regime_label,
    build_features_and_forward_labels,
)

# label ints (match train._LABEL_MAP): TRENDING=0, RANGING=1, VOLATILE=2
_TRENDING, _RANGING, _VOLATILE = 0, 1, 2


def test_forward_label_trending():
    closes = [100.0 + i * 0.5 for i in range(12)]  # steady +5.5% drift, low bar vol
    assert _forward_regime_label(closes, trend_return_pct=1.5, vol_bar_std_pct=1.0) == _TRENDING


def test_forward_label_ranging():
    closes = [100.0, 100.1, 99.9, 100.05, 99.95, 100.0] * 2  # flat oscillation
    assert _forward_regime_label(closes, trend_return_pct=1.5, vol_bar_std_pct=1.0) == _RANGING


def test_forward_label_volatile():
    closes = [100.0, 104.0, 97.0, 105.0, 96.0, 103.0]  # big per-bar swings
    assert _forward_regime_label(closes, trend_return_pct=1.5, vol_bar_std_pct=1.0) == _VOLATILE


def test_forward_label_short_window_is_ranging():
    assert _forward_regime_label([100.0], trend_return_pct=1.5, vol_bar_std_pct=1.0) == _RANGING


def test_build_forward_labels_shape_and_horizon():
    rng = np.random.default_rng(0)
    n = 100
    closes = 100.0 + np.cumsum(rng.normal(0, 0.5, n))
    df = pd.DataFrame({
        "open": closes, "high": closes + 0.5, "low": closes - 0.5,
        "close": closes, "volume": rng.uniform(1.0, 2.0, n),
    })
    horizon = 10
    X, y = build_features_and_forward_labels(df, horizon=horizon)
    assert X.shape[1] == 5            # same 5 features as the rule path
    assert len(X) == len(y)
    assert len(X) == n - horizon - 40  # start_idx=40, stop horizon bars early
    assert set(np.unique(y)).issubset({0, 1, 2, 3, 4})
