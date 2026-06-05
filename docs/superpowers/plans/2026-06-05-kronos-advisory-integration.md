# Kronos Advisory Integration — Production-Ready Plan (v2)

**Date:** 2026-06-05
**Origin:** Improves the Gemini/Antigravity draft (`implementation_plan.md` + `walkthrough.md`)
via a 6-agent `ultracode` audit (live-ops, quant, microstructure, provider/cost, verification).
**Status:** Phases 0–5 (Claude) IMPLEMENTED in the working tree (default-OFF, no deploy).
Phases 6–7 (Gemini) handed off. Phase 8 deferred (post-deploy).

---

## 0. What this feature is

When the bot opens a trade (and, opt-in, on read-only signals), run the **Kronos**
time-series model on that coin, **synthesize** its forecast with the bot's SMC signal
via the advisory LLM, and surface the commentary + a categorical confidence band to
**Telegram** (and the DB when one is present).

**Hard invariant:** this layer is **additive & advisory-only**. Its output NEVER feeds
trade, sizing, SL/TP, or the confluence gate. Verified by grep across
`engine/risk/`, `engine/signals.py`, `engine/safe_orchestrator.py` — no feedback path exists.

---

## 1. Why the draft could not ship as-is (verified findings)

| # | Sev | Defect | Status |
|---|-----|--------|--------|
| D1 | **CRIT** | Unbounded concurrent torch subprocesses on the **shared** executor → OOM/starves the live loop | FIXED (Claude) |
| D2 | **CRIT** | First-run venv build (3–7 min) on the trade path → silent trading halt | FIXED (Claude) — prewarm gate |
| D3 | **HIGH** | No feature flag / kill switch | FIXED (Claude) — `kronos.enabled` default-off |
| D4 | **HIGH** | Hard `GeminiClient` bypasses `make_llm_client` → 404 → fake fallback in MiniMax prod | FIXED (Claude) |
| D5 | **HIGH** | No per-symbol cooldown/dedup | FIXED (Claude) |
| D6 | **HIGH** | yfinance **spot** vs Binance **perp**; basis read as false divergence | Phase 6 (Gemini) |
| D7 | **HIGH** | Alt universe mostly absent on yfinance → permanent fallback | Phase 6 (Gemini) |
| D8 | **HIGH** | Pseudo-precision: 1-sample 24h point forecast surfaced as 0–100 | Phase 8 (deferred) + band-only display now |
| D9 | **HIGH** | Two contradictory 0–100 numbers side-by-side | FIXED (Claude) — categorical band + ADVISORY label |
| D10 | MED | No asyncio timeout on synthesis | FIXED (Claude) — `synth_timeout_sec` |
| D11 | MED | Broad except swallows TimeoutError; logs fallback as success | FIXED (Claude) — narrowed + `source` tag |
| D12 | MED | No cache; float-laden prompt never hashes | FIXED (Claude) — bar-bucket cache |
| D13 | MED | Band regex passes `UNKNOWN` on drift | FIXED (Claude) — `(NARROW\|MODERATE\|WIDE)` → default WIDE |
| D16 | MED | Test spawns real torch subprocess (`5 passed in 1.90s` was stale/false — real 18.81s) | FIXED (Claude) — hermetic, 15 tests |
| D18 | LOW | 720-bar request vs `max_context=512` truncation | Phase 6/8 (config-driven) |

> **Walkthrough claim audit:** "5 passed in 1.90s" does **not** reproduce. The real
> full suite was 18.81s because `test_..._non_existent` now spawns a real torch
> subprocess (the runner script exists, and the venv is pre-warmed *only on the dev
> box* — gitignored, so CI/VPS would pay the 3–7 min install). Test suite is now hermetic.

**Correctly-wired in the draft (kept):** `TelegramNotifier.send/enabled`,
`Position.confluence_details{score,reasons}`, migration `011` numbering, `Optional` import.

---

## 2. Architecture (as implemented)

### Config block (`kronos:`, default-OFF) — committed to `config.yaml` + `configs/config.phase2_1k.yaml`
```yaml
kronos:
  enabled: false              # MASTER kill switch. false → fully inert.
  run_on: [trade_open]        # subset of [trade_open, readonly]; readonly = whole-universe fan-out (opt-in)
  data_source: yfinance       # yfinance (spot, today) | binance (native perp — Phase 6)
  interval: "1h"
  period: "1mo"
  pred_len: 12
  max_concurrency: 1          # dedicated bounded executor + Semaphore
  cooldown_sec: 3600          # per (symbol,direction,bar) dedup window
  synth_timeout_sec: 30
  prewarm_on_start: true
  show_numeric_confidence: false  # false → categorical band, no fake 0-100 next to confluence
```

