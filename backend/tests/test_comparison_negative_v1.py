"""BT-10: comparison gate'leri negatif v1 metriklerinde oran işaret hatası.

v2/v1 oranı v1 < 0 iken monotonluğu ters çevirir:
  sharpe v1=-1.0, v2=+0.5 (BÜYÜK iyileşme) → ratio -0.5 → hard_reject (YANLIŞ)
  sharpe v1=-1.0, v2=-2.0 (kötüleşme)      → ratio  2.0 → pass        (YANLIŞ)

Fix: v1 < 0 dalında işaretli normalize delta (v2 - v1) / |v1| kullanılır;
v1 > 0 yolu bit-bit aynı kalır (ratio < T  ⇔  (v2-v1)/v1 < T-1).
"""
from __future__ import annotations

import pytest

from backtest.comparison import _evaluate_metric, evaluate_gates, DEFAULT_GATES

HIGHER_BETTER = {"v2_min_vs_v1": 1.0, "hard_reject_vs_v1": 0.9}
LOWER_BETTER = {"v2_max_vs_v1": 1.0, "hard_reject_vs_v1": 1.1}


# ── higher-is-better, v1 negatif ──

def test_negative_v1_improvement_passes():
    # -1.0 → +0.5: norm delta = +1.5 ≥ (1.0 - 1) → pass
    assert _evaluate_metric(-1.0, 0.5, HIGHER_BETTER) == "pass"


def test_negative_v1_regression_hard_rejects():
    # -1.0 → -2.0: norm delta = -1.0 < (0.9 - 1) → hard_reject
    assert _evaluate_metric(-1.0, -2.0, HIGHER_BETTER) == "hard_reject"


def test_negative_v1_equal_passes():
    assert _evaluate_metric(-1.0, -1.0, HIGHER_BETTER) == "pass"


def test_negative_v1_small_regression_warns():
    # -1.0 → -1.05: norm delta = -0.05; (0.9-1) < -0.05 < (1.0-1) → warn
    assert _evaluate_metric(-1.0, -1.05, HIGHER_BETTER) == "warn"


# ── lower-is-better, v1 negatif ──

def test_negative_v1_lower_better_improvement_passes():
    # -2.0 → -3.0 (daha düşük = daha iyi): norm delta = -0.5 ≤ 0 → pass
    assert _evaluate_metric(-2.0, -3.0, LOWER_BETTER) == "pass"


def test_negative_v1_lower_better_regression_hard_rejects():
    # -2.0 → 0.0: norm delta = +1.0 > (1.1 - 1) → hard_reject
    assert _evaluate_metric(-2.0, 0.0, LOWER_BETTER) == "hard_reject"


# ── pozitif v1 yolu regresyonsuz (bit-bit aynı) ──

@pytest.mark.parametrize("v1,v2,expected", [
    (2.0, 2.2, "pass"),
    (2.0, 1.9, "warn"),          # ratio 0.95: < 1.0, değil < 0.9
    (2.0, 1.7, "hard_reject"),   # ratio 0.85 < 0.9
])
def test_positive_v1_higher_better_unchanged(v1, v2, expected):
    assert _evaluate_metric(v1, v2, HIGHER_BETTER) == expected


@pytest.mark.parametrize("v1,v2,expected", [
    (10.0, 9.0, "pass"),
    (10.0, 10.5, "warn"),        # ratio 1.05: > 1.0, değil > 1.1
    (10.0, 12.0, "hard_reject"),
])
def test_positive_v1_lower_better_unchanged(v1, v2, expected):
    assert _evaluate_metric(v1, v2, LOWER_BETTER) == expected


def test_evaluate_gates_end_to_end_negative_sharpe():
    v1 = {"win_rate": 50.0, "avg_realized_rr": 2.0, "max_drawdown_pct": 5.0,
          "stop_hunt_rate": 0.2, "sharpe_like": -0.5}
    v2 = dict(v1, sharpe_like=0.8)  # negatiften pozitife büyük iyileşme
    gates = evaluate_gates(v1, v2, DEFAULT_GATES)
    assert gates["sharpe_like"] == "pass"
