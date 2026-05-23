# SMC v2 tp2 Optional[float] + Orphan SL Cleanup Implementation Plan (PR #S5.5)

**Goal:** Type-widen `tp2` to `Optional[float]` across 11 reader sites + wire orchestrator-side `_cancel_position_siblings` on single-target TP1.

**Tech Stack:** Python 3.14, asyncpg, Postgres.

## Task 1: exchange.Position dataclass + OrderManager.open_position widening

**Files:**
- `exchange/__init__.py` (Position dataclass + open_position signature + 3 construction sites)
- `backend/tests/test_exchange_tp2_optional.py` (new)

- [ ] Write failing tests for None handling in Position + dry_run path
- [ ] Position.tp2: float → Optional[float] = 0.0
- [ ] OrderManager.open_position: tp2 type → Optional[float]
- [ ] Internal: skip TP2 placement when tp2 is None; TP1 takes full size in that case
- [ ] Tests pass + existing 72 order_manager tests green
- [ ] Commit: `feat(exchange): widen Position.tp2 + open_position to Optional[float]`

## Task 2: on_tick guards (exchange/__init__.py:913 + 808)

**Files:**
- `exchange/__init__.py` lines 808 and 913
- Test extends Task 1's file

- [ ] Write failing test: `test_exchange_on_tick_sim_skips_tp2_when_none`
- [ ] Add `if pos.tp2 is not None:` guard at line 913
- [ ] Add `if pos.tp2 is None: return None` defensive at line 808
- [ ] Tests pass
- [ ] Commit: `feat(exchange): on_tick + tp2_hit guards for tp2=None`

## Task 3: report.py format safety

**Files:**
- `engine/report.py:134`
- `backend/tests/test_report_tp2_optional.py` (new, small)

- [ ] Write failing test for crash on None
- [ ] Conditional: `"NONE(single-target)" if p.tp2 is None else f"{p.tp2:,.2f}"`
- [ ] Tests pass
- [ ] Commit: `fix(report): handle tp2=None in position summary`

## Task 4: backtest serialization

**Files:**
- `backtest/metrics.py:29 serialize_trade`
- `backend/tests/test_backtest_metrics_tp2_optional.py` (new)

- [ ] Write failing test for `float(None)` crash
- [ ] Conditional: `float(p.tp2) if p.tp2 is not None else None`
- [ ] Tests pass + existing backtest tests still green
- [ ] Commit: `fix(backtest): serialize tp2=None as JSON null`

## Task 5: Migration 008 + db.py widening

**Files:**
- `backend/migrations/008_tp2_nullable.sql` (new)
- `backend/db.py record_trade_open` signature
- `backend/tests/test_db_tp2_optional.py` (new)

- [ ] Write failing test: `record_trade_open(tp2=None)` doesn't crash
- [ ] Migration: `ALTER TABLE trades ALTER COLUMN tp2 DROP NOT NULL;`
- [ ] db.py: `tp2: float` → `tp2: Optional[float]` in record_trade_open
- [ ] Tests pass + existing 11 db tests green
- [ ] Commit: `feat(db): migration 008 + record_trade_open tp2 Optional`

## Task 6: Orphan SL cleanup wiring (CRITICAL)

**Files:**
- `exchange/__init__.py _move_sl_to_breakeven`
- `backend/tests/smc_v2/test_single_target_cleanup.py` (new)

- [ ] Write failing test: `test_move_sl_to_breakeven_skips_be_and_cleans_siblings_for_single_target`
- [ ] Write regression test: `test_move_sl_to_breakeven_unchanged_for_two_target`
- [ ] Add guard at start of `_move_sl_to_breakeven`:
  ```python
  if pos.tp2 is None:
      ccxt_sym = self.client.to_ccxt_symbol(pos.symbol)
      self._cancel_position_siblings(pos, ccxt_sym, reason="TP1_FULL_CLOSE")
      return
  ```
- [ ] Tests pass
- [ ] Commit: `feat(exchange): cancel orphan SL on single-target TP1 fill`

## Task 7: Full suite + 2-pass review + push/merge

- [ ] Full backend suite: expect ~654 passed
- [ ] `efloud-code-reviewer` agent
- [ ] `efloud-risk-ops-reviewer` agent (REQUIRED — exchange/ + migration)
- [ ] Apply review findings
- [ ] Push branch + create PR
- [ ] Self-approve merge (Hermes mode, scope is technical prerequisite)
- [ ] Update memory file
