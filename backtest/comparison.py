"""SMC v1 vs v2 backtest comparison harness (spec §8.2).

Runs both backtest paths over identical data, computes per-metric deltas,
and applies the spec §8.2 acceptance gates returning pass/warn/hard_reject.
"""
from __future__ import annotations

from typing import Any

import pandas as pd

from backtest.engine import _DEFAULT_SMC_WINDOW, run_backtest
from backtest.metrics import compute_stop_hunt_rate


# Gate semantics (per spec §8.2):
#   "v2_min_vs_v1" — higher is better; v2/v1 ratio threshold
#   "v2_max_vs_v1" — lower is better; v2/v1 ratio threshold
#   "v2_min_abs"   — absolute floor regardless of v1
#   "hard_reject_*" companions define the drop-dead line
#
# NOTE: spec §8.2 lists 6 gates; the 6th — "setup_rejection_rate" — requires a
# producer counter (REJECT_REASON over total_setup_candidates) that does not yet
# exist in engine.smc_v2. PR #S5 (lifecycle telemetry) will add the producer and
# enable that gate. Not gating on a metric we cannot yet compute.
DEFAULT_GATES = {
    "win_rate":         {"v2_min_vs_v1": 1.0,  "hard_reject_vs_v1": 0.95},
    "avg_realized_rr":  {"v2_min_abs":   1.5,  "hard_reject_abs":   1.2},
    "max_drawdown_pct": {"v2_max_vs_v1": 1.0,  "hard_reject_vs_v1": 1.1},  # lower=better
    "stop_hunt_rate":   {"v2_max_vs_v1": 0.5,  "hard_reject_vs_v1": 1.0},  # lower=better
    "sharpe_like":      {"v2_min_vs_v1": 1.0,  "hard_reject_vs_v1": 0.9},
}


def _evaluate_metric(v1_val: float, v2_val: float, spec: dict) -> str:
    """Return 'pass' | 'warn' | 'hard_reject' for one metric per its gate spec."""
    if "v2_min_abs" in spec:
        if v2_val < spec["hard_reject_abs"]:
            return "hard_reject"
        if v2_val < spec["v2_min_abs"]:
            return "warn"
        return "pass"
    if "v2_min_vs_v1" in spec:
        # higher is better
        if v1_val == 0:
            return "pass" if v2_val >= 0 else "hard_reject"
        # BT-10 (2026-07-11 review): v1 < 0 iken v2/v1 orani monotonlugu ters
        # cevirir (iyilesme hard_reject, kotulesme pass gorunur — orn. sharpe
        # -1.0 -> +0.5 red, -1.0 -> -2.0 gecer). Isaretli normalize delta
        # (v2-v1)/|v1| kullan; v1 > 0 icin ratio testiyle birebir denk:
        # ratio < T  <=>  norm < T - 1.
        if v1_val < 0:
            norm = (v2_val - v1_val) / abs(v1_val)
            if norm < spec["hard_reject_vs_v1"] - 1.0:
                return "hard_reject"
            if norm < spec["v2_min_vs_v1"] - 1.0:
                return "warn"
            return "pass"
        ratio = v2_val / v1_val
        if ratio < spec["hard_reject_vs_v1"]:
            return "hard_reject"
        if ratio < spec["v2_min_vs_v1"]:
            return "warn"
        return "pass"
    if "v2_max_vs_v1" in spec:
        # lower is better
        if v1_val == 0:
            return "pass" if v2_val <= 0 else "hard_reject"
        # BT-10: ayni isaret duzeltmesi — lower-is-better yonunde.
        if v1_val < 0:
            norm = (v2_val - v1_val) / abs(v1_val)
            if norm > spec["hard_reject_vs_v1"] - 1.0:
                return "hard_reject"
            if norm > spec["v2_max_vs_v1"] - 1.0:
                return "warn"
            return "pass"
        ratio = v2_val / v1_val
        if ratio > spec["hard_reject_vs_v1"]:
            return "hard_reject"
        if ratio > spec["v2_max_vs_v1"]:
            return "warn"
        return "pass"
    return "pass"


def evaluate_gates(v1: dict, v2: dict, gate_table: dict) -> dict[str, str]:
    """Apply each gate to v1/v2 metric values."""
    return {
        metric: _evaluate_metric(
            float(v1.get(metric, 0.0)),
            float(v2.get(metric, 0.0)),
            spec,
        )
        for metric, spec in gate_table.items()
    }


