"""S3 — correlation-aware position sizing primitive.

The bot trades 10 majors that move as a cluster. ``max_total_exposure`` and the
per-name risk budget assume INDEPENDENT trades, so a correlated book carries far
more true risk than the nominal sum. This module measures portfolio correlation
and derives a sizing haircut for a new position given the open book.

Pure functions, no I/O. Wiring a live multi-symbol return matrix into the sizing
path is a separate, backtest-validated adoption step.
"""
from __future__ import annotations

import numpy as np


def correlation_matrix(returns_by_symbol: dict[str, list[float]]):
    """Pairwise Pearson correlation across symbols' (equal-length, aligned) return
    series. Returns ``(sorted_symbols, corr_matrix)``. Identity when < 2 symbols
    or < 2 observations."""
    symbols = sorted(returns_by_symbol)
    n = len(symbols)
    if n < 2:
        return symbols, np.eye(n)
    mat = np.array([list(returns_by_symbol[s]) for s in symbols], dtype=float)
    if mat.ndim != 2 or mat.shape[1] < 2:
        return symbols, np.eye(n)
    corr = np.corrcoef(mat)
    corr = np.nan_to_num(corr, nan=0.0)  # constant series → undefined → 0
    np.fill_diagonal(corr, 1.0)
    return symbols, corr


def average_pairwise_correlation(corr) -> float:
    """Mean of the off-diagonal correlation entries (the book's average rho)."""
    corr = np.asarray(corr, dtype=float)
    n = corr.shape[0]
    if n < 2:
        return 0.0
    off_sum = corr.sum() - np.trace(corr)
    return float(off_sum / (n * (n - 1)))


def effective_independent_bets(n_positions: int, avg_rho: float) -> float:
    """Diversification-adjusted bet count: ``N / (1 + (N-1)·rho)``.

    rho=0 → N independent bets; rho=1 → 1 effective bet (the whole book is one
    trade). rho is clamped to [0, 1] (negative correlation is treated as 0 — it
    does not *increase* concentration risk for sizing purposes)."""
    if n_positions <= 0:
        return 0.0
    rho = max(0.0, min(1.0, float(avg_rho)))
    return n_positions / (1.0 + (n_positions - 1) * rho)


def correlation_sizing_factor(n_open: int, avg_rho: float) -> float:
    """0–1 size haircut for a NEW position given ``n_open`` already-open positions
    at average correlation ``avg_rho``.

    factor = effective_bets(n_open+1) / (n_open+1). The first position (n_open=0)
    is never cut (factor 1.0). A fully-correlated book (rho=1) cuts the new
    position to ``1/(n_open+1)``; an uncorrelated book (rho=0) is not cut."""
    total = n_open + 1
    return effective_independent_bets(total, avg_rho) / total
