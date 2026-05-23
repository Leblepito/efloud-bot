# SMC v2 Backtest Harness Implementation Plan (PR #S4)

**Goal:** Add v2 path to `run_backtest`, comparison harness, stop-hunt metric, CLI subcommand.

**Architecture:** `run_backtest(smc_version=...)` toggles between v1 (current) and v2 (with SetupStateStore). New `backtest/comparison.py` orchestrates both runs + gate eval. New metric helper for stop-hunt rate.

**Tech Stack:** Python 3.14, pandas, pytest, existing engine/smc_v2 modules.

---

## Task 1: Add `smc_version` kwarg to `run_backtest`, default v1, byte-identical

**Files:**
- Modify: `backtest/engine.py:53` (add kwarg + result dict key)
- Test: `backend/tests/test_backtest_engine_v2.py` (new)

- [ ] **Step 1: Write failing test for v1 default byte-identical**

```python
# backend/tests/test_backtest_engine_v2.py
import pytest
import pandas as pd
import numpy as np
import yaml
from backtest.engine import run_backtest


@pytest.fixture
def base_config():
    with open("configs/config.phase2_1k.yaml", encoding="utf-8") as f:
        return yaml.safe_load(f)


@pytest.fixture
def synthetic_data():
    """Trending synthetic OHLCV for two timeframes."""
    rng = np.random.default_rng(42)
    n = 400
    idx_15m = pd.date_range("2025-01-01", periods=n, freq="15min", tz="UTC")
    idx_1h = pd.date_range("2025-01-01", periods=n // 4 + 1, freq="1h", tz="UTC")
    idx_4h = pd.date_range("2025-01-01", periods=n // 16 + 1, freq="4h", tz="UTC")

    def make_df(idx):
        closes = 100 + np.cumsum(rng.normal(0, 0.5, len(idx)))
        return pd.DataFrame({
            "open": closes,
            "high": closes + 0.3,
            "low": closes - 0.3,
            "close": closes,
            "volume": 1000.0,
        }, index=idx)

    return {"ETH/USDT": {"4h": make_df(idx_4h), "1h": make_df(idx_1h), "15m": make_df(idx_15m), "1d": make_df(idx_4h)}}


def test_v1_default_byte_identical(base_config, synthetic_data):
    r1 = run_backtest(symbols=["ETH/USDT"], data=synthetic_data, config=base_config, initial_balance=2000.0)
    r2 = run_backtest(symbols=["ETH/USDT"], data=synthetic_data, config=base_config, initial_balance=2000.0, smc_version="v1")
    # Strip non-deterministic fields if any
    assert r1["total_trades"] == r2["total_trades"]
    assert r1["final_balance"] == r2["final_balance"]
    assert r1["trades"] == r2["trades"]
```

- [ ] **Step 2: Run test (must FAIL)**

Run: `python -m pytest backend/tests/test_backtest_engine_v2.py::test_v1_default_byte_identical -x -q`
Expected: FAIL with `TypeError: run_backtest() got an unexpected keyword argument 'smc_version'`

- [ ] **Step 3: Add kwarg with default "v1", thread through**

In `backtest/engine.py`, add to signature:

```python
from typing import Literal

def run_backtest(
    *,
    symbols: list[str],
    data: dict[str, dict[str, pd.DataFrame]],
    config: dict,
    initial_balance: float = 2000.0,
    warmup_bars: int = 200,
    step_every_n_bars: int = 1,
    smc_window_bars: int = _DEFAULT_SMC_WINDOW,
    smc_version: Literal["v1", "v2"] = "v1",
) -> dict[str, Any]:
```

And add to the return dict:

```python
        return {
            "initial_balance": initial_balance,
            ...
            "max_drawdown_pct": round(max_drawdown_pct, 2),
            "smc_version": smc_version,
            **agg,
        }
```

- [ ] **Step 4: Run test (must PASS)**

Run: `python -m pytest backend/tests/test_backtest_engine_v2.py::test_v1_default_byte_identical -x -q`
Expected: PASS