def compute_deltas(v1: dict, v2: dict) -> dict[str, dict]:
    """Per-metric absolute and relative delta (v2 - v1).

    Skips non-numeric fields. `rel_pct` is None when v1 == 0.
    """
    out = {}
    for key in v1.keys():
        v1_val = v1.get(key)
        v2_val = v2.get(key)
        if not isinstance(v1_val, (int, float)) or not isinstance(v2_val, (int, float)):
            continue
        if isinstance(v1_val, bool) or isinstance(v2_val, bool):
            continue
        abs_delta = v2_val - v1_val
        rel_pct = (abs_delta / v1_val * 100) if v1_val != 0 else None
        out[key] = {"abs": abs_delta, "rel_pct": rel_pct}
    return out


def _avg_realized_rr(trades: list[dict]) -> float:
    """Average realized RR across closed trades.

    Approximation: |exit - entry| / |entry - sl|, signed by pnl direction.
    Trades with degenerate risk (entry == sl) are skipped. Returns 0.0
    when no usable trades exist.

    LIMITATION: serialize_trade emits only the last exit price. For multi-exit
    trades (e.g. v1 TP1-partial then BE-SL), `exit ≈ entry` collapses RR
    toward 0 even though the trade was profitable. Correct for v2 single-target
    mode (full close at TP1). PR #S5 (lifecycle telemetry) will expose realized
    PnL / notional_at_entry for a precise calculation.
    """
    rrs = []
    for t in trades:
        entry = float(t.get("entry", 0.0))
        sl = float(t.get("sl", 0.0))
        pnl = float(t.get("pnl", 0.0))
        risk_per_unit = abs(entry - sl)
        if risk_per_unit <= 0:
            continue
        exit_price = float(t.get("exit", entry))
        rr = abs(exit_price - entry) / risk_per_unit
        if pnl < 0:
            rr = -rr
        rrs.append(rr)
    return sum(rrs) / len(rrs) if rrs else 0.0


def run_v1_v2_comparison(
    *,
    symbols: list[str],
    data: dict[str, dict[str, pd.DataFrame]],
    config: dict,
    initial_balance: float = 2000.0,
    warmup_bars: int = 200,
    step_every_n_bars: int = 1,
    smc_window_bars: int = _DEFAULT_SMC_WINDOW,
    entry_tf: str | None = None,
    hypothesis: str | None = None,
    doctrine_tags: list[str] | None = None,
) -> dict[str, Any]:
    """Run v1 + v2 backtests over the same data, return comparison report.

    Output shape:
        {
            "v1": <run_backtest result + stop_hunt_rate + avg_realized_rr>,
            "v2": <run_backtest result + stop_hunt_rate + avg_realized_rr>,
            "deltas": {<metric>: {"abs": ..., "rel_pct": ...}, ...},
            "gates": {<metric>: "pass" | "warn" | "hard_reject", ...},
            "hypothesis": str | None,
            "doctrine_tags": list[str] | None,
        }
    """
    import copy
    entry_tf = entry_tf or config["timeframes"]["entry"]
    
    v1_cfg = copy.deepcopy(config)
    v1_cfg.setdefault("engine", {})["smc_version"] = "v1"
    
    v2_cfg = copy.deepcopy(config)
    v2_cfg.setdefault("engine", {})["smc_version"] = "v2"
    v2_cfg["engine"]["smc_v2_shadow"] = False
    v2_cfg["engine"]["smc_v2_symbols"] = ["*"]
    v2_cfg.setdefault("risk", {})["min_confluence"] = 999

    v1 = run_backtest(
        symbols=symbols,
        data=data,
        config=v1_cfg,
        initial_balance=initial_balance,
        warmup_bars=warmup_bars,
        step_every_n_bars=step_every_n_bars,
        smc_window_bars=smc_window_bars,
        smc_version="v1",
    )
    v2 = run_backtest(
        symbols=symbols,
        data=data,
        config=v2_cfg,
        initial_balance=initial_balance,
        warmup_bars=warmup_bars,
        step_every_n_bars=step_every_n_bars,
        smc_window_bars=smc_window_bars,
        smc_version="v2",
    )
    v1["stop_hunt_rate"] = compute_stop_hunt_rate(v1["trades"], data, entry_tf=entry_tf)
    v2["stop_hunt_rate"] = compute_stop_hunt_rate(v2["trades"], data, entry_tf=entry_tf)
    v1["avg_realized_rr"] = _avg_realized_rr(v1["trades"])
    v2["avg_realized_rr"] = _avg_realized_rr(v2["trades"])

    return {
        "v1": v1,
        "v2": v2,
        "deltas": compute_deltas(v1, v2),
        "gates": evaluate_gates(v1, v2, DEFAULT_GATES),
        "hypothesis": hypothesis,
        "doctrine_tags": doctrine_tags,
    }
