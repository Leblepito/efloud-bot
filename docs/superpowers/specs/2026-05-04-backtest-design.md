# efloud-bot Backtest Subsystem — Design

**Author:** Leblepito + Claude
**Date:** 2026-05-04
**Status:** Draft (pending spec review)
**Related:** existing `backtest/runner.py` (legacy, to be replaced)

---

## 1. Goal

Build a backtest mechanism that mirrors the live bot's setup so the owner can:

- **A — Strategy validation** — answer "Did `phase2_1k` (now scaled to $2000 + 5x) earn money over the last 1 year of historical data?"
- **C — Parameter optimization** — grid-search the most impactful parameters to find a better-performing config
- **B — Live-vs-backtest comparison** — replay the same period the live bot has been trading and compare the bot's actual fills against what backtest would have produced (post-Phase A and C)

The work proceeds in that order: A → C → B.

## 2. Non-goals

- **Web dashboard integration** is Phase 2 (after CLI MVP lands). Phase 2 gets its own design doc.
- **Cross-asset / multi-strategy frameworks** — out of scope. This is for one bot's strategy.
- **Real-time / paper-trading mode** — backtest is offline, historical only. The live bot already exists for real-time.
- **ML / parameter learning** — grid search only. No gradient/Bayesian optimization in v1.

## 3. Constraints

- **Production parity**: backtest must use the same `engine.SafeOrchestrator` as live. No re-implementation of trading logic.
- **Determinism**: same config + same data → same result. Critical for Phase B comparison.
- **Reproducibility**: any run must be reproducible 6 months later. Snapshot config, code (git SHA), deps, and data hashes.
- **Performance budget**: 1y × 1 symbol single-mode ≤ 5 min. 20-config grid × 10 symbols ≤ 1 night (~12 h with 4 workers).
- **Resource budget**: data cache ≤ 200 MB on disk; per-run report dir ≤ 5 MB.
- **No look-ahead bias**: at bar `i`, only data ≤ bar `i` is visible. Intrabar SL/TP fills permitted (using bar high/low).

## 4. Decisions Confirmed With Owner

| Topic | Decision |
|-------|----------|
| Goal phasing | A → C → B |
| Modes | Single-symbol AND portfolio (10 symbols, shared balance/breaker) |
| Period | 1 year historical (~35k 15m bars/symbol) |
| Where to run | CLI first (this design); dashboard later (Phase 2) |
| Grid strategy | Aşamalı: confluence × max_position_notional_pct first (5×4=20 configs), expand only if needed |
| Live config baseline | $2000 wallet, 5x leverage, `phase2_1k.yaml` post-2026-05-04 update |

## 5. Architecture (post-Plan-review)

### 5.1 Module layout

```
data/                              NEW
├── fetcher.py                     CCXT-wrapped Binance public REST (no auth);
│                                  fetch_ohlcv_range(symbol, tf, start_ms, end_ms)
│                                  fetch_funding_rates(symbol, start_ms, end_ms)
├── cache.py                       parquet read/write, key=(symbol, tf), one file per pair
└── manifest.py                    cache manifest JSON for fast lookups

backtest/                          REWRITE (delete legacy runner.py)
├── __init__.py                    public API re-export
├── engine.py                      pure simulation; takes symbols list (single OR portfolio
│                                  via N=1 vs N>1); intrabar fill; MTM drawdown; no I/O
├── grid.py                        ProcessPoolExecutor grid search;
│                                  param_grid as dict[str, list[Any]] (generic dimensions)
├── metrics.py                     extracted aggregation: per-symbol + portfolio totals
├── slippage.py                    entry/sl/exit slip pct config (per-leg)
├── funding.py                     8h funding fee application per open position
├── reproducibility.py             snapshot git SHA, pip freeze, data manifest
├── api.py                         list_runs / load_run / compare_runs (Phase 2 dashboard hook)
└── cli.py                         argparse subcommands: single | portfolio | grid

engine/safe_orchestrator.py        EDITS:
  - __init__ adds `freshness_check: bool = True` (replaces brittle monkey-patch)
  - __init__ adds `persist: bool = True` (avoid 350k disk writes in portfolio mode)

reports/backtests/{run_id}/        NEW: each run gets a uuid4 short id
├── summary.md                     human-readable report
├── trades.csv                     all trades with entry_ts_ms / exit_ts_ms (int64)
├── equity.json                    per-cycle MTM equity (not snapshots)
├── result.json                    full structured result (Phase 2 dashboard reads this)
├── config.yaml                    config snapshot
└── provenance.json                git_sha, pip_freeze_sha256, data_manifest, host, wall time

backend/tests/                     8 NEW TDD test files
├── test_data_fetcher.py
├── test_data_cache.py
├── test_backtest_engine_single.py
├── test_backtest_engine_portfolio.py
├── test_intrabar_fill.py
├── test_funding_fees.py
├── test_grid_search.py
└── test_slippage.py
```