- [ ] **Step 5: Run existing backtest tests (must still pass)**

Run: `python -m pytest backend/tests/test_backtest_engine_single.py backend/tests/test_backtest_engine_portfolio.py -q`
Expected: 6 passed

- [ ] **Step 6: Commit**

```bash
git add backtest/engine.py backend/tests/test_backtest_engine_v2.py
git commit -m "feat(backtest): add smc_version kwarg (default v1, byte-identical)"
```

---

## Task 2: Wire SetupStateStore for v2 path

**Files:**
- Modify: `backtest/engine.py` (instantiate store when v2)
- Test: `backend/tests/test_backtest_engine_v2.py` (add 3 tests)

- [ ] **Step 1: Add tests for v2 wiring**

```python
def test_v2_records_marker(base_config, synthetic_data):
    r = run_backtest(symbols=["ETH/USDT"], data=synthetic_data, config=base_config, smc_version="v2")
    assert r["smc_version"] == "v2"


def test_v2_runs_to_completion_no_signals(base_config, synthetic_data):
    """Synthetic noise data — v2 may produce zero trades; must not raise."""
    r = run_backtest(symbols=["ETH/USDT"], data=synthetic_data, config=base_config, smc_version="v2")
    assert r["total_trades"] >= 0
    assert r["skipped_cycles"] >= 0


def test_v2_orchestrator_has_setup_state_store(base_config, synthetic_data, monkeypatch):
    """Verify the v2 path constructs a SetupStateStore and passes it to orch."""
    from backtest import engine as bt_engine
    captured = {}
    original_orch_cls = bt_engine.SafeOrchestrator

    class SpyOrch(original_orch_cls):
        def __init__(self, *args, **kwargs):
            captured["setup_state_store"] = kwargs.get("setup_state_store")
            super().__init__(*args, **kwargs)

    monkeypatch.setattr(bt_engine, "SafeOrchestrator", SpyOrch)
    run_backtest(symbols=["ETH/USDT"], data=synthetic_data, config=base_config, smc_version="v2")
    assert captured["setup_state_store"] is not None
    assert captured["setup_state_store"].max_pending_per_symbol == 3
```

- [ ] **Step 2: Run tests (must FAIL)**

Run: `python -m pytest backend/tests/test_backtest_engine_v2.py -x -q`
Expected: FAIL — `setup_state_store` is None / kwarg ignored

- [ ] **Step 3: Implement v2 wiring**

In `backtest/engine.py` inside the `TemporaryDirectory` block, before constructing `orch`:

```python
        setup_state_store = None
        if smc_version == "v2":
            from pathlib import Path
            from engine.smc_v2.setup_state import SetupStateStore
            setup_state_store = SetupStateStore(
                path=Path(state_dir) / "setup_candidates.json",
                max_pending_per_symbol=int(config.get("smc_v2", {}).get("max_pending_per_symbol", 3)),
            )

        orch = SafeOrchestrator(
            config,
            state_dir=state_dir,
            notification_mgr=NullNotificationManager(),
            freshness_check=False,
            persist=False,
            setup_state_store=setup_state_store,
        )
```

- [ ] **Step 4: Run tests (must PASS)**

Run: `python -m pytest backend/tests/test_backtest_engine_v2.py -x -q`
Expected: 4 passed (including the v1 byte-identical test)

- [ ] **Step 5: Run existing backtest tests (must still pass)**

Run: `python -m pytest backend/tests/test_backtest_engine_single.py backend/tests/test_backtest_engine_portfolio.py -q`
Expected: 6 passed

- [ ] **Step 6: Commit**

```bash
git add backtest/engine.py backend/tests/test_backtest_engine_v2.py
git commit -m "feat(backtest): wire SetupStateStore for v2 path (inert when v1)"
```

---

## Task 3: Stop-hunt rate metric

**Files:**
- Modify: `backtest/metrics.py` (add `compute_stop_hunt_rate`)
- Test: `backend/tests/test_stop_hunt_rate.py` (new)

- [ ] **Step 1: Write failing tests**

