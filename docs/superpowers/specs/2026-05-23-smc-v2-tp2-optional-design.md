# SMC v2 tp2 Optional[float] Widening + Orphan SL Cleanup — Design Spec (PR #S5.5)

**Status:** Approved (Hermes 2026-05-23: "Claude yapsın, ayrı PR")
**Branch:** `feat/smc-v2-tp2-optional`
**Parent PR:** #S5 (telemetry, master `be1d135`)
**Successor:** PR #S6 (config flag flip — REQUIRES this PR)

## 1. Goal

Two technical-debt items flagged by PR #S5 reviewers that MUST land before the v2 flag flip (PR #S6):

**A. Widen `tp2` type from `float` to `Optional[float]` across all 11 reader sites.**
Today PR #S5 supports `tp2=None` only on `engine.lifecycle.Position`. `exchange.Position.tp2` is still `float` per dataclass, and 10 other reader sites assume non-None.

**B. Wire orchestrator-side orphan SL cleanup on single-target TP1 fill.**
PR #S5 lifecycle calls `partial_close` which delegates to `close_position`, but no `_cancel_position_siblings('TP1_FULL_CLOSE')` call. Without it, a v2 single-target TP1 fill leaves an orphan reduceOnly SL on Binance.

## 2. Inert today, critical for PR #S6

- v2 entry path (`_place_v2_entry_order`) currently REJECTS `tp2=None` (`if tp2 is None: log... deferred to PR #S5; return None`).
- PR #S6 will remove that rejection. After flag flip, v2 can emit `tp2=None` setups.
- Therefore PR #S5.5 MUST land before PR #S6 (or strictly atomically within S6).

## 3. Scope A: `tp2` type widening

### 3a. `exchange.Position` dataclass (PR #S5 missed this)
```python
# exchange/__init__.py:206
tp2: Optional[float] = 0.0  # WAS: tp2: float
```
Same default (`0.0`) for backward compat with persisted positions.

### 3b. `OrderManager.open_position` signature
```python
# exchange/__init__.py:380-389
def open_position(self, ..., tp1: float, tp2: Optional[float], ...) -> Optional[Position]:
```
Plus internal handling:
- TP2 placement is skipped when `tp2 is None`.
- `half_size = size / 2` is replaced when `tp2 is None` → TP1 takes full size.

### 3c. Reader audit + guards

| Reader | Current | Fix |
|---|---|---|
| `exchange/__init__.py:808 return pos.tp2` (TP2 detector) | reached only when TP2 order id exists | wrap: `if pos.tp2 is None: return None` (defensive) |
| `exchange/__init__.py:867 tp2_initial=pos.tp2` (reconcile siblings) | passes `pos.tp2` to lifecycle.close_position kwarg | None acceptable (close_position writes pos.tp2 as-is for trade record) |
| `exchange/__init__.py:913 price >= pos.tp2` (on_tick sim) | TypeError on None | guard `if pos.tp2 is not None:` (mirror lifecycle:445) |
| `engine/safe_orchestrator.py:381 tp2_initial=pos.tp2` | same as above | None acceptable |
| `engine/report.py:134 f"TP2: {p.tp2:,.2f}"` | format crash on None | ternary string: `"NONE(single-target)" if p.tp2 is None else f"{p.tp2:,.2f}"` |
| `backend/api.py:65 "tp2": p.tp2` | JSON None-safe (works) | no change — Python None → JSON null |
| `backtest/metrics.py:29 float(p.tp2)` | `float(None)` crashes | conditional: `float(p.tp2) if p.tp2 is not None else None` |
| `main.py:394 tp2=pos.tp2` (reverse handler) | forwards to OrderManager.open_position which now accepts None | no change after 3b lands |
| `backend/bot_runner.py:345 "tp2": pos.tp2` (JSON snapshot) | None-safe | no change |
| `backend/bot_runner.py:360 tp2=pos.tp2` (persist) | reaches db.record_trade_open(tp2: float) — needs db.py widening | db.py update |
| `backend/bot_runner.py:385 tp2=pos.tp2` (close persist) | same | db.py update |
| `tests/test_e2e_trace_id_correlation.py:88` | test sets numeric tp2 — no break | no change |

### 3d. `backend/db.py`

`record_trade_open` signature: `tp2: float` → `tp2: Optional[float]`. Postgres `trades.tp2 NUMERIC NOT NULL` constraint means we CANNOT insert NULL — would error. Two options:

