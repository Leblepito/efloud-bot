# efloud-bot Trading-Core Bug Hunt — 2026-06-05

**Method:** ultracode multi-agent Workflow (24 agents) over the trading-critical core
(signals, safety, lifecycle/risk, orchestrator, exchange, api/runner). Each subsystem
finder → adversarial refutation per finding → synthesis. 17 raw → **12 CONFIRMED, 1 UNCERTAIN**.
Run on master `635ad97` (post discovery-clamp deploy).

Verifiers were rigorous: downgraded 3 findings HIGH→MEDIUM, corrected one claim
(avg_entry_price breakeven-SL half is wrong — only the PnL half holds), and downgraded
the start() race to UNCERTAIN (only exploitable if DB enabled + breaker OPEN).

Recurring themes: **leverage/unit mismatches (3)**, **logical-vs-exchange desync (3)**,
**breaker-PnL corruption (cross-cuts #1/#2/#7)**.

---

## CRITICAL

### 1. Reconcile exit-price misattribution blinds the drawdown breaker
`exchange/__init__.py:1363, 1580-1598` — **CRITICAL** — exchange
`_estimate_exit_price` is fed `bn_orders_raw` (regular orders from `fetch_open_orders`),
but SL/TP are **algo orders** (algoIds) absent from that list. So for any dual-target
position the `tp2_order_id not in order_ids` branch is **always True** → exit always
attributed to `pos.tp2` (or `pos.sl` for single-target). An SL-hit **loss** is logged as
a TP2 **profit**; when `fetch_realized_pnl` soft-fails (rate-limit/timeout — designed to
soft-fail), that phantom PnL feeds `breaker.record_trade` → drawdown/consecutive-loss
under-counted → **breaker can fail to halt**. `audit_realized_pnl` never back-corrects the
breaker. Test-masked (tests inject `{'id':'SL-1'}` regular-shaped dicts).
**Fix:** pass the algo-inclusive `bn_order_ids` set into `_estimate_exit_price` (not
`bn_orders_raw`); gate attribution on `orders_fetch_ok`/`algo_fetch_ok` (fall through to
market price on failed fetch).

---

## HIGH

### 2. Max-holding force-close never closes the exchange — phantom PnL + same-direction stacking
`engine/safe_orchestrator.py:851-858` — **HIGH** — orchestrator — STEP 5 calls
`lifecycle.close_position` (logical-only, no exchange order) for positions past
`max_holding_hours:24` (prod). Logical marks closed at bar-close price (phantom breaker
PnL) while the **real Binance position stays open** and invisible to the dup-direction
guard → stacked same-symbol/direction positions (2026-05-08 failure mode).
**Fix:** mirror `_handle_reverse` — `order_manager._fallback_close(...)` (market reduceOnly
+ cancel siblings) before the logical close.

### 3. Kill-switch HALT not persisted — bot resumes trading after restart
`backend/api.py:297-309` — **HIGH** — api_runner — `_halt()` mutates breaker status in
memory only; the kill-switch handler never calls `_persist_state()` /
`db.upsert_breaker_state()`. A restart inside the ~30s cycle window reloads the stale OPEN
breaker → bot opens new positions, defeating the emergency stop. `/breaker/reset` was
already hardened against this exact window; kill-switch was not.
**Fix:** after `_halt(...)`, immediately `orch._persist_state()` and/or
`db.upsert_breaker_state(...)`.

---

## MEDIUM

### 4. Structural SL drops the ATR buffer whenever a prior swing exists
`engine/signals.py:536-540 (LONG), 581-585 (SHORT)` — **MEDIUM** — signals — SL set to the
**raw swing price**; buffer applied only to the `local_lo/local_hi` fallback, and the clamp
direction guarantees the buffered value is discarded (~96% of signals per Monte Carlo).
Stops sit on/above structure → stop-hunt targets, premature stop-outs. (Fail-safe for
risk sizing — tightens risk — but erodes win-rate.)
**Fix:** `sl = (sl_c[-1].price - buffer) if sl_c else local_lo` then `sl = min(sl, local_lo)`
(mirror `+`/`max` for SHORT).

### 5. Range-deviation play is permanently dead
`engine/smc.py:282-286` — **MEDIUM** — signals — `range_info` computes `hi/lo` over a window
that **includes the current bar**, so `dev_bull`/`dev_bear` are mathematically always False
(200k-sample empirical proof). The tight-SL override, EQ-as-TP1, opposite-extreme TP2, and
the +5 'Range deviation' confluence bonus **never execute**; deviation setups silently fall
through to trending/discovery geometry. Dead since initial commit; tests mock `range_info`.
**Fix:** exclude current bar — `r = df.iloc[-(lb+1):-1]` (guard `len(df)>=2`); add an
unmocked end-to-end test with a final sweep bar.

### 6. `reverse_from_risk` sizing under-sizes every trade by the leverage factor
`engine/risk/custom_calculator.py:56` + `engine/safe_orchestrator.py:1003-1005` — **MEDIUM**
— lifecycle_risk — orchestrator divides the calculator's **margin** figure by entry price as
if it were notional → position opened at `1/leverage` of intended size (5× under-risked at
leverage=5). Latent (all shipped configs use `legacy`) but a supported runtime lever;
fail-safe direction. **Fix:** `notional = calc.calculate_position_size(...) * leverage; size
= notional/entry` (or use `calc.calculate_notional_exposure()`).

### 7. `avg_entry_price` double-counts exited inventory after pyramiding past a TP1 partial
`engine/lifecycle.py:126-132` (via `safe_orchestrator.py:1250`) — **MEDIUM** —
lifecycle_risk — average computed over all original entries + adds without removing
already-exited cost basis → corrupted realized PnL fed to the breaker (daily-PnL aggregate +
consecutive-loss sign). **Verifier correction:** the breakeven-SL is set at TP1 *before* the
add, so the BE-stop claim is WRONG; only the PnL half holds. Drawdown breaker is shielded
(exchange equity resync), but the logical daily-PnL/consec-loss counters are not.
**Fix:** track a remaining-inventory cost basis (subtract `exit_size * current_avg` per exit,
divide by `remaining_size`).

### 8. `_handle_reverse` returns True when no matching exchange position found, even if still live on Binance
`engine/safe_orchestrator.py:574-616` — **MEDIUM** — orchestrator — on lifecycle-vs-
order_manager desync (`exchange_pos=None`), it skips the exchange close, closes logical,
returns True; caller sends the opposite side → under hedge-off/ISOLATED, Binance **auto-flips**
the still-live position uncontrolled with no SL/TP, leaving orphan algo orders. Trigger needs
a restart/manual-injection state divergence.
**Fix:** when `exchange_pos is None`, fetch live exchange positions; close any live opposite
first, else return False; or add a live-opposite guard in `open_position`.

### 9. Orphan protection treats failed algo-fetch as "missing SL" → duplicate close-position SL
`exchange/__init__.py:1334 (with 1266-1273)` — **MEDIUM** — safety — `'algo_orders' in
locals()` yields `[]` on any algo/order fetch failure, so `analyze_coverage` flags every
orphan as `missing_sl`; under prod config (`place_missing_sl` + `require_tp_present:false`)
it places a duplicate STOP_MARKET SL on a possibly-already-protected position. The sibling
`_repair` path is already guarded on `algo_fetch_ok`; this one was not.
**Fix:** `if ... detected_orphans and algo_fetch_ok:` (skip when coverage is unknowable).

---

## LOW (fail-safe; batch)

### 10. Total-exposure guard mixes margin and notional units
`engine/safety/position_guard.py:233-273` — **LOW** — safety — new position added as
**margin** while existing positions summed as full **notional** → exposure cap too permissive
by `(L-1)/L` for the new position (~8% over the 1.0× cap; bounded).
**Fix:** keep both terms full notional (don't reassign `notional` to margin before the
exposure check).

### 11. Daily-loss breaker: rolling-24h window vs calendar-midnight resume → re-trips after resume
`engine/safety/breaker.py:168-173 (with 228-233)` — **LOW** — safety — late-day losses stay
inside the rolling-24h window past midnight → breaker re-trips at the calendar-midnight
resume, extending the halt ~1 day. Fail-safe (over-conservative, self-clears).
**Fix:** align windows — sum trades since calendar midnight, or `resume_at =
oldest_today_trade_ts + 24h`.

### 12. WEAKNESS-exit dust gate compares asset units to a "USDT-notional" constant
`engine/lifecycle.py:479, 493` — **LOW** — lifecycle_risk — `MIN_REMAINING_SIZE=0.01`
(commented USDT) compared to `remaining_size` (asset units) → for BTC/ETH/BNB/BCH at prod
sizes post-TP1 the remaining is always `<0.01` → weakness-exit permanently suppressed; never
fires for sub-$1 coins. Fail-safe (holds a winner).
**Fix:** gate on notional — `if pos.remaining_size * price < MIN_REMAINING_NOTIONAL_USDT`
(rename, ~$5 floor).

---

## UNCERTAIN — needs human call

### No lock around `BotRunner.start()` — concurrent start/restart could spawn duplicate loops
`backend/bot_runner.py:117-167, 314` — **UNCERTAIN/LOW** — api_runner — mechanism real (no
`asyncio.Lock`, `running` set only at end), but single-threaded uvicorn means the only `await`
in the guard→`running=True` window is `db.load_breaker_state()`, a no-op pass-through in the
**DB-less** prod (pool=None) gated behind breaker==OPEN. Genuinely racy **only** if DB
persistence is enabled while breaker is OPEN.
**Human call:** confirm prod stays DB-less; if DB ever enabled, add `asyncio.Lock` around
`start()`/`restart`.

---

## Recommended fix order (atomic PRs)

1. **PR-1 (CRITICAL):** #1 reconcile exit-price algoId fix — blinds the drawdown breaker; highest blast-radius. `exchange/__init__.py`.
2. **PR-2 (HIGH):** #3 kill-switch persistence — tiny, restores emergency-stop invariant; mirrors `/breaker/reset`.
3. **PR-3 (HIGH):** #2 max-holding exchange-close — closes stacking + phantom-PnL hole; reuses `_fallback_close`.
4. **PR-4 (MEDIUM):** #9 orphan-protect `algo_fetch_ok` guard — one-line; same file as PR-1/PR-3 (sequence after).
5. **PR-5 (MEDIUM):** #8 `_handle_reverse` live-position check — completes desync triad with #2.
6. **PR-6 (MEDIUM):** #4 SL buffer, then #5 dead range-deviation — both `signals.py`/`smc.py`, both need unmocked e2e tests (two small PRs).
7. **PR-7 (MEDIUM):** #7 cost-basis — `lifecycle.py`; drop the corrected breakeven-SL claim from scope.
8. **PR-8 (latent):** #6 `reverse_from_risk` leverage — fix before the lever is flipped.
9. **PR-9 (LOW batch):** #10 exposure units + #11 breaker window + #12 dust gate — three fail-safe fixes.

All HIGH/CRITICAL items affect live-mainnet breaker accuracy, emergency-stop, or stacking
safety → land before the fail-safe LOW batch.