```python
# backend/tests/test_stop_hunt_rate.py
import pandas as pd
import pytest
from backtest.metrics import compute_stop_hunt_rate


def _make_trade(symbol, direction, sl, tp1, exit_reason, closed_at):
    return {
        "symbol": symbol, "direction": direction,
        "entry": 100.0, "sl": sl, "tp1": tp1,
        "pnl": -10.0 if exit_reason == "SL" else 10.0,
        "exit_reason": exit_reason, "closed_at": closed_at,
        "exit": sl if exit_reason == "SL" else tp1,
    }


def _make_data(symbol, after_close_highs, after_close_lows, freq="15min"):
    idx = pd.date_range("2025-01-01 00:00", periods=10, freq=freq, tz="UTC")
    closes = [100.0] * 10
    return {symbol: {"15m": pd.DataFrame({
        "open": closes,
        "high": after_close_highs + [100.0] * (10 - len(after_close_highs)),
        "low": after_close_lows + [100.0] * (10 - len(after_close_lows)),
        "close": closes,
        "volume": [1.0] * 10,
    }, index=idx)}}


def test_no_sl_exits_returns_zero():
    trades = [_make_trade("ETH/USDT", "LONG", 95.0, 110.0, "TP1", "2025-01-01 00:00:00+00:00")]
    rate = compute_stop_hunt_rate(trades, _make_data("ETH/USDT", [], []), entry_tf="15m", lookback_bars=4)
    assert rate == 0.0


def test_pure_stop_hunt_returns_one():
    # SL at 95, tp1 at 110. After close at t=0, next 4 bars: high reaches 112 → stop hunt.
    trades = [_make_trade("ETH/USDT", "LONG", 95.0, 110.0, "SL", "2025-01-01 00:00:00+00:00")]
    data = _make_data("ETH/USDT", [105.0, 108.0, 112.0, 113.0], [94.0, 93.0, 95.0, 96.0])
    rate = compute_stop_hunt_rate(trades, data, entry_tf="15m", lookback_bars=4)
    assert rate == 1.0


def test_clean_sl_not_counted():
    # SL at 95, tp1 at 110. After close: price keeps falling. No stop hunt.
    trades = [_make_trade("ETH/USDT", "LONG", 95.0, 110.0, "SL", "2025-01-01 00:00:00+00:00")]
    data = _make_data("ETH/USDT", [94.0, 93.0, 92.0, 91.0], [90.0, 89.0, 88.0, 87.0])
    rate = compute_stop_hunt_rate(trades, data, entry_tf="15m", lookback_bars=4)
    assert rate == 0.0


def test_short_direction_uses_low():
    # SHORT trade: SL at 105, tp1 at 90. Stop hunt = low reaches 90 after SL exit.
    trades = [_make_trade("ETH/USDT", "SHORT", 105.0, 90.0, "SL", "2025-01-01 00:00:00+00:00")]
    data = _make_data("ETH/USDT", [106.0, 107.0, 108.0, 109.0], [100.0, 95.0, 89.0, 88.0])
    rate = compute_stop_hunt_rate(trades, data, entry_tf="15m", lookback_bars=4)
    assert rate == 1.0
```

- [ ] **Step 2: Run tests (must FAIL)**

Run: `python -m pytest backend/tests/test_stop_hunt_rate.py -x -q`
Expected: FAIL with ImportError

- [ ] **Step 3: Implement `compute_stop_hunt_rate`**

Append to `backtest/metrics.py`:

