# FVG offline replay — ADR-0011 offline gate for the target model (2026-11-14)

**Status:** operator-approved order (2026-11-14 "sıradaki işleri önerdiğin şekilde ve sıralama ile yap"); stacked on
PR #348 (shadow SL variant B + canonical cost). Tool only — no engine, config or order-path change.

## Why
ADR-0011 makes the offline NET-cost gate the main gate. `backtest.cli` forces `smc_v2.fvg_entry` off
(`backtest/engine.py::_offline_run_config`), so the target model (`docs/STRATEGY_INTENT.md`) cannot be measured
there. Forward shadow gives ~1–2 setups/day (2026-11-14 funnel), i.e. weeks for n ≥ 30. A walk-forward replay of the
**same shadow code** (`build_plans` + `FvgShadowBook`) over cached history gives the ADR-0011 offline result with
shadow↔offline parity by construction.

## Design
`tools/fvg_offline_replay.py` (CLI):
- Inputs: `--config` (default `configs/config.phase2_1k.yaml`), `--symbols` (default `engine.smc_v2_symbols`),
  `--days` (evaluation window, default 180), `--end` (fixed window end, ISO date; required for gate reports),
  `--cache-dir` (default `cache`), `--out` (JSON + markdown report path), `--is-frac` (default 0.67).
- Data: `data.cache.OHLCVCache` (filled by `python -m scripts.prefetch_data --config … --days N`); entry TF and MTF
  from `data/timeframes.py` profile of the config. Needs `kline_limit` bars of MTF history before the window
  (≈ 750 × 4h = 125 days for mid); missing history → hard error naming the symbol/TF (no silent short run).
- Walk-forward per closed entry bar t: entry window = last `kline_limit` bars ending at t; MTF window = closed MTF
  bars with close ≤ close(t), last `kline_limit`; LuxAlgo + bias + `build_plans` called exactly as
  `SafeOrchestrator._fvg_shadow_step` does (same config keys, same variants from `smc_v2.fvg_entry_sl_variants`).
  Bias is recomputed only when a new MTF bar closes (cache) — the result is identical, it only saves time.
- One process per symbol (`--symbols` single value) is the supported parallel mode (Windows MP hangs — see
  `docs/runbooks/backtest-gate.md`); a `merge` subcommand combines per-symbol JSON files into one report.
- Trades: parse the book's `exit` lines (variant, symbol, direction, gross_r, net_r, cost_r, entry/exit ts).
- Metrics per variant (pure functions, unit-tested): n, win rate, avg gross R, avg NET R, NET PF, max NET drawdown in
  R, IS vs OOS (split by exit time at `--is-frac`), symbols NET-positive share, avg cost_r.
- Verdict per variant against ADR-0011 offline criteria: n ≥ 100, IS and OOS avg NET R > 0, OOS NET PF ≥ 1.30,
  ≥ 60 % symbols positive → `PASS` / `FAIL (reasons)`; the report also states window end, git SHA, cost line and the
  number of variants tried.

## Out of scope
Changing any trading rule (TP1/FVG window etc.); backtest engine integration; live order path.

## Tests (TDD)
- metrics: PF, avg R, drawdown, IS/OOS split, symbol share on hand-built trade lists.
- verdict: each ADR-0011 criterion fails independently.
- exit-line parser: A/B lines, legacy lines without `v=`.
- MTF window selection never uses an unclosed MTF bar (look-ahead guard).
- missing history → error.
- tiny synthetic end-to-end run (fixture frames) produces deterministic trades.
