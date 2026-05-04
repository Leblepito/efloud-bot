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
└── cli.py                         argparse subcommands: single | portfolio | grid

# (api.py deferred to Phase 2 dashboard work — YAGNI per spec review)

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

### 6.1 SafeOrchestrator: full I/O purity audit + flags

Replace the brittle module-globals monkey-patch in current `runner.py:298-313` with explicit constructor flags AND audit every other I/O path. The "pure engine" claim only holds if **all** the following are addressed:

| I/O path in `SafeOrchestrator` and dependencies | Backtest behavior | Implementation |
|---|---|---|
| `_persist_state()` writes to `state_dir` | NO disk writes | `persist: bool = True` flag; `if not self.persist: return` |
| `validate_kline_freshness()` reads system clock | NO clock dependency | `freshness_check: bool = True` flag; skipped if False |
| `notification_manager.notify(...)` writes to log/email/webhook | NO external notifications | Inject `NullNotificationManager` (no-op subclass) in backtest mode |
| `logging.getLogger(...).info/warning/error` writes to file handler | Mute or route to per-worker StringIO | Backtest mode sets a `logging.NullHandler()` on the orchestrator subtree, OR uses `multiprocessing.get_logger()` with per-worker config |
| `time.time()` / `datetime.utcnow()` for timestamps | Use bar timestamp, not wall clock | Engine passes `current_ts` from the data into orchestrator state; SafeOrchestrator must accept this (audit needed) |
| `random.seed(...)` if any | Deterministic seed | Backtest sets `random.seed(0)` per run; document any stochastic call sites |

**Implementation steps:**

1. Add an explicit audit pass: `grep -nE "open\(|requests\.|time\.time|datetime\.now|datetime\.utcnow|logging\.getLogger" engine/safe_orchestrator.py engine/safety/ engine/intent.py engine/scenarios.py engine/risk/`
2. Each match is either: (a) safe (uses bar ts), (b) needs gating (add flag/dependency injection), or (c) acceptable in test mode.
3. The audit results go into a comment block at the top of `backtest/engine.py` listing every I/O point and how it's neutralized.
4. **Test (`test_engine_purity.py`)**: run a short backtest under `pyfakefs` filesystem (no real disk) AND with network blocked (`unittest.mock.patch("socket.socket")`) — must complete without errors.

```python
class SafeOrchestrator:
    def __init__(self, config, *,
                 freshness_check: bool = True,
                 persist: bool = True,
                 notifications: NotificationManager | None = None,
                 state_dir: str = ...):
        self.freshness_check = freshness_check
        self.persist = persist
        self.notifications = notifications or NotificationManager()
        ...
```

Backtest passes `freshness_check=False, persist=False, notifications=NullNotificationManager()`.

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

For each open position at bar `i+1`, evaluate which level triggers first based on `bar.open` proximity (deterministic tie-break since OHLC alone cannot reconstruct the within-bar path):

**Tie-break rule (explicit):**

```python
def resolve_fill(pos, bar):
    """Returns (level, fill_price) or (None, None) if neither hit."""
    sl_hit = (pos.direction == "LONG" and bar.low <= pos.sl) or \
             (pos.direction == "SHORT" and bar.high >= pos.sl)
    tp_hit = (pos.direction == "LONG" and bar.high >= pos.tp1) or \
             (pos.direction == "SHORT" and bar.low <= pos.tp1)

    if not sl_hit and not tp_hit:
        return (None, None)
    if sl_hit and not tp_hit:
        return ("SL", _adverse_fill(bar.open, pos.sl, pos.direction, "SL"))
    if tp_hit and not sl_hit:
        return ("TP1", _adverse_fill(bar.open, pos.tp1, pos.direction, "TP"))

    # Both hit in same bar — use bar.open distance heuristic:
    # whichever level is on the SAME side as bar.open from entry, that one fired first.
    # E.g. LONG: open below entry → SL was nearer in time → SL hit first.
    if pos.direction == "LONG":
        return ("SL", _adverse_fill(...)) if bar.open < pos.entry else ("TP1", ...)
    else:
        return ("SL", _adverse_fill(...)) if bar.open > pos.entry else ("TP1", ...)

def _adverse_fill(bar_open, trigger, direction, kind):
    """Always pessimistic: fill at the worse of bar.open or trigger price."""
    if kind == "SL":
        return min(bar_open, trigger) if direction == "LONG" else max(bar_open, trigger)
    else:  # TP
        return max(bar_open, trigger) if direction == "LONG" else min(bar_open, trigger)
```

**Properties:**

- **Pessimistic** — closes at the worse of `bar.open` or trigger price (avoids systematic optimism)
- **Deterministic** — same OHLCV → same fills, byte-identical results
- **Same-bar SL+TP collision rule**: explicit `bar.open` heuristic; documented as a known modeling limitation (truth requires tick data)