```python
def compute_stop_hunt_rate(
    trades: list[dict],
    data: dict,
    entry_tf: str = "15m",
    lookback_bars: int = 4,
) -> float:
    """Fraction of SL exits where price subsequently reached original tp1
    within `lookback_bars` bars after the exit.

    Returns 0.0 if no SL exits in trades. Closed trades only.

    For LONG: stop-hunt if any high in next N bars >= tp1.
    For SHORT: stop-hunt if any low in next N bars <= tp1.
    """
    sl_trades = [t for t in trades if t.get("exit_reason") == "SL"]
    if not sl_trades:
        return 0.0
    hunt_count = 0
    for t in sl_trades:
        sym = t["symbol"]
        sym_data = data.get(sym)
        if sym_data is None or entry_tf not in sym_data:
            continue
        df = sym_data[entry_tf]
        closed_at = pd.Timestamp(t["closed_at"])
        after = df.loc[df.index > closed_at].iloc[:lookback_bars]
        if after.empty:
            continue
        tp1 = float(t["tp1"])
        if t["direction"] == "LONG":
            if (after["high"] >= tp1).any():
                hunt_count += 1
        else:  # SHORT
            if (after["low"] <= tp1).any():
                hunt_count += 1
    return hunt_count / len(sl_trades)
```

Add `import pandas as pd` to the top of `backtest/metrics.py` (currently just numpy).

- [ ] **Step 4: Run tests (must PASS)**

Run: `python -m pytest backend/tests/test_stop_hunt_rate.py -x -q`
Expected: 4 passed

- [ ] **Step 5: Commit**

```bash
git add backtest/metrics.py backend/tests/test_stop_hunt_rate.py
git commit -m "feat(backtest): add compute_stop_hunt_rate metric (spec §8.2)"
```

---

## Task 4: Comparison harness module

**Files:**
- Create: `backtest/comparison.py`
- Test: `backend/tests/test_backtest_comparison.py` (new)

- [ ] **Step 1: Write failing tests**

```python
# backend/tests/test_backtest_comparison.py
import pytest
import yaml
from backtest.comparison import (
    run_v1_v2_comparison,
    evaluate_gates,
    compute_deltas,
    DEFAULT_GATES,
)


@pytest.fixture
def base_config():
    with open("configs/config.phase2_1k.yaml", encoding="utf-8") as f:
        return yaml.safe_load(f)


@pytest.fixture
def synthetic_data():
    import pandas as pd
    import numpy as np
    rng = np.random.default_rng(7)
    n = 400
    idx_15m = pd.date_range("2025-01-01", periods=n, freq="15min", tz="UTC")
    idx_1h = pd.date_range("2025-01-01", periods=n // 4 + 1, freq="1h", tz="UTC")
    idx_4h = pd.date_range("2025-01-01", periods=n // 16 + 1, freq="4h", tz="UTC")

    def make_df(idx):
        closes = 100 + np.cumsum(rng.normal(0, 0.5, len(idx)))
        return pd.DataFrame({
            "open": closes,
            "high": closes + 0.3,
            "low": closes - 0.3,
            "close": closes,
            "volume": 1000.0,
        }, index=idx)

    return {"ETH/USDT": {"4h": make_df(idx_4h), "1h": make_df(idx_1h), "15m": make_df(idx_15m), "1d": make_df(idx_4h)}}


def test_comparison_runs_both_paths(base_config, synthetic_data):
    report = run_v1_v2_comparison(symbols=["ETH/USDT"], data=synthetic_data, config=base_config)
    assert "v1" in report and "v2" in report
    assert "deltas" in report and "gates" in report
    assert report["v1"]["smc_version"] == "v1"
    assert report["v2"]["smc_version"] == "v2"


def test_evaluate_gates_pass_case():
    v1 = {"win_rate": 50.0, "max_drawdown_pct": 10.0, "sharpe_like": 1.0, "stop_hunt_rate": 0.3}
    v2 = {"win_rate": 60.0, "max_drawdown_pct": 8.0, "sharpe_like": 1.2, "stop_hunt_rate": 0.1, "avg_realized_rr": 2.0}
    gates = evaluate_gates(v1, v2, DEFAULT_GATES)
    assert gates["win_rate"] == "pass"
    assert gates["max_drawdown_pct"] == "pass"
    assert gates["sharpe_like"] == "pass"
    assert gates["stop_hunt_rate"] == "pass"
    assert gates["avg_realized_rr"] == "pass"


def test_evaluate_gates_hard_reject_case():
    v1 = {"win_rate": 50.0, "max_drawdown_pct": 10.0, "sharpe_like": 1.0, "stop_hunt_rate": 0.3}
    v2 = {"win_rate": 50.0, "max_drawdown_pct": 10.0, "sharpe_like": 0.5, "stop_hunt_rate": 0.5, "avg_realized_rr": 1.0}
    gates = evaluate_gates(v1, v2, DEFAULT_GATES)
    assert gates["sharpe_like"] == "hard_reject"
    assert gates["avg_realized_rr"] == "hard_reject"


def test_evaluate_gates_warn_case():
    v1 = {"win_rate": 50.0, "max_drawdown_pct": 10.0, "sharpe_like": 1.0, "stop_hunt_rate": 0.3}
    v2 = {"win_rate": 48.0, "max_drawdown_pct": 10.0, "sharpe_like": 0.95, "stop_hunt_rate": 0.2, "avg_realized_rr": 1.3}
    gates = evaluate_gates(v1, v2, DEFAULT_GATES)
    assert gates["win_rate"] == "warn"
    assert gates["sharpe_like"] == "warn"
    assert gates["avg_realized_rr"] == "warn"


def test_deltas_computed_per_metric():
    v1 = {"win_rate": 50.0, "max_drawdown_pct": 10.0, "sharpe_like": 1.0, "total_trades": 20}
    v2 = {"win_rate": 60.0, "max_drawdown_pct": 8.0, "sharpe_like": 1.2, "total_trades": 12}
    d = compute_deltas(v1, v2)
    assert d["win_rate"]["abs"] == pytest.approx(10.0)
    assert d["sharpe_like"]["rel_pct"] == pytest.approx(20.0)
    assert d["total_trades"]["abs"] == -8
```

