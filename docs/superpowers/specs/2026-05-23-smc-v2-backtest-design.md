# SMC v2 Backtest Harness + v1 Baseline — Design Spec (PR #S4)

**Status:** Approved (self-approved 2026-05-23 via Hermes-mode autoresearch ratchet)
**Date:** 2026-05-23
**Author:** Claude (autonomous)
**Branch:** `feat/smc-v2-backtest`
**Parent spec:** `docs/superpowers/specs/2026-05-23-smc-entry-sltp-rework-design.md` §8.2

---

## 1. Goal

Add a v2 path to the existing backtest engine (`backtest/engine.py`) and a comparison
harness that runs v1 + v2 over the same data slice, producing a per-metric delta
report against the spec §8.2 acceptance gates.

PR #S4 produces:
1. `run_backtest(..., smc_version="v1"|"v2")` switch (default `"v1"` — byte-identical to current).
2. `backtest.comparison.run_v1_v2_comparison(...)` orchestrator.
3. `compute_stop_hunt_rate()` metric helper.
4. `backtest.cli compare` subcommand.
5. Committed JSON baseline fixture under `docs/backtest/`.

PR #S4 does **NOT** include:
- dry_run shadow mode (deferred to PR #S6)
- lifecycle telemetry fields (PR #S5)
- production config changes
- Hermes-time real 6-month walk-forward run (operator activity, post-merge)

## 2. Architecture

```
                ┌─────────────────────────┐
                │ backtest.cli compare    │
                │ (new subcommand)        │
                └────────────┬────────────┘
                             │
                             ▼
                ┌─────────────────────────┐
                │ run_v1_v2_comparison()  │
                │ (backtest/comparison.py)│
                └────────────┬────────────┘
                             │
              ┌──────────────┼──────────────┐
              ▼              ▼              ▼
   ┌──────────────┐ ┌──────────────┐ ┌─────────────────┐
   │run_backtest( │ │run_backtest( │ │ evaluate_gates  │
   │smc_version=  │ │smc_version=  │ │ (per metric)    │
   │  "v1")       │ │  "v2")       │ │                 │
   └──────────────┘ └──────────────┘ └─────────────────┘
              │              │
              ▼              ▼
   ┌──────────────┐ ┌──────────────┐
   │ existing v1  │ │ NEW: passes  │
   │ orch path,   │ │ SetupStateStore│
   │ no v2 deps   │ │ to orch ctor │
   └──────────────┘ └──────────────┘
```

## 3. Backtest engine changes

### 3.1 `run_backtest` signature

Add an optional `smc_version: Literal["v1", "v2"] = "v1"` keyword argument. When
`"v2"`, the engine constructs a `SetupStateStore` with a tempdir path and passes
it to `SafeOrchestrator`. When `"v1"` (default), behavior is unchanged.

```python
def run_backtest(
    *,
    symbols: list[str],
    data: dict[str, dict[str, pd.DataFrame]],
    config: dict,
    initial_balance: float = 2000.0,
    warmup_bars: int = 200,
    step_every_n_bars: int = 1,
    smc_window_bars: int = _DEFAULT_SMC_WINDOW,
    smc_version: Literal["v1", "v2"] = "v1",   # NEW
) -> dict[str, Any]:
```

### 3.2 SetupStateStore wiring (v2 only)

Inside the `tempfile.TemporaryDirectory(prefix="bt_")` block, when `smc_version == "v2"`:

```python
setup_state_store = None
if smc_version == "v2":
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
    setup_state_store=setup_state_store,   # None for v1, set for v2
)
```

The result dict gains a `smc_version` field for downstream identification.

### 3.3 Inert invariant

When `smc_version="v1"`:
- `setup_state_store` is `None`
- `SafeOrchestrator._advance_setup_state_tick` short-circuits (verified in PR #67)
- `SafeOrchestrator._emit_setup_candidates` short-circuits (verified in PR #70)
- `SafeOrchestrator._place_v2_entry_order` is never called (no candidates exist)
- All 6 existing backtest tests must still pass byte-identical.

## 4. Comparison harness

### 4.1 `backtest/comparison.py`

```python
def run_v1_v2_comparison(
    *,
    symbols: list[str],
    data: dict[str, dict[str, pd.DataFrame]],
    config: dict,
    initial_balance: float = 2000.0,
    warmup_bars: int = 200,
    step_every_n_bars: int = 1,
    smc_window_bars: int = _DEFAULT_SMC_WINDOW,
) -> dict[str, Any]:
    """Run v1 + v2 backtests over the same data, return comparison report."""
    v1 = run_backtest(symbols=symbols, data=data, config=config, ..., smc_version="v1")
    v2 = run_backtest(symbols=symbols, data=data, config=config, ..., smc_version="v2")

    v1["stop_hunt_rate"] = compute_stop_hunt_rate(v1["trades"], data, ...)
    v2["stop_hunt_rate"] = compute_stop_hunt_rate(v2["trades"], data, ...)

    return {
        "v1": v1,
        "v2": v2,
        "deltas": compute_deltas(v1, v2),
        "gates": evaluate_gates(v1, v2, gate_table=DEFAULT_GATES),
    }
```

### 4.2 Acceptance gate table (from spec §8.2)

```python
DEFAULT_GATES = {
    "win_rate":         {"v2_min_vs_v1": 1.0,    "hard_reject_vs_v1": 0.95},
    "avg_realized_rr":  {"v2_min_abs":   1.5,    "hard_reject_abs": 1.2},
    "max_drawdown_pct": {"v2_max_vs_v1": 1.0,    "hard_reject_vs_v1": 1.1},  # smaller=better
    "stop_hunt_rate":   {"v2_max_vs_v1": 0.5,    "hard_reject_vs_v1": 1.0},
    "sharpe_like":      {"v2_min_vs_v1": 1.0,    "hard_reject_vs_v1": 0.9},
}
```

`evaluate_gates` returns per-metric verdict: `"pass" | "warn" | "hard_reject"`.

### 4.3 Setup rejection rate

Computed as `1 - (v2.total_trades / v1.total_trades)` (approximation; real v2 has
explicit reject paths via `SLTooFarError` / `InsufficientTPDistanceError`). The
spec target is 40-60% rejection rate vs. v1 trade count.

## 5. Stop-hunt rate metric

```python
def compute_stop_hunt_rate(
    trades: list[dict],
    data: dict[str, dict[str, pd.DataFrame]],
    entry_tf: str = "15m",
    lookback_bars: int = 4,  # 1h = 4 × 15m
) -> float:
    """Fraction of SL exits where price subsequently reached original tp1 within
    `lookback_bars` bars after the exit.

    Returns 0.0 if no SL exits in trades. Closed trades only.
    """
```

For each closed trade with `exit_reason == "SL"`:
- Look up the symbol's entry-TF data starting from `closed_at`
- For LONG: check whether high in next `lookback_bars` >= original tp1
- For SHORT: check whether low in next `lookback_bars` <= original tp1
- If yes, increment stop-hunt counter

Returns `stop_hunt_count / total_sl_exits`.

## 6. CLI integration

New subcommand `compare`:

```python
def cmd_compare(args):
    with open(args.config, encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    tfs = [...]
    symbols = [...]
    data = _load_data_for_period(symbols, tfs, args.period_days)
    out_dir = Path(f"reports/backtests/{ts}_compare_{run_id}")
    capture_provenance(out_dir)
    report = run_v1_v2_comparison(symbols=symbols, data=data, config=cfg)
    (out_dir / "comparison.json").write_text(json.dumps(report, indent=2, default=str))
    print_summary(report)
```

## 7. Tests (TDD)

### 7.1 Engine-level (`backend/tests/test_backtest_engine_v2.py`)

1. `test_v1_default_byte_identical` — `run_backtest(..., smc_version="v1")` produces
   the same result as `run_backtest(...)` (no kwarg).
2. `test_v2_invokes_setup_store` — `run_backtest(..., smc_version="v2")` constructs
   a `SetupStateStore` and passes it to the orch (asserted via mock or by checking
   the result dict contains v2 marker).
3. `test_v2_falls_back_safely_when_no_signals` — synthetic flat data → v2 produces
   zero trades, no exception.
4. `test_v2_records_marker` — result dict carries `"smc_version": "v2"`.

### 7.2 Comparison harness (`backend/tests/test_backtest_comparison.py`)

1. `test_comparison_runs_both_paths` — output dict has `v1`, `v2`, `deltas`, `gates` keys.
2. `test_evaluate_gates_pass_case` — synthetic v1/v2 dicts where v2 wins every metric → all gates `"pass"`.
3. `test_evaluate_gates_hard_reject_case` — v2 sharpe < 0.9 × v1 → `"hard_reject"`.
4. `test_evaluate_gates_warn_case` — between min and hard-reject thresholds.
5. `test_deltas_computed_per_metric` — relative & absolute deltas present.

### 7.3 Stop-hunt metric (`backend/tests/test_stop_hunt_rate.py`)

1. `test_no_sl_exits_returns_zero` — only TP exits → 0.0.
2. `test_pure_stop_hunt_returns_one` — synthetic SL exit followed by price reaching original tp1 → 1.0.
3. `test_clean_sl_not_counted` — SL hit, price keeps going against original direction → 0.0.
4. `test_short_direction_uses_low` — LONG uses high, SHORT uses low (separate assertions).

## 8. Acceptance criteria

- All existing backtest tests pass (6 tests).
- New v2 backtest tests pass (≥ 4).
- New comparison tests pass (≥ 5).
- New stop-hunt metric tests pass (≥ 4).
- Full backend suite green (currently 603).
- `python -m backtest.cli compare --help` shows the new subcommand.
- Inert invariant verified by `test_v1_default_byte_identical`.

## 9. Rollout

- PR ships as feat branch, squash-merged to master.
- Self-approved (Hermes mode) — no risk surface (offline tool).
- Post-merge: operator can run `backtest.cli compare` against real cached data
  to produce the actual 6-month baseline JSON; that JSON gets committed in a
  follow-up doc PR (NOT this PR).

## 10. Risks

- **Tempdir cleanup with active store**: SetupStateStore writes to a path inside
  the `TemporaryDirectory` context manager. When the context exits, the tempdir
  is removed; the store reference goes out of scope first. Safe.
- **Walk-forward state pollution between cycles**: SetupStateStore is constructed
  fresh per backtest run (not shared across v1+v2 runs). v2 candidates from a v1
  cycle do not exist (v1 doesn't populate). Independent.
- **Determinism**: v1 path remains deterministic. v2 path: SetupStateStore uses
  `time.time()` for one log statement on archive — does not affect candidate
  ordering or outcomes. Verified by re-running comparison with the same data.