Tested in `test_intrabar_fill.py` with 6 cases: LONG/SL only, LONG/TP only, LONG/both with open<entry, LONG/both with open>entry, SHORT mirror, gap-through (bar.open beyond trigger).

### 6.4 MTM drawdown

`peak_balance` and `max_drawdown_pct` are computed on **mark-to-market equity** (`balance + sum(unrealized_pnl)`) every cycle, not only at position-close. Captures mid-trade drawdowns that recover.

### 6.5 Funding fees (Phase B critical)

Binance Futures charges funding every 8h (00:00, 08:00, 16:00 UTC). For 1y backtest, this can shift PnL by ±10–30%. Implementation:

- `data/fetcher.fetch_funding_rates(symbol, start, end)` → DataFrame[ts, funding_rate]
- For each open position at funding timestamp, the **balance impact** is:

  ```
  balance_delta = -side_sign × position_notional × funding_rate

  where side_sign = +1 for LONG, -1 for SHORT
  ```

  **Sign convention** (Binance documented behavior):

  | Direction | funding_rate | side_sign | balance_delta | Meaning |
  |-----------|-------------|-----------|---------------|---------|
  | LONG  | +0.01% | +1 | -0.01% × notional | Long PAYS positive funding |
  | LONG  | -0.01% | +1 | +0.01% × notional | Long RECEIVES negative funding |
  | SHORT | +0.01% | -1 | +0.01% × notional | Short RECEIVES positive funding |
  | SHORT | -0.01% | -1 | -0.01% × notional | Short PAYS negative funding |

- Apply at the timestamp boundary; mutate `balance` and append to `position.funding_paid_total` (cumulative)
- Tag in `trades.csv`: separate `funding_total_paid` column per trade

**Tests required (`test_funding_fees.py`)**: all 4 combinations from the table above + boundary case (position closes between funding timestamps → no fee applied for that window) + multi-funding case (position open across 3 funding events → cumulative deduction).

### 6.6 `holding_bars` derived from `entry_tf`

```python
def _tf_to_minutes(tf: str) -> float:
    """Normalize Binance/CCXT-style TF strings to minutes.
    Handles: '1m', '15m', '1h', '4h', '1d'. Raises ValueError for unknown."""
    tf_map = {"m": 1, "h": 60, "d": 1440, "w": 10080}
    if not tf or tf[-1] not in tf_map:
        raise ValueError(f"Unsupported timeframe: {tf!r}")
    return int(tf[:-1]) * tf_map[tf[-1]]

bar_minutes = _tf_to_minutes(entry_tf)
holding_bars = int((closed_at - opened_at).total_seconds() / 60 / bar_minutes)
```

No `15m` hardcode. Explicit normalization avoids `pd.Timedelta` quirks across TF strings.

### 6.7 Slippage model (per-leg, configurable)

`backtest/slippage.py` exposes:

```python
@dataclass
class SlippageConfig:
    entry_slip_pct: float = 0.05    # 5 bp adverse on market entry
    sl_slip_pct: float = 0.10       # 10 bp adverse on SL fills (gaps are worse)
    exit_slip_pct: float = 0.05     # 5 bp adverse on TP fills

def adverse_fill(price: float, direction: str, leg: str, cfg: SlippageConfig) -> float:
    """Apply per-leg slippage in the trader-adverse direction."""
    pct = {"entry": cfg.entry_slip_pct, "SL": cfg.sl_slip_pct, "TP": cfg.exit_slip_pct}[leg]
    sign = +1 if (direction == "LONG" and leg == "entry") or \
                  (direction == "SHORT" and leg in ("SL", "TP")) else -1
    return price * (1 + sign * pct / 100)
```

**Pyramid adds**: each pyramid entry pays `entry_slip_pct` on the **incremental notional** (not on the cumulative position). Exits (whole-position SL or per-half TP1/TP2) pay slippage on the closed notional only.

**Tests required (`test_slippage.py`)**:
- LONG entry adverse-up, LONG SL adverse-down, LONG TP adverse-down (4 cases × 2 directions = 8)
- Pyramid: 2 adds → each pays slippage on its incremental size, position avg_entry blends slipped prices
- TP1 partial close: half-size pays exit_slip_pct, remaining half not affected until TP2/SL

### 6.8 Reproducibility

`reports/backtests/{run_id}/provenance.json`:

