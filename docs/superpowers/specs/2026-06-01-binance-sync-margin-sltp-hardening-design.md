# Design — Binance Sync, Margin Isolation & SL/TP Verification Hardening

**Date:** 2026-06-01
**Author:** Claude (brainstorming) — to be implemented by Gemini
**Source audit:** `direct_binance_reconciliation_report.md` (2026-06-01 02:48 UTC)
**Status:** Approved decomposition (C → B → A), pending spec review

---

## Problem Statement

A direct Binance API audit (last 24h) surfaced three independent defects on the
live mainnet bot:

1. **Hedge mode lets the bot hold opposite sides of the same symbol.** Live
   config is `margin_mode: CROSSED` + `hedge_mode: true`. Dual-side position mode
   means Binance itself permits simultaneous long+short on one coin. The bot's
   anti-flip guards read position side from **local state only**, so when local
   state drifts they fail to prevent it.
2. **Local PnL diverges from exchange truth (+87.44 local vs +32.42 real).** The
   bot records **gross** PnL using an **estimated** exit price
   (`_record_close` → `_estimate_exit_price`), deducting no fees/funding/slippage
   and not reading the exchange `realizedPnl`. The dashboard's `/history` &
   `/equity` panels are fed by this inflated local figure. 14 real losing trades
   were recorded locally as wins/wrong prices.
3. **No immediate confirmation that SL/TP orders actually landed.** SL/TP/TP2 are
   placed after entry, but verification is deferred to the *next* reconcile
   cycle. There is no 2-3s post-placement re-query + retry loop. A failed
   protection order can leave a position effectively bare until the next cycle.

## Goals

- The bot **cannot** open long+short on the same symbol (exchange-enforced).
- One symbol's volatility cannot drain the whole wallet (ISOLATED margin).
- Local PnL and the dashboard match Binance's real realized PnL + fees.
- Every entry is confirmed protected (SL + TP) within seconds, or the position
  is closed (SL) / tolerated with background retry (TP) — never silently bare.

## Non-Goals