### 5.2 Data flow

```
┌─────────────┐      ┌──────────┐      ┌──────────┐
│   CLI       │─────▶│  Cache   │─────▶│  Engine  │
│ (subcommand)│      │ (parquet)│      │  (pure)  │
└─────────────┘      └──────────┘      └────┬─────┘
       │                  ▲                  │
       │                  │                  ▼
       │            ┌─────┴────┐      ┌──────────┐
       └───────────▶│ Fetcher  │      │  Output  │
                    │ (CCXT)   │      │  Writer  │
                    └──────────┘      └──────────┘
                          ▲
                          │
                  Binance public REST
```

CLI selects mode (`single` / `portfolio` / `grid`); cache layer checks for parquet hit; on miss the fetcher pulls from Binance and writes parquet; engine runs the pure walk-forward simulation; output writer serializes results to `reports/backtests/{run_id}/`.

### 5.3 Boundary contracts

- **`data/fetcher`**: input = `(symbol, tf, start_ms, end_ms)`; output = `pd.DataFrame[ts, open, high, low, close, volume]`. Throttles to ≤ 2 req/s. No auth needed (public klines). For funding: `(symbol, start_ms, end_ms) → DataFrame[ts, fundingRate]`.
- **`data/cache`**: `get(symbol, tf, start_ms, end_ms) → DataFrame | None`; `put(symbol, tf, df) → None`. Reads parquet metadata for range check; falls through to fetcher on miss/gap.
- **`backtest/engine.run`**: input = `(symbols: list[str], dataframes: dict[symbol, dict[tf, DataFrame]], config: dict, initial_balance: float)`. Output = `BacktestResult` (dict, picklable). No file I/O, no network.
- **`backtest/grid`**: input = `(base_config, param_grid, symbols, period)`. Output = `list[BacktestResult]` plus a ranking summary.

## 6. Critical fixes incorporated from architecture review

### 6.1 SafeOrchestrator: `freshness_check` + `persist` params

Replace the brittle module-globals monkey-patch in current `runner.py:298-313` with explicit constructor flags:

```python
class SafeOrchestrator:
    def __init__(self, config, *, freshness_check: bool = True,
                 persist: bool = True, state_dir: str = ...):
        self.freshness_check = freshness_check
        self.persist = persist
        ...

    def run_cycle(self, symbol, h, m, e, d, balance):
        if self.freshness_check:
            validate_kline_freshness(...)
        ...

    def _persist_state(self):
        if not self.persist:
            return
        ...
```

Backtest mode passes `freshness_check=False, persist=False`. No more monkey-patches; multiprocessing-safe.

### 6.2 Single + portfolio mode in one engine

Symbol list is just a parameter:

```python
def run(symbols: list[str], data: dict, config: dict, initial_balance: float):
    orch = SafeOrchestrator(config, freshness_check=False, persist=False)
    for tick in walk_forward(data):
        for symbol in symbols:        # 1 symbol = single mode; 10 = portfolio mode
            orch.run_cycle(symbol, ...)
        update_mtm_equity(orch.lifecycle.positions, current_prices)
        check_breaker_globally(orch)
    return build_result(orch, ...)
```

No separate `portfolio.py` module. Portfolio mode is just `run(symbols=ALL_TEN, ...)`.

### 6.3 Intrabar fill simulation

For each open position at bar `i+1`:

```python
bar = next_bar
if pos.direction == "LONG":
    if bar.low <= pos.sl: fill_sl(price=min(bar.open, pos.sl))      # gap-down
    elif bar.high >= pos.tp1: fill_tp1(price=max(bar.open, pos.tp1)) # gap-up
elif pos.direction == "SHORT":
    if bar.high >= pos.sl: fill_sl(price=max(bar.open, pos.sl))
    elif bar.low <= pos.tp1: fill_tp1(price=min(bar.open, pos.tp1))
```

