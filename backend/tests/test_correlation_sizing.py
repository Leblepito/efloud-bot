"""S3: correlation-aware position sizing primitive.

The bot trades 10 majors that move as a cluster (high pairwise correlation,
especially in risk-off). max_total_exposure / per-name risk assume INDEPENDENT
trades, so a correlated book carries far more true risk than the nominal sum
(the 44% portfolio DD in the conf=50 backtest was exactly this). This module
provides the MEASURED-correlation primitive: an effective-independent-bets count
and a 0–1 sizing haircut for a new position given the open, correlated book.

Pure functions. Live wiring (feeding a multi-symbol return matrix into sizing)
is a separate, backtest-validated adoption step — see PR notes.
"""
import numpy as np
import pytest

from engine.risk.correlation import (
    average_pairwise_correlation,
    correlation_matrix,
    correlation_sizing_factor,
    effective_independent_bets,
)


def test_correlation_matrix_identical_series_is_one():
    r = {"A": [0.1, -0.2, 0.3, -0.1, 0.2], "B": [0.1, -0.2, 0.3, -0.1, 0.2]}
    syms, corr = correlation_matrix(r)
    assert syms == ["A", "B"]
    assert corr[0, 1] == pytest.approx(1.0, abs=1e-9)


def test_correlation_matrix_anti_correlated_is_minus_one():
    r = {"A": [0.1, -0.2, 0.3, -0.1, 0.2], "B": [-0.1, 0.2, -0.3, 0.1, -0.2]}
    _, corr = correlation_matrix(r)
    assert corr[0, 1] == pytest.approx(-1.0, abs=1e-9)


def test_average_pairwise_excludes_diagonal():
    corr = np.array([[1.0, 0.8], [0.8, 1.0]])
    assert average_pairwise_correlation(corr) == pytest.approx(0.8)


def test_effective_bets_uncorrelated_equals_n():
    assert effective_independent_bets(5, 0.0) == pytest.approx(5.0)


def test_effective_bets_fully_correlated_equals_one():
    assert effective_independent_bets(5, 1.0) == pytest.approx(1.0)


def test_sizing_factor_first_position_no_haircut():
    assert correlation_sizing_factor(0, 0.9) == pytest.approx(1.0)


def test_sizing_factor_correlated_book_cuts_size():
    # 4 open + new = 5; rho=1 → effective bets 1 → factor 1/5.
    assert correlation_sizing_factor(4, 1.0) == pytest.approx(0.2)


def test_sizing_factor_uncorrelated_book_no_haircut():
    assert correlation_sizing_factor(4, 0.0) == pytest.approx(1.0)