**Option 1**: Migrate `tp2` column to nullable.
**Option 2**: Substitute a sentinel (e.g., 0.0 or tp1 itself) on insert.

**Decision**: Option 1. Migration 008 makes `tp2 NUMERIC NULL`. This is the cleanest contract — DB reflects reality. v1 still inserts numeric tp2. v2 single-target inserts NULL.

```sql
-- 008_tp2_nullable.sql
ALTER TABLE trades ALTER COLUMN tp2 DROP NOT NULL;
```

Postgres `ALTER COLUMN ... DROP NOT NULL` is metadata-only, instant, no table rewrite.

## 4. Scope B: Orphan SL cleanup wiring

### 4a. Single-target TP1 detection point

PR #S5's `lifecycle.partial_close` early-return branch:
```python
if reason == "TP1" and pos.tp2 is None:
    pos.tp1_hit = True
    return self.close_position(pos, price, "TP1")
```

This is the in-memory lifecycle. The exchange-side cleanup must happen at the orchestrator/reconcile callsite — the layer that owns the link between the in-memory Position and the exchange order IDs.

### 4b. Callsites that trigger TP1 close

Existing callsites for `lifecycle.partial_close(reason="TP1")`:
- `exchange/__init__.py: reconcile()` — detects TP1 fill via missing open order
- `exchange/__init__.py: _move_sl_to_breakeven` — after TP1 detection

The cleanup pattern (existing helper from PR #C1, used by `_fallback_close`):
```python
self._cancel_position_siblings(pos, ccxt_sym, reason="TP1_FULL_CLOSE")
```

### 4c. Wiring decision

Add a single guard inside `_move_sl_to_breakeven` (which today moves the SL to BE after TP1 partial):
```python
def _move_sl_to_breakeven(self, pos, avg_entry):
    if pos.tp2 is None:
        # Single-target mode — full close already done by lifecycle.
        # Skip BE move; cancel orphan SL + TP2 (if any).
        ccxt_sym = self.client.to_ccxt_symbol(pos.symbol)
        self._cancel_position_siblings(pos, ccxt_sym, reason="TP1_FULL_CLOSE")
        return
    # ... existing BE move logic
```

Inert today: `pos.tp2 is None` only happens when v2 emits a single-target setup, which v2 entry path currently rejects. Activated by PR #S6.

## 5. Tests

### 5a. exchange.Position widening
- `test_exchange_position_accepts_tp2_none`
- `test_order_manager_open_position_with_tp2_none_skips_tp2_order` (dry_run path)
- `test_order_manager_open_position_with_tp2_none_tp1_full_size` (dry_run, size handling)

### 5b. on_tick guard symmetry (exchange/__init__.py:913)
- `test_exchange_on_tick_sim_skips_tp2_when_none`

### 5c. report.py format safety
- `test_report_renders_single_target_position_without_crash`

### 5d. backtest/metrics.py serialization
- `test_serialize_trade_handles_tp2_none`

### 5e. db.py + migration
- `test_record_trade_open_accepts_tp2_none` (mocked pool)
- Migration 008: idempotency check in plan, no automated test (DB-dependent)

### 5f. Orphan SL cleanup wiring (CRITICAL)
- `test_move_sl_to_breakeven_skips_be_and_cleans_siblings_for_single_target`
- `test_move_sl_to_breakeven_unchanged_for_two_target` (regression)

## 6. Risk-ops gate

**REQUIRED.** Touches:
- `exchange/__init__.py` (Position dataclass + OrderManager signature + on_tick guard + cleanup wiring)
- `backend/migrations/008_tp2_nullable.sql` (DDL change on prod table)
- `backend/db.py` (signature change)

All changes are additive/forward-compatible from v1's perspective:
- v1 never produces tp2=None → cleanup branch unreachable
- DB NOT NULL drop accepts existing data → zero data loss
- type widening: Optional[float] is a strict superset of float

## 7. Out of scope

- Backtest harness changes (already handled in PR #S4)
- Config flag flip (PR #S6)
- Telegram notifications for single-target setups (operator log)

## 8. Acceptance

- 9 new tests (8 widening + 1 cleanup wiring); all green
- Full backend suite: 645 + 9 = ~654 passed
- v1 path strictly unchanged (numeric tp2 throughout)
- `grep -n "pos.tp2\\|p.tp2" --include="*.py"` shows zero unguarded numeric-only consumers