If working tree is dirty in single mode, also write `provenance_diff.patch` (`git diff HEAD`) to the run dir so the exact code state is recoverable. Grid mode refuses dirty trees outright (since 200+ runs over 17h shouldn't sit on uncommitted code).

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

## 9. Risks, edge cases & operational concerns

### 9.1 Phase B prerequisites (live-vs-backtest comparison)

Public funding rate history alone is insufficient for Phase B. The live bot's actual paid funding can drift from `notional × rate` due to: timing precision (8h boundary vs entry), wallet partial fills, exchange-side rounding. To reconcile honestly:

- Fetch **private** trade history via `ccxt.fetch_my_trades(symbol, since)` for each symbol the live bot traded
- Fetch **private** funding history via `ccxt.fetch_funding_history(symbol, since)` (Binance: `/fapi/v1/income?incomeType=FUNDING_FEE`)
- Compare backtest output against live in two layers:
  - **Layer A**: trade-level — same entries/exits, prices within slip_pct tolerance
  - **Layer B**: PnL-level — backtest total vs live total balance change, reconcile within ±5% (more than that = funding/slippage model needs calibration)
- Phase B design adds `backtest/compare_live.py` with `CompareReport` output: per-trade match/miss matrix + PnL reconciliation table

This is added to Phase 8 in the phase plan.

### 9.2 Partial fetch failures + gap detection

`data/fetcher.fetch_ohlcv_range` contract returns `(df, gaps: list[(start_ms, end_ms)])`:

- `gaps` is non-empty if Binance returned fewer bars than `(end_ms - start_ms) / tf_ms`
- Backtest engine **refuses to start** if total gap duration > 1% of requested period (configurable via `--max-gap-pct`)
- Logged warning if 0 < gaps ≤ threshold; small gaps imputed via forward-fill (documented in result.json)

### 9.3 Cache corruption recovery

Parquet writes use atomic write-then-rename:

```python
def cache_put(symbol, tf, df):
    target = cache_path(symbol, tf)
    tmp = target.with_suffix(".tmp")
    df.to_parquet(tmp)
    os.replace(tmp, target)  # atomic on POSIX, near-atomic on Windows
    update_manifest(symbol, tf, sha256_of_file(target))
```

On read: `cache.verify(symbol, tf)` re-checksums the file against the manifest. Mismatch → delete file + manifest entry, re-fetch.

### 9.4 Grid search resumability

`backtest/grid.py` writes per-config result atomically to `reports/backtests/{grid_run_id}/configs/{config_hash}.json`. On (re-)start:

1. Compute config_hash for each entry in the grid
2. Skip configs whose result file already exists and passes JSON-schema validation
3. Print resume summary: "X/Y configs already complete, resuming with Z workers"

Critical for 17h+ grid runs that can be interrupted by any issue. Tested in `test_grid_search.py` with a forced mid-grid interruption + restart.

### 9.5 Other risks

- **Portfolio mode determinism**: `SafeOrchestrator._processed_signals` set is keyed by `(symbol, ts)`; multi-symbol single tick must process symbols in alphabetical order. `test_backtest_engine_portfolio.py` asserts byte-identical `result.json` across two runs with the same data.
- **Leverage scaling sensitivity**: new 5x live leverage may surface position-guard FP edge cases. Every grid run records `position_guard_rejections` count in result.json; CI test asserts 0 false-positive rejections at the cap boundary.
- **Cache invalidation on Binance kline revisions**: Binance occasionally revises old klines. The data manifest's sha256 detects this; on mismatch, the cache file is rebuilt and a warning logged. (Phase B comparison MUST use freshly-fetched data, not stale cache.)
- **Funding history depth**: Binance public funding history goes back ~3 years; 1y window is safe. If fetch fails, backtest fails loudly (not silently produce wrong PnL).

## 10. Phase plan (high-level)

| Phase | Deliverable | Effort estimate (realistic) |
|-------|-------------|------------------------------|
| 1 — SafeOrchestrator I/O purity audit + flags | freshness_check, persist, notifications params; full I/O grep audit; test_engine_purity.py | 1.5 days |
| 2 — Data layer | fetcher with gap detection, cache with atomic writes + verify, manifest, 3 test files | 2.5 days |
| 3 — Backtest engine rewrite | engine.py, slippage (per-leg + pyramid), funding (4 sign cases), intrabar fill (with same-bar tie-break), MTM DD, metrics, 4 test files | 4.5 days |
| 4 — Grid search + resumability | grid.py with checkpoint/resume, multiprocessing, ranking, 1 test file | 1.5 days |
| 5 — CLI + reproducibility | cli.py (3 subcommands), reproducibility.py (provenance + dirty-diff hash), output writers | 1.5 days |
| 6 — Phase A validation runs | run portfolio + per-symbol on 1y data, write findings to `docs/results/` | 1 day |
| 7 — Phase C grid search | confluence × notional_pct grid; rerun loop on bug discovery; pick best config | 2-3 days (compute wall time + iteration loop) |
| 8 — Phase B live-vs-backtest | private fetch_my_trades + fetch_funding_history; compare_live.py; reconciliation report | 1.5 days |

**Total**: 14–17 working days. Phase 1–5 sequential; Phase 6+ depend on data cache populated (one-time ~10min cost). Estimates revised upward from initial 10–12 days after spec review surfaced compression in Phase 3 (intrabar + funding + slippage all interact) and Phase 7 (iteration loop).

Phase 2 web dashboard is a separate design + plan, after Phase 8 lands.

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