Closes at the **worse** of bar-open or trigger price. Avoids the systematic delay of "next-cycle close" fills.

### 6.4 MTM drawdown

`peak_balance` and `max_drawdown_pct` are computed on **mark-to-market equity** (`balance + sum(unrealized_pnl)`) every cycle, not only at position-close. Captures mid-trade drawdowns that recover.

### 6.5 Funding fees (Phase B critical)

Binance Futures charges funding every 8h (00:00, 08:00, 16:00 UTC). For 1y backtest, this can shift PnL by ±10–30%. Implementation:

- `data/fetcher.fetch_funding_rates(symbol, start, end)` → DataFrame
- For each open position at funding timestamp: `fee = position_notional × funding_rate × side_sign`
- Apply at the timestamp boundary; deduct from `balance`
- Tag in `trades.csv` as a separate `funding_total_paid` column per trade

### 6.6 `holding_bars` derived from `entry_tf`

```python
bar_minutes = pd.Timedelta(entry_tf).total_seconds() / 60
holding_bars = int((closed_at - opened_at).total_seconds() / 60 / bar_minutes)
```

No more `15m` hardcode.

### 6.7 Slippage model (per-leg, configurable)

`backtest/slippage.py` exposes:

```python
@dataclass
class SlippageConfig:
    entry_slip_pct: float = 0.05    # 5 bp adverse on market entry
    sl_slip_pct: float = 0.10       # 10 bp adverse on SL fills (gaps are worse)
    exit_slip_pct: float = 0.05     # 5 bp adverse on TP fills
```

Each fill price is adjusted in the adverse direction by the slip pct before being applied to balance. Per-leg config because SL fills are systematically worse than TP fills (Plan agent flagged this as real-world reality).

### 6.8 Reproducibility

`reports/backtests/{run_id}/provenance.json`:

```json
{
  "run_id": "a3f7b2c1",
  "started_at": "2026-05-04T14:23:11Z",
  "ended_at":   "2026-05-04T14:28:43Z",
  "wall_seconds": 332,
  "git_sha": "6712047...",
  "git_dirty": false,
  "pip_freeze_sha256": "9a8f7e6d...",
  "host": {"os": "Windows", "python": "3.14.0", "hostname": "..."},
  "data_manifest": {
    "BTC/USDT_15m": {"min_ts": 1714521600000, "max_ts": 1746057600000, "sha256": "..."},
    ...
  }
}
```

`pip_freeze_sha256` is `sha256(pip_freeze_output_bytes)` so we can detect dependency changes.

Grid search refuses to run on a dirty tree (commits should be clean before optimization). Single-mode warns but proceeds.

## 7. CLI surface

```
# Phase A: validate single symbol
python -m backtest.cli single --symbol BTC/USDT --period 1y \
    --config configs/config.phase2_1k.yaml \
    --balance 2000

# Phase A: validate portfolio
python -m backtest.cli portfolio --symbols BTC/USDT,ETH/USDT,XRP/USDT,DOGE/USDT,SOL/USDT,BNB/USDT,TRX/USDT,LINK/USDT,BCH/USDT,ADA/USDT \
    --period 1y --config configs/config.phase2_1k.yaml --balance 2000

# Phase C: grid search (param_grid via YAML)
python -m backtest.cli grid \
    --grid configs/grids/confluence_x_notional.yaml \
    --symbols BTC/USDT,ETH/USDT,...,ADA/USDT \
    --period 1y --workers 4
```

Grid YAML format:

```yaml
# configs/grids/confluence_x_notional.yaml
base: configs/config.phase2_1k.yaml
overrides:
  risk.min_confluence: [40, 45, 50, 55, 60]
  safety.max_position_notional_pct: [2.0, 3.33, 5.0, 7.0]
```

5 × 4 = 20 configs × 10 symbols = 200 individual runs. With 4 workers ≈ 17 hours wall.

## 8. Testing strategy (TDD)