- SMC v2 shadow → live promotion (roadmap item #3; out of scope here).
- Over-trading / 363-trades-per-day root cause (separate investigation).
- Changing entry signal logic, confluence scoring, or TF chain.

## Confirmed Codebase Facts (verified, not assumed)

- **Active prod config:** `configs/config.phase2_1k.yaml` (via
  `EFLOUD_CONFIG_PATH` in `.env`). Root `config.yaml` is the CLI default.
  Config edits target **`configs/config.phase2_1k.yaml`** and should be mirrored
  to `config.yaml` for consistency. *(Confirm the live VPS `EFLOUD_CONFIG_PATH`
  at deploy time — it may differ from the committed `.env`.)*
- **State file:** `order_manager_positions.json` (not `positions.json`). Atomic
  write via `_persist()` (`exchange/__init__.py:1545`). Prod is **DB-less**
  (`DATABASE_URL` unset) → `trade_journal.jsonl` + daily report are the durable
  PnL record; DB `/history` `/equity` are empty in prod.
- **`open_position` is synchronous** (`exchange/__init__.py:805`) and runs inside
  an executor (`bot_runner._run_loop` → `run_in_executor`). `_retry_tp_order`
  already uses `_time.sleep` for backoff (`:553`). An inline bounded verify loop
  with `_time.sleep(2–3s)` is consistent and will not block the event loop.
- **Existing pieces to reuse, not rebuild:**
  - `set_position_mode(dual_side=...)` already exists (`:194`, GET-first to avoid
    -4067) and `set_margin_mode(symbol, mode)` (`:167`, treats -4046 as success).
  - `bot_runner.py:165–193` already loops tradeable symbols calling
    `set_margin_mode` + `set_leverage`, then `set_position_mode(dual_side=hedge_mode)`
    once, and aborts startup on position-mode failure.
  - `_repair_missing_protection_orders(bn_order_ids)` (`:556`) re-sends missing
    SL/TP during reconcile; SL repair preserves full size.
  - `_rollback_entry_after_protection_failure` (`:732`) market-closes the entry
    when SL placement fails at open time.
  - `_is_unreachable_error` / `_TP_UNREACHABLE_SENTINEL` (`:384`) detect Binance
    **-2021 "would immediately trigger"**; `_is_real_oid` (`:434`) skips the
    sentinel so repair/cancel loops don't churn.
  - `positionSide` injection is gated on `self.hedge_mode`; when hedge is OFF the
    code already uses `reduceOnly=True` instead — so flipping to one-way needs no
    per-order-site changes.
  - Signal-level target-inversion guard `_enforce_tp2_beyond_tp1`
    (`engine/signals.py:98`) + deviation clamp `_resolve_deviation_tp2` (`:75`)
    already prevent TP2 ≤ TP1 at signal time.
  - `preflight.py` exists (root) — flat-book check will be added there.

---

## Decomposition & Rollout Order: C → B → A

Three atomic PRs (per the live-bot atomic-PR workflow), merged on a flat book.

| PR | Scope | Risk | Precondition |
|----|-------|------|--------------|
| **C** | PnL reconcile: real `realizedPnl` + fees + periodic income audit | Reporting-only; no order behavior change | None — flag-gated |
| **B** | SL/TP post-placement verify + repair/rollback loop | Bot-internal behavioral | None — flag-gated |
| **A** | Margin ISOLATED + one-way (hedge OFF) enforce + flat-book preflight | Exchange-side structural | **Flat book** (no open positions/orders) |

Rationale: C changes only reporting → lands first so B/A effects can be measured
against true exchange numbers. B is flag-gated and additive. A requires a flat
maintenance window and is exchange-irreversible mid-position, so it lands last.

---

## PR C — PnL Reconcile & Audit

**Goal:** Local recorded PnL equals Binance net realized PnL (realizedPnl −
commission − funding) for every closed position, and the dashboard reflects it.

### Data model (`exchange/__init__.py`, `Position` dataclass)
Add fields with **defaults** (backward-compatible restore from old JSON):
- `realized_pnl_exchange: float = 0.0` — net realizedPnl pulled from Binance.
- `commission_paid: float = 0.0` — summed commission for the position's fills.
- `funding_paid: float = 0.0` — summed funding fees over the position lifetime.
- `pnl_source: str = "estimated"` — `"estimated"` until reconciled, then `"exchange"`.

### Exchange read path (`BinanceClient`)
New method `fetch_realized_pnl(symbol, since_ms, until_ms=None) -> dict`:
- Primary: `fapiPrivateGetIncome` with `incomeType` in
  `{REALIZED_PNL, COMMISSION, FUNDING_FEE}`, filtered by symbol + time window.
- Returns `{realized_pnl, commission, funding, net}`.
- Errors fail **soft** → caller keeps the estimated value and leaves
  `pnl_source="estimated"` (never crash reconcile).

### Close path (`_record_close`, `:1384`)
- When a close is detected in `reconcile()`, after `_estimate_exit_price`, call
  `fetch_realized_pnl(symbol, since=position.opened_at_ms)` and set
  `pos.realized_pnl_exchange`, `commission_paid`, `funding_paid`, and
  `pnl_usdt = net`, `pnl_source = "exchange"`.
- If the exchange read fails, keep the estimated `pnl_usdt` and tag
  `pnl_source="estimated"` so the audit pass can correct it later.
- `_journal_record_close` (`:1407`) writes the net figure + source tag.

### Periodic audit sweep
- New `OrderManager.audit_realized_pnl(window_hours=24)`: pulls income history
  for the window, reconciles each journal entry whose `pnl_source != "exchange"`
  or whose value diverges beyond a tolerance, and rewrites the journal entry
  (append a correction record; never silently mutate history in place — keep an
  audit trail).
- Invoked on a low cadence from `reconcile()` (e.g. once per N cycles) or a
  dedicated timer; flag-gated by `safety.enable_pnl_audit` (default true).

### Dashboard (`backend/api.py`)
- `/positions` already reads exchange truth — leave as-is.
- `/history` & `/equity` (DB-backed, empty in prod) → add a journal-backed
  fallback that reads the corrected `trade_journal.jsonl` so the dashboard shows
  the reconciled net PnL even when DB-less. New helper, e.g.
  `read_journal_history()`.

### Tests
- `test_fetch_realized_pnl_income.py` — income endpoint parsing + soft-fail.
- Extend `test_order_manager_v2.py` / a new `test_record_close_realized.py` —
  `_record_close` uses exchange net when available, falls back to estimated.
- `test_pnl_audit_sweep.py` — audit corrects an estimated/divergent entry and
  appends a correction record.

---

## PR B — SL/TP Post-Placement Verify & Repair Loop

**Goal:** Confirm SL + TP orders are actually live on the exchange within seconds
of entry; repair transient failures; for permanent failures, close on missing SL
and tolerate (+ background retry) on missing TP. Never hold a silently bare
position.

### Config (`configs/config.phase2_1k.yaml`, mirror to `config.yaml`)
```yaml
safety:
  enable_post_placement_verify: true   # master switch for the inline verify loop
  verify_delay_sec: 2.5                 # wait before first re-query (user: 2–3s)
  verify_max_attempts: 3                # bounded retries before fallback decision
  rollback_on_sl_failure: true         # market-close if SL can't be confirmed
```
Wired in `bot_runner.py` (next to existing `max_entry_drift_pct` wiring `:217`).

### New method `OrderManager._verify_and_repair_protection(position) -> dict`
Called at the **end of `open_position`** (after SL/TP placement) and reusable
from `reconcile()`.

Per attempt (up to `verify_max_attempts`):
1. `_time.sleep(verify_delay_sec)`.
2. `fetch_open_orders(symbol)` + algo orders (same source as reconcile,
   `fapiPrivateGetOpenAlgoOrders`).
3. Check each expected protection order id (`sl_order_id`, `tp1_order_id`,
   `tp2_order_id` when set) is present **and** still backs the position size.
4. For any **missing** order: re-place via `_retry_tp_order`.
   - If re-place returns `_TP_UNREACHABLE_SENTINEL` (**-2021**): treat as
     **permanent** for this attempt — do not spin.

Fallback decision after attempts exhausted:
- **SL still unconfirmed** → if `rollback_on_sl_failure`, call
  `_rollback_entry_after_protection_failure` (existing market-close);
  emit a critical alert. *(Decision: never hold a position without a stop.)*
- **Only TP unconfirmed** (SL is live) → tolerate: leave position open, log a
  warning, mark the TP order id empty so the existing reconcile
  `_repair_missing_protection_orders` keeps retrying in the background. Permanent
  -2021 on a TP means price already passed it → genuinely unplaceable, accepted.

### Idempotency / safety
- Guard against double-placing: only re-send when the id is genuinely absent
  (reuse `_is_real_oid`); never duplicate a live order.
- The loop runs in the executor (sync) so the 2.5s sleeps don't block the loop.
- Behavior unchanged when `enable_post_placement_verify: false` (matches today).

### Tests
- `test_post_placement_verify.py`:
  - happy path: SL+TP present on first re-query → no action.
  - transient TP missing → repaired on retry, position kept.
  - SL missing after all attempts → rollback (market-close) + alert.
  - permanent -2021 on TP → tolerated, position kept, flagged for reconcile.
  - `enable_post_placement_verify: false` → loop is a no-op (regression guard).

---

## PR A — Margin ISOLATED + One-Way Enforcement

**Goal:** Exchange-enforced single-direction-per-symbol and per-symbol margin
isolation.

### Config (`configs/config.phase2_1k.yaml`, mirror to `config.yaml`)
```yaml
exchange:
  margin_mode: ISOLATED   # was CROSSED
  hedge_mode: false       # was true → one-way; Binance blocks long+short on one symbol
```

### Startup enforcement (`bot_runner.py:165–193`)
- Already loops symbols calling `set_margin_mode` + `set_leverage` and calls
  `set_position_mode(dual_side=hedge_mode)`. With config above, `dual_side=False`.
- Harden: if **margin-mode** set fails for a symbol (beyond the benign -4046
  "no need to change"), **abort startup** the same way position-mode failure
  already does — don't run half-isolated. Make the enforce result explicit in
  `self.last_error` and the health endpoint.

### Flat-book preflight (`preflight.py`)
- Add a check: query `get_open_positions()` and `fetch_open_orders()`; if **any**
  open position or pending order exists, **fail preflight** with a clear operator
  message ("Margin/position-mode change requires a flat book — close all
  positions and open orders, then restart"). This prevents a half-applied
  exchange state. Gate behind the fact that margin/hedge differ from the
  exchange's current setting (only enforce-flat when a change is actually needed).

### One-way order path
- No per-order-site change needed: `positionSide` injection is already gated on
  `self.hedge_mode`; with hedge OFF the code uses `reduceOnly=True`. Verify the
  anti-flip guards (`PositionGuard.can_open_position` opposite-direction reject)
  still behave correctly in one-way mode (they should — net position makes
  opposite entries reduce/close rather than stack).

### Deploy (operator runbook, not code)
- Stop bot → confirm flat book on Binance (no positions, no open orders) →
  deploy config → start → preflight confirms ISOLATED + one-way applied.

### Tests
- Extend `test_exchange_futures_methods.py`: `set_position_mode(dual_side=False)`
  POST path + -4059 success handling; `set_margin_mode` ISOLATED + -4046 success.
- `test_preflight_flat_book.py`: preflight fails when an open position/order
  exists and a margin/mode change is pending; passes on a flat book.
- Regression: one-way order params use `reduceOnly` (no `positionSide`).

---

## Cross-Cutting Concerns

- **Backward-compatible state restore:** new `Position` fields have defaults so
  `_restore()` loads old `order_manager_positions.json` without quarantine.
- **Soft-fail on exchange reads:** PnL/audit/verify reads must never crash the
  reconcile or entry path — degrade to existing behavior + alert.
- **Flag-gated:** C (`enable_pnl_audit`), B (`enable_post_placement_verify`) ship
  inert-capable so they can be toggled live without redeploy if needed.
- **Alerts:** SL-failure rollback and PnL audit corrections route through the
  existing `ops/alerter` path.

## Test Strategy

TDD per PR (red → green). Full suite (`pytest backend/tests -v`) must stay green
(baseline ~1139 tests). Each PR adds its own focused tests above. No live-mainnet
test calls — mock the exchange client.

## Open Items (confirm before/at deploy)

1. Confirm live VPS `EFLOUD_CONFIG_PATH` matches the committed `.env`
   (`configs/config.phase2_1k.yaml`) — apply config edits to the truly-active file.
2. Confirm live leverage value to bake into ISOLATED enforce (audit said 5x;
   committed `config.yaml` says 3 — reconcile which is intended).
3. PR A deploy needs a scheduled flat-book maintenance window.