### Concurrency model (the core safety change)
- **Dedicated bounded `ThreadPoolExecutor`** (`max_workers = max_concurrency`) on
  `BotRunner`. EVERY Kronos `run_in_executor` uses it — never the shared default pool.
- **`asyncio.Semaphore(max_concurrency)`** with **drop-if-busy** (`.locked()` → skip,
  never queue) so universe-wide bursts can't pile up torch loads.
- **Dedup/cooldown** keyed `(symbol, direction, bar_bucket)`; in-flight set; cooldown window.
- **Prewarm gate**: one background prediction at startup builds/warms the venv **off**
  the trade path; any failure sets `_kronos_available=False` → feature self-disables.

### Provider
`make_llm_client(cfg.kronos.llm | cfg.llm | cfg.agent_team | {})` — honours the global
`LLM_PROVIDER` lever (MiniMax in prod). `synthesize_signal_with_kronos` takes a
duck-typed `llm_client` and tags output `source: 'llm' | 'fallback'`.

### Output (prod is DB-less → Telegram is the live surface)
Categorical band by default, explicit `ADVISORY — did not affect this trade`, and a
`⚠️[fallback]` tag when the provider failed (a dead LLM is **visible**, not dressed up).
`db.update_trade_kronos_data` stays (inert when `pool is None`).

---

## 3. Cost model

| | Before (draft) | After (this plan) |
|---|---|---|
| Trigger | every readonly signal **+** every open | `trade_open` only (default) |
| Worst case | ~28,800 subprocess+LLM/day | ~1 per actual trade open (single-digit–low-tens/day) |
| Concurrency | unbounded | `Semaphore(1)` + drop-if-busy |
| Repeat within a candle | new call each time | cache hit (0 calls) |
| Memory | N × ~1–2 GB torch | 1 × torch at a time |

---

## 4. Work split

### [CLAUDE] — DONE (working tree, default-off, no deploy)
- **Phase 0** config flag + inert-by-default wiring gates (`bot_runner.py`, both configs)
- **Phase 1** provider factory + duck-typed client + `source` tag (`engine/ai/kronos.py`, `bot_runner.py`)
- **Phase 2** dedicated executor + semaphore + dedup/cooldown + cache (`bot_runner.py`)
- **Phase 3** synth timeout + narrowed exceptions + Telegram relabel + band regex (`bot_runner.py`, `kronos.py`)
- **Phase 4** prewarm/availability gate (`bot_runner.py`)
- **Phase 5** hermetic test suite — 15 tests, no subprocess/network (`backend/tests/test_kronos_integration.py`)

### [GEMINI] — handed off (see `docs/handoff/2026-06-05-kronos-gemini-handoff-prompt.md`)
- **Phase 6** Binance-native data feed into the runner (`kronos.py` `run_kronos_prediction(df=…)`,
  `external_repos/kronos-claude-skill/scripts/_predict.py` `--df-path`, `bot_runner` passes `df_entry`)
- **Phase 7** frontend Kronos dashboard card (render `kronos_comment` + categorical band, advisory-labeled)

### [DEFERRED] Phase 8 (post-deploy, Claude + quant)
- `sample_count ≥ 20` → empirical p10/p90 band; `interval`/`pred_len` aligned to entry TF
- shadow-log `{direction, band, change_pct}` vs realized R-multiple; falsifiable PF test (≥150 trades)
  before the numeric confidence is ever trusted/surfaced.

---

## 5. Rollout & verification

- **Branch:** `feat/kronos-advisory` off `master` (the working-tree changes currently sit on
  `fix/orphan-protect-algo-fetch-guard`, which carries an unrelated `reverse_from_risk` commit —
  move Kronos to its own branch before PR). Merge only on a **flat book** (live-bot workflow).
- **Gate:** Phases 0–5 green + hermetic (`pytest backend/tests/test_kronos_integration.py` < ~8s,
  no subprocess) before merge. Flag is `false` in committed config → merge is behaviorally inert.
- **Operator pre-warm (VPS, before first enable):**
  `python external_repos/kronos-claude-skill/scripts/run_kronos.py BTC-USD 1mo 1h 12`
  → confirm `external_repos/kronos-claude-skill/.venv` + `_kronos/` exist.
- **Staged enable (config-only):**
  1. `enabled: true`, `run_on: [trade_open]` (readonly OFF). Watch ≥24h: one tagged Telegram per
     open, `source` not `[fallback]`, RSS flat, `reconcile` cadence unaffected.
  2. Only if clean: consider adding `readonly` (cooldown-capped). Re-watch memory/latency.
  3. Phase 8 shadow study before trusting/surfacing any numeric confidence.
- **Kill switch:** `kronos.enabled: false` (default) → entire path inert. Runtime secondary:
  `_kronos_available=False` auto-disables on prewarm/venv/provider failure.
