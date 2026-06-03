# Efloud Console — Strategy & Visual Handoff Report

**Date:** generated for the Phase 1–4 console upgrade handoff
**Active config:** `configs/config.phase2_1k.yaml` (production-active via
`.env.production → EFLOUD_CONFIG_PATH`; root `config.yaml` is the CLI default and is
**not** read in FastAPI mode).
**Build/test baseline:** `npm run build` → 0 errors · `pytest backend/tests tests`
→ **1268 passed / 6 skipped / 0 failures** · safety suites green & untouched.

---

## A. Active strategy configuration (the deployed parameter set)

| Group | Parameter | Value |
|---|---|---|
| Exchange | venue / market | Binance **Futures**, MAINNET (`testnet: false`) |
| Exchange | leverage | **5×** |
| Exchange | margin / position mode | **ISOLATED**, one-way (`hedge_mode: false`) |
| Engine | `smc_version` | **v2** (`smc_v2_symbols: ["*"]`, `smc_v2_shadow: true` → v2 logged, **v1 executes**) |
| Universe | symbols (10) | BTC, ETH, XRP, DOGE, SOL, BNB, TRX, LINK, BCH, ADA / USDT |
| Timeframes | profile | **mid** — entry `15m`, MTF `1h`, HTF `4h`, `kline_limit: 500` |
| Structure | swing / OB / range | `swing_lookback: 5`, `ob_sequential: 5`, `eq_threshold_pct: 0.1`, `range_lookback: 50` |
| Fibonacci | OTE / TP2 ext | `0.618–0.786` / `1.618` |
| Risk | risk per trade | **1.0%** (`max_loss_per_trade_usdt: 20`) |
| Risk | max open positions | **10** |
| Risk | min R:R / min confluence | **1.8** / **50** |
| Operation | cycle / mode | `check_interval_sec: 30`, `dry_run: false` (**real orders**), `parallel_workers: 3` |

## B. Risk & safety envelope (circuit breaker triggers)

| Guard | Threshold |
|---|---|
| Daily loss limit | **10%** → breaker TRIPS |
| Weekly drawdown limit | **25%** → breaker HALTS |
| Consecutive losses | 3 → pause 120 min |
| Starting balance | $2000 |
| Emergency balance HALT | **$1800** (−10%) |
| Per-trade notional cap | `max_position_notional_pct: 2.0` (~$200) |
| Total exposure cap | `max_total_exposure: 1.0` (~$2000, 1× net) |
| Max holding | 24h |
| Entry-drift guard | reject fill if live price > **1.0%** off signal entry |
| Post-placement SL/TP verify | on (3 attempts, market-close on SL failure) |
| PnL reconcile audit | on (every 20 cycles, corrects to Binance net realizedPnl) |
| Orphan protection | on (auto-SL on exchange-orphan positions) |

These are the **safety boundaries verified by the green test suite** — the console
upgrade did not alter any of them.

## C. SMC engine ↔ chart-overlay alignment

The new `/api/signals/smc` heuristic and the client `computeSMC` should mirror the
engine's structural sensitivity:

| Knob | Engine (`config.structure`) | Overlay default | Action |
|---|---|---|---|
| `swing_lookback` | 5 | 5 | ✅ already aligned |
| `range_lookback` / `range_bars` | 50 | 90 | ⚠️ **set overlay `range_bars: 50`** to match the engine's premium/discount range |
| `eq_threshold_pct` | 0.1 | n/a (geometric mid) | optional: apply a 0.1% EQ tolerance band |

> Recommended: expose `swing_lookback` & `range_bars` as `/api/signals/smc` query
> params (Reviewer R2) and have `InteractiveChart` pass the active config values so
> overlays are byte-for-byte consistent with what the engine trades on.

## D. Performance metrics — populate from your run artifacts

I did **not** fabricate Sharpe/Sortino/drawdown figures. Generate the real numbers
from the repo's own tooling and paste them here:

```bash
# Backtest the active config over a window (see backtest/cli.py for flags)
python -m backtest.cli --config configs/config.phase2_1k.yaml --report reports_1k/
# Live-vs-backtest reconciliation
python -m backtest.compare_live --journal state_1k/trade_journal.jsonl
```

| Metric | Value | Source |
|---|---|---|
| Net return (90d) | _fill_ | `reports_1k/` |
| Sharpe / Sortino | _fill_ / _fill_ | `backtest/metrics.py` |
| Max drawdown | _fill_ | `reports_1k/` |
| Win rate / Profit factor | _fill_ / _fill_ | `reports_1k/` |
| Live↔backtest divergence | _fill_ | `backtest/compare_live.py` |

> Note: the u2Algo design-system handoff quotes "median 90d Sharpe 2.8 / avg max DD
> −6.4%" — those are **marketing reference figures for the design system, not
> efloud's measured results**. Do not present them as this bot's backtest.

## E. Console visual validation results

| Phase | Delivered | Verified |
|---|---|---|
| 1 — Aesthetic | Design-engineered terminal: solid hairline panels, no glass/neon/emoji, `--ek-*` easings, tabular nums | ✅ build 0 err |
| 2 — Safety lock | TopBar `TESTNET SANDBOX` / `DRY-RUN` / crimson `MAINNET` badges from `useStatus()` | ✅ |
| 3 — Telemetry | `SYNCED/CONNECTING/OFFLINE` chip + bottom-right WS heartbeat; selected-row highlights | ✅ |
| 3.8 — Chart | SMC overlay primitive (BOS/ChoCh, OB, FVG, premium/discount, PDH/PDL) + SMC toggle + socket-driven feed pill | ✅ build 0 err |
| 4 — Backend | `/api/signals/smc` (engine-preferred, heuristic fallback) + `useSmcSignals` + `SMC: engine/heuristic/client/loading` HUD tag | ✅ build 0 err, +5 unit tests green |

Responsive: status grid 4→2→1, content grids collapse, tables fit without
horizontal scroll at 1320 / 1100 / 640. a11y: `aria-label`s on icon controls,
focus-visible rings, reduced-motion-gated animations.

## F. Open items (fast-follows, non-blocking — from the code review)

1. **MEDIUM** — cache `/api/signals/smc` per `(symbol,timeframe)` ~15–30s to avoid
   doubling Binance kline load under concurrent viewers.
2. Align overlay `range_bars` to engine `range_lookback: 50` (Section C).
3. Add route + engine-bridge tests (httpx monkeypatch; fake `smc_telemetry`).
4. Expose `swing_lookback` / `range_bars` as endpoint query params.
5. RTL/Playwright test for the SMC overlay toggle.

Full review: `docs/reviews/console_code_review.md`.