- [ ] **Step 2: Run tests (must FAIL)**

Run: `python -m pytest backend/tests/test_backtest_comparison.py -x -q`
Expected: FAIL with ImportError

- [ ] **Step 3: Implement `backtest/comparison.py`**

```python
"""SMC v1 vs v2 backtest comparison harness (spec §8.2)."""
from __future__ import annotations

from typing import Any

import pandas as pd

from backtest.engine import run_backtest, _DEFAULT_SMC_WINDOW
from backtest.metrics import compute_stop_hunt_rate


# Gate semantics:
#   v2_min_vs_v1 / v2_max_vs_v1 — soft target vs v1 ratio (higher/lower better)
#   hard_reject_vs_v1           — drop dead line vs v1
#   v2_min_abs                  — absolute floor irrespective of v1
#   hard_reject_abs             — absolute hard floor
DEFAULT_GATES = {
    "win_rate":         {"v2_min_vs_v1": 1.0,  "hard_reject_vs_v1": 0.95},
    "avg_realized_rr":  {"v2_min_abs":   1.5,  "hard_reject_abs":   1.2},
    "max_drawdown_pct": {"v2_max_vs_v1": 1.0,  "hard_reject_vs_v1": 1.1},  # lower=better
    "stop_hunt_rate":   {"v2_max_vs_v1": 0.5,  "hard_reject_vs_v1": 1.0},  # lower=better
    "sharpe_like":      {"v2_min_vs_v1": 1.0,  "hard_reject_vs_v1": 0.9},
}


def _evaluate_metric(v1_val, v2_val, spec):
    """Return 'pass' | 'warn' | 'hard_reject' for one metric."""
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
        ratio = v2_val / v1_val
        if ratio > spec["hard_reject_vs_v1"]:
            return "hard_reject"
        if ratio > spec["v2_max_vs_v1"]:
            return "warn"
        return "pass"
    return "pass"


def evaluate_gates(v1: dict, v2: dict, gate_table: dict) -> dict:
    """Apply each gate to v1/v2 metric values."""
    out = {}
    for metric, spec in gate_table.items():
        v1_val = float(v1.get(metric, 0.0))
        v2_val = float(v2.get(metric, 0.0))
        out[metric] = _evaluate_metric(v1_val, v2_val, spec)
    return out


def compute_deltas(v1: dict, v2: dict) -> dict:
    """Per-metric absolute and relative delta (v2 - v1)."""
    out = {}
    for key in v1.keys():
        v1_val = v1.get(key)
        v2_val = v2.get(key)
        if not isinstance(v1_val, (int, float)) or not isinstance(v2_val, (int, float)):
            continue
        abs_delta = v2_val - v1_val
        rel_pct = (abs_delta / v1_val * 100) if v1_val != 0 else None
        out[key] = {"abs": abs_delta, "rel_pct": rel_pct}
    return out


def _avg_realized_rr(trades: list[dict]) -> float:
    """Avg realized RR across closed trades. RR = |pnl/risk|.

    Uses entry+sl gap as risk unit. Returns 0.0 for empty/missing data.
    """
    rrs = []
    for t in trades:
        entry = float(t.get("entry", 0.0))
        sl = float(t.get("sl", 0.0))
        pnl = float(t.get("pnl", 0.0))
        risk_per_unit = abs(entry - sl)
        if risk_per_unit <= 0:
            continue
        # pnl_per_unit needs size; we don't track it here. Approximate via exit price.
        exit_price = float(t.get("exit", entry))
        pnl_per_unit = abs(exit_price - entry)
        rr = pnl_per_unit / risk_per_unit
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
) -> dict[str, Any]:
    """Run v1 + v2 backtests over same data, return comparison report."""
    entry_tf = entry_tf or config["timeframes"]["entry"]
    common = dict(
        symbols=symbols, data=data, config=config,
        initial_balance=initial_balance, warmup_bars=warmup_bars,
        step_every_n_bars=step_every_n_bars, smc_window_bars=smc_window_bars,
    )
    v1 = run_backtest(**common, smc_version="v1")
    v2 = run_backtest(**common, smc_version="v2")
    v1["stop_hunt_rate"] = compute_stop_hunt_rate(v1["trades"], data, entry_tf=entry_tf)
    v2["stop_hunt_rate"] = compute_stop_hunt_rate(v2["trades"], data, entry_tf=entry_tf)
    v1["avg_realized_rr"] = _avg_realized_rr(v1["trades"])
    v2["avg_realized_rr"] = _avg_realized_rr(v2["trades"])

    return {
        "v1": v1,
        "v2": v2,
        "deltas": compute_deltas(v1, v2),
        "gates": evaluate_gates(v1, v2, DEFAULT_GATES),
    }
```