| Test file | Target |
|-----------|--------|
| `test_data_fetcher.py` | range fetch with mocked CCXT, gap detection, throttle |
| `test_data_cache.py` | parquet round-trip, manifest update, gap re-fetch |
| `test_backtest_engine_single.py` | single-symbol walk-forward; deterministic results |
| `test_backtest_engine_portfolio.py` | shared breaker tripping across symbols halts all 10 |
| `test_intrabar_fill.py` | SL/TP detection at bar high/low; gap-through fills |
| `test_funding_fees.py` | 8h boundary application; sign convention (long pays positive) |
| `test_grid_search.py` | param_grid expansion; multiprocessing safety; ranking |
| `test_slippage.py` | per-leg slip applied in adverse direction |

Existing `backtest/runner.py` deleted with this work. Its 3 known issues (hardcoded 15m, monkey-patch, no slippage) are resolved by the rewrite, not by patching the legacy module.

## 9. Risks & open questions

- **Funding rate data availability**: Binance public funding history is ~3 years; 1y window safe. If fetch fails, backtest must fail loudly (not silently produce wrong PnL).
- **Cache invalidation on Binance kline revisions**: Binance occasionally revises old klines. The data manifest's sha256 will detect this; on mismatch, the cache file is rebuilt and a warning logged. (Phase B comparison must use freshly-fetched data, not stale cache.)
- **Leverage scaling sensitivity**: with new 5x live leverage, the position guard's FP-tolerance fix (`+ 1e-6` in `engine/safety/position_guard.py`) must hold across all grid configs. Add a regression test: every grid run asserts no `Size X exceeds max X` rejections at boundary.
- **Portfolio mode determinism**: `SafeOrchestrator._processed_signals` set is keyed by `(symbol, ts)`; multi-symbol single tick must process symbols in a deterministic order (alphabetical) for reproducibility.

## 10. Phase plan (high-level)

| Phase | Deliverable | Effort estimate |
|-------|-------------|------------------|
| 1 — Engine refactor + freshness/persist params | SafeOrchestrator changes, 66 tests still pass | 1 day |
| 2 — Data layer | fetcher, cache, manifest, 2 test files | 2 days |
| 3 — Backtest engine rewrite | engine.py, slippage, funding, intrabar fill, MTM DD, metrics, 4 test files | 3 days |
| 4 — Grid search | grid.py, multiprocessing, ranking, 1 test file | 1 day |
| 5 — CLI + reproducibility | cli.py, reproducibility.py, output writers | 1 day |
| 6 — Phase A validation runs | run portfolio + per-symbol on 1y data, write findings to `docs/results/` | 1 day |
| 7 — Phase C grid search | confluence × notional_pct grid; pick best config | 1-2 days (mostly compute wall time) |
| 8 — Phase B live-vs-backtest | replay live trade window in backtest mode; comparison report | 1 day |

**Total**: 10–12 working days. Phase 1–5 are blocking sequentially; Phase 6+ depend on data being available (which means cache populated once, cheap thereafter).

Phase 2 (web dashboard) is a separate design + plan, after Phase 8.

---

## Appendix A — Why these changes (rationale for major decisions)

### Why not keep `backtest/runner.py` as a deprecated wrapper?

Plan-agent review flagged the freshness-bypass as multiprocessing-unsafe. Wrapping it would carry that bug forward. Cleaner to fix the root cause (`SafeOrchestrator.freshness_check` flag) and rewrite the runner against the new contract. The behavior is preserved; the implementation is replaced.

### Why parquet (not SQLite or CSV)?

- **CSV**: too slow for 35k-bar reads; no schema enforcement.
- **SQLite**: requires schema migrations as columns evolve; not a great fit for tabular OHLCV.
- **Parquet**: native pandas/pyarrow support, columnar compression (~70% smaller than CSV), ts-range queries via metadata without opening file.

### Why CCXT for fetcher (not raw aiohttp)?

CCXT already handles rate limits, pagination edge cases, kline boundary semantics, IP-ban-on-burst recovery. Building a separate aiohttp client duplicates ~800 lines of nuance. The cost is one extra dependency we already have.

### Why drop `backtest/portfolio.py` (collapse into engine.py)?

Plan-agent review: "engine.py + portfolio.py would share 90% logic." Symbol list is a parameter; single-symbol mode is just `symbols=[ONE]`. Premature abstraction otherwise.
