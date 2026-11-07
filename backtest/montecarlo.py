"""S6 — backtest robustness: Monte Carlo bootstrap + IS/OOS split.

A single contiguous backtest yields one point estimate that can be a product of
trade ordering / a lucky regime window. These pure helpers quantify and gate
that risk:

  * ``bootstrap_pnl_distribution`` — resample the closed-trade pnl sequence with
    replacement to get a distribution of total-return % and max-drawdown %.
  * ``walk_forward_split`` — bar-index ranges for an in-sample / out-of-sample
    split so edge can be checked on unseen data.
  * ``montecarlo_gate`` — robustness gate: the 5th-percentile return must stay
    positive (i.e. the strategy is profitable across most resamples, not just
    the one realized ordering).

Pure functions, no I/O. Randomness is seeded for reproducibility.
"""
from __future__ import annotations

import random
from typing import Sequence


def _percentile(sorted_vals: list[float], p: float) -> float:
    """Index-based percentile on an already-sorted list (p in [0, 100])."""
    if not sorted_vals:
        return 0.0
    idx = int(p / 100.0 * len(sorted_vals))
    idx = max(0, min(len(sorted_vals) - 1, idx))
    return sorted_vals[idx]


def bootstrap_pnl_distribution(
    trade_pnls: Sequence[float],
    initial_balance: float,
    n_runs: int = 1000,
    seed: int = 42,
) -> dict:
    """Resample ``trade_pnls`` with replacement ``n_runs`` times; for each
    resample build an equity curve and record final return % and max drawdown %.
    Returns a percentile summary (p05 / p50 / p95)."""
    n = len(trade_pnls)
    if n == 0 or initial_balance <= 0:
        return {
            "n_runs": n_runs, "n_trades": n,
            "return_pct_p05": 0.0, "return_pct_p50": 0.0, "return_pct_p95": 0.0,
            "max_drawdown_pct_p50": 0.0, "max_drawdown_pct_p95": 0.0,
        }
    pnls = [float(x) for x in trade_pnls]
    rng = random.Random(seed)
    returns: list[float] = []
    drawdowns: list[float] = []
    for _ in range(n_runs):
        bal = initial_balance
        peak = bal
        max_dd = 0.0
        for _ in range(n):
            bal += pnls[rng.randrange(n)]
            if bal > peak:
                peak = bal
            if peak > 0:
                dd = (peak - bal) / peak * 100.0
                if dd > max_dd:
                    max_dd = dd
        returns.append((bal - initial_balance) / initial_balance * 100.0)
        drawdowns.append(max_dd)
    returns.sort()
    drawdowns.sort()
    return {
        "n_runs": n_runs, "n_trades": n,
        "return_pct_p05": round(_percentile(returns, 5), 2),
        "return_pct_p50": round(_percentile(returns, 50), 2),
        "return_pct_p95": round(_percentile(returns, 95), 2),
        "max_drawdown_pct_p50": round(_percentile(drawdowns, 50), 2),
        "max_drawdown_pct_p95": round(_percentile(drawdowns, 95), 2),
    }


def walk_forward_split(
    n_bars: int, warmup_bars: int, is_frac: float = 0.7,
) -> tuple[tuple[int, int], tuple[int, int]]:
    """Return ``(is_range, oos_range)`` bar-index half-open ranges for an
    in-sample / out-of-sample split. IS = ``[warmup, is_end)``,
    OOS = ``[is_end, n_bars)``. Raises if the split would be degenerate."""
    if not (0.0 < is_frac < 1.0):
        raise ValueError(f"is_frac must be in (0,1), got {is_frac}")
    usable = n_bars - warmup_bars
    if usable <= 1:
        raise ValueError(f"Not enough bars for a split: usable={usable}")
    is_len = int(usable * is_frac)
    is_end = warmup_bars + is_len
    return (warmup_bars, is_end), (is_end, n_bars)


def montecarlo_gate(dist: dict, min_p05_return_pct: float = 0.0) -> bool:
    """Robustness gate: True when the bootstrap 5th-percentile return is above
    ``min_p05_return_pct`` (default 0 → profitable across ~95% of resamples)."""
    return float(dist.get("return_pct_p05", 0.0)) > min_p05_return_pct