- [ ] **Step 4: Run tests (must PASS)**

Run: `python -m pytest backend/tests/test_backtest_comparison.py -x -q`
Expected: 5 passed

- [ ] **Step 5: Commit**

```bash
git add backtest/comparison.py backend/tests/test_backtest_comparison.py
git commit -m "feat(backtest): v1/v2 comparison harness + gate eval (spec §8.2)"
```

---

## Task 5: CLI subcommand `compare`

**Files:**
- Modify: `backtest/cli.py` (add `cmd_compare` + parser hookup)
- Test: `backend/tests/test_backtest_cli_compare.py` (new, lightweight argparse smoke)

- [ ] **Step 1: Write failing argparse smoke test**

```python
# backend/tests/test_backtest_cli_compare.py
import pytest
from backtest.cli import build_parser


def test_compare_subcommand_registered():
    parser = build_parser()
    args = parser.parse_args([
        "compare",
        "--config", "configs/config.phase2_1k.yaml",
        "--symbols", "ETH/USDT,BTC/USDT",
        "--period-days", "7",
    ])
    assert args.cmd == "compare"
    assert args.symbols == "ETH/USDT,BTC/USDT"
    assert args.period_days == 7
```

Check whether `build_parser` exists. If not in existing CLI, the test will fail at import. The existing CLI uses an inline `main()` function — first refactor to expose `build_parser`.

- [ ] **Step 2: Refactor cli.py to expose `build_parser`**

Read `backtest/cli.py` end-of-file and locate the `argparse` block. Extract into:

