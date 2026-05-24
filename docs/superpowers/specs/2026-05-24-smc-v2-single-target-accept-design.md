# SMC v2 Single-Target Accept — Design Spec (PR #S6.5)

**Status:** Approved (Hermes 2026-05-24: "non-risk, Claude yapabilir")
**Branch:** `feat/smc-v2-single-target-accept`
**Predecessor:** PR #S6 (master `cdd01c5`)
**Successor:** PR #S7 (production rollout)

## 1. Goal

Remove the `tp2=None` early rejection in `_place_v2_entry_order` so v2 can
emit single-target setups end-to-end. All downstream support shipped in
prior PRs:

| Layer | PR | Provided |
|---|---|---|
| `Position.tp2: Optional[float]` | #S5.5 | dataclass accepts None |
| `OrderManager.open_position(tp2=None)` | #S5.5 | skips TP2 placement, TP1 = full size |
| `partial_close` single-target branch | #S5 | TP1 fill → full close |
| `on_tick` TP2 guard | #S5 | `pos.tp2 is not None` skip |
| `_move_sl_to_breakeven` cleanup | #S5.5 | cancels orphan SL on single-target TP1 |
| `record_trade_open(tp2=None)` | #S5.5 | nullable INSERT (migration 008) |
| State-reload preserves tp2=None | #S5.6 | restart doesn't downgrade to two-target |
| Notifications None-safe | #S5.6 | TP2: `NONE` marker |
| Shadow mode logs single-target | #S6 | tp2=None already serializes to JSON null |

## 2. Change

`engine/safe_orchestrator.py:1334-1336` — DELETE this block:

```python
# tp2 may be None (spec §4.2 single-target mode). Reject the setup
# rather than fold into a zero-distance double-fill — folding would
# cause OrderManager to send two TAKE_PROFIT_MARKET at the same
# stopPrice. Single-target lifecycle support lands in PR #S5.
if tp2 is None:
    log.info(f"[v2 reject] {cand.symbol}: tp2_none (single-target mode, deferred to PR #S5)")
    return None
```

The next line (sizing) handles tp2 transparently — `calc_position_size`
only reads `entry` and `sl`. `OrderManager.open_position` accepts `tp2=None`
since PR #S5.5. Telemetry (`tp2_target_type="NONE"`) already wired in PR #S5.

## 3. Inert invariant

In production today:
- `engine.smc_version=v1` (default) → v2 path unreachable
- `engine.smc_v2_symbols=[]` (default) → whitelist blocks all symbols
- `engine.smc_v2_shadow=true` (Hermes's planned shadow activation) → logged
  to file, NO order placed

After Hermes flips `smc_v2_shadow=false` (PR #S7 phase 1): a v2 candidate
producing tp2=None will:
1. Pass whitelist (if symbol is in `smc_v2_symbols`)
2. Pass all safety gates (breaker, pos_guard, pause)
3. Reach `OrderManager.open_position(tp2=None)` — PR #S5.5 path:
   - market entry order at full size
   - SL reduceOnly at full size
   - TP1 TAKE_PROFIT_MARKET at full size (instead of half)
   - TP2 placement SKIPPED entirely
4. On TP1 fill (detected by reconcile or polling):
   - `lifecycle.partial_close(reason="TP1")` early-returns to `close_position` (PR #S5)
   - `_move_sl_to_breakeven` detects `pos.tp2 is None` → calls
     `_cancel_position_siblings('TP1_FULL_CLOSE')` (PR #S5.5) — cancels
     orphan SL on Binance
5. DB row: `record_trade_open(tp2=None)` → SQL NULL (migration 008)
6. Telegram: notify_position_opened renders `TP2: NONE (single-target)`

## 4. Tests

`backend/tests/smc_v2/test_single_target_entry.py`:
1. `test_place_v2_entry_order_accepts_tp2_none_end_to_end` — when
   `calc_tp_targets` returns tp2=None, the helper calls `open_position`
   with `tp2=None` (no rejection)
2. `test_place_v2_entry_order_two_target_unchanged` — regression: numeric
   tp2 path identical to PR #71 baseline
3. `test_place_v2_entry_order_single_target_telemetry_correct` —
   `tp2_target_type="NONE"` passed through

## 5. Out of scope

- Backtest integration of single-target setups (already works — backtest
  uses same `_place_v2_entry_order` path, and PR #S5 lifecycle handles tp2=None
  in `on_tick`).
- Live exchange validation (Hermes-time activity during shadow → live
  rollout in PR #S7).

## 6. Acceptance

- 3 new tests green
- Full backend suite: 693 + 3 = 696 expected (was 693 after PR #S6)
- Zero regression on existing entry_order_placement tests
- v1 path strictly unchanged

## 7. Risk-ops gate

**OPTIONAL but recommended** (Hermes called it "non-risk"). The actual
production risk surface (order placement at tp2=None) is fully covered
by PR #S5/#S5.5/#S5.6 tests + reviews. PR #S6.5 just removes an early
rejection block. Single-pass code review is sufficient; risk-ops review
recommended for confirmation but not blocking.