```python
def build_parser():
    parser = argparse.ArgumentParser(...)
    sub = parser.add_subparsers(dest="cmd")

    # existing 'single', 'portfolio', 'grid' subcommands stay

    # NEW compare subcommand
    p_compare = sub.add_parser("compare", help="Run v1 vs v2 SMC comparison")
    p_compare.add_argument("--config", required=True)
    p_compare.add_argument("--symbols", required=True)
    p_compare.add_argument("--period-days", type=int, default=30)
    p_compare.add_argument("--balance", type=float, default=2000.0)
    p_compare.set_defaults(func=cmd_compare)
    return parser


def main():
    args = build_parser().parse_args()
    args.func(args)
```

- [ ] **Step 3: Implement `cmd_compare`**

Add to `backtest/cli.py`:

```python
def cmd_compare(args):
    from backtest.comparison import run_v1_v2_comparison

    with open(args.config, encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    tfs = [cfg["timeframes"]["htf"], cfg["timeframes"]["mtf"], cfg["timeframes"]["entry"], "1d"]
    symbols = [s.strip() for s in args.symbols.split(",") if s.strip()]
    data = _load_data_for_period(symbols, tfs, args.period_days)

    run_id = uuid.uuid4().hex[:8]
    out_dir = Path(
        f"reports/backtests/{time.strftime('%Y-%m-%d')}_"
        f"compare_{len(symbols)}sym_{args.period_days}d_{run_id}"
    )
    capture_provenance(out_dir)

    report = run_v1_v2_comparison(
        symbols=symbols, data=data, config=cfg, initial_balance=args.balance,
    )
    (out_dir / "comparison.json").write_text(json.dumps(report, indent=2, default=str))
    print(f"OK Compare backtest: {out_dir}")
    print(f"   v1 trades={report['v1']['total_trades']}  v2 trades={report['v2']['total_trades']}")
    for metric, verdict in report["gates"].items():
        marker = {"pass": "[PASS]", "warn": "[WARN]", "hard_reject": "[REJECT]"}.get(verdict, "?")
        print(f"   {marker} {metric}: v1={report['v1'].get(metric)} v2={report['v2'].get(metric)}")
```

- [ ] **Step 4: Run argparse test (must PASS)**

Run: `python -m pytest backend/tests/test_backtest_cli_compare.py -x -q`
Expected: PASS

- [ ] **Step 5: Smoke `--help`**

Run: `python -m backtest.cli compare --help`
Expected: usage line with `--config`, `--symbols`, `--period-days`, `--balance`

- [ ] **Step 6: Commit**

```bash
git add backtest/cli.py backend/tests/test_backtest_cli_compare.py
git commit -m "feat(backtest): cli 'compare' subcommand"
```

---

## Task 6: Full suite verification + final commit

- [ ] **Step 1: Run all new tests together**

Run: `python -m pytest backend/tests/test_backtest_engine_v2.py backend/tests/test_backtest_engine_single.py backend/tests/test_backtest_engine_portfolio.py backend/tests/test_stop_hunt_rate.py backend/tests/test_backtest_comparison.py backend/tests/test_backtest_cli_compare.py -q`
Expected: all green (≥ 18 tests)

- [ ] **Step 2: Run full backend suite**

Run: `python -m pytest backend/tests/ -q --timeout=120`
Expected: 603 + new tests, all green

- [ ] **Step 3: Verify v1 inert invariant via grep**

Run: `python -c "from backtest.engine import run_backtest; import inspect; print('smc_version' in inspect.signature(run_backtest).parameters)"`
Expected: `True`

- [ ] **Step 4: Update memory file PR status (post-merge step, included as plan reminder)**

Update `C:\Users\utkuc\.claude\projects\c--Users-utkuc-Downloads-efloud-bot\memory\smc_v2_rework_initiative.md` once PR is merged with SHA + test counts.

---

## Done criteria

- 5 commits (one per task), no mixed concerns.
- `smc_version` kwarg defaults to v1, byte-identical behavior preserved.
- 4+ engine tests, 5+ comparison tests, 4+ stop-hunt tests, 1+ cli test = 14+ new tests.
- All existing tests green.
- CLI `compare` subcommand functional via `--help`.
- Spec file at `docs/superpowers/specs/2026-05-23-smc-v2-backtest-design.md` committed.
