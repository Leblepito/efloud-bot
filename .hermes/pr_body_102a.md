## Summary

Fixes PR #99 post-deploy LINK/USDT bug: TP repair loop when price already passed TP target (Binance -2021 "Order would immediately trigger").

## Production incident (2026-05-28 14:41 UTC)

**Scenario**: LINK/USDT SHORT position with working SL (placed correctly by PR #99)

**Observed behavior**: Every 30s, reconcile ran `_repair_missing_protection_orders`:
```
CRITICAL repair_missing_tp: LINK SHORT TP1 → re-sending
WARNING tp_placement_failed_after_sl: error=binance {"code":-2021,"msg":"Order would immediately trigger."} attempts=1/3
CRITICAL repair_missing_tp: LINK SHORT TP2 → re-sending
WARNING tp_placement_failed_after_sl: ... -2021
```
~90 warnings/hour × 2 = 432 log lines/hour, wasting CPU + Binance API rate limit tokens.

**Root cause chain**:
1. SL protected ✅ (PR #99 success)
2. Price already passed TP1 target (SHORT position in profit zone)
3. Binance rejects TP placement with -2021
4. `_is_transient_error` returns False → no retry → `return ""`
5. `tp1_order_id` stays `""` → next cycle triggers repair again
6. ∞ infinite loop

## Fix

| Component | Change |
|-----------|--------|
| `_is_unreachable_error(exc)` | NEW helper: detects Binance -2021 / "would immediately trigger" |
| `_retry_tp_order` | Returns `"UNREACHABLE"` sentinel (truthy) on unreachable errors |
| `_repair_missing_protection_orders` | Skips TP repair when `tp1_order_id` or `tp2_order_id == "UNREACHABLE"` (subsequent cycles no longer retry) |
| `open_position` SL path | Handles `sl_oid == "UNREACHABLE"` same as `""` → immediate rollback (SL -2021 means position already at loss, must rollback) |
| Sentinel assignment | Emits `log.critical` with event `order_manager.tp_unreachable` for operator awareness |

## Semantic rationale

**Two distinct situations**:
- **TP -2021** (price passed TP target, position in profit zone):
  - Sentinel stops infinite loop
  - Position stays open with SL protection (operator manual decision for partial/full close)
  - Profit preserved, protected

- **SL -2021** (price already past SL level, position at loss):
  - Immediate rollback required
  - Keeping entry would mean holding position at loss without stop protection
  - Rollback triggered same as exhausted retry case

## Tests

**13 new tests** in `backend/tests/test_tp_unreachable.py`:
- `TestIsUnreachableError` (5): detection accuracy
- `TestRetryTPUnreachableSentinel` (4): sentinel return value
- `TestRepairSkipsUnreachable` (4): skip-on-sentinel behavior in subsequent cycles

**3 legacy test updates** in `test_order_manager_atomicity.py`:
- Changed generic `"would immediately trigger"` error text to `"market data delayed"` / `"SL failed — insufficient margin"` to match test intent (non-unreachable generic failure; -2021 scenario now covered in new suite)

**Regression suite** (111 OrderManager-related tests): ✅ all pass

## Files changed

- `exchange/__init__.py`: `_is_unreachable_error` helper, sentinel propagation in `_retry_tp_order`, SL rollback fix in `open_position`, sentinel skip in `_repair_missing_protection_orders`
- `backend/tests/test_tp_unreachable.py` (NEW): 13 tests
- `backend/tests/test_order_manager_atomicity.py`: 3 error text updates

## Risk assessment

- ✅ **Non-breaking** for production (bot_runner.py path unchanged)
- ✅ **No config changes** (CLAUDE.md §3 safe scope)
- ✅ **Dry-run mode unaffected** (sentinel logic only matters when exchange calls fail)
- ⚠️ **Operator visibility**: Sentinel events trigger `log.critical` for Telegram alerts when wired

## Verification

Local regression: 111/111 OM tests pass
Production expected: LINK/USDT loop stops after next reconcile cycle, position preserved with SL protection

## Security & Scope Check

- [x] Live config touched? **No**
- [x] Risk/safety parameters modified? **No**
- [x] Research-only? **No** (runtime fix for production bug)
- [x] Requires migration? **No** (sentinel stored in existing string field)

## Post-deploy monitoring

Watch for event `order_manager.tp_unreachable` (log.critical + Telegram alert). This event now means:
- Position identified as in-profit-zone
- Sentinel set, loop stopped
- Operator manual decision point

Refs: PR #99 (SL/TP reliability), investigation triggered by Hermes post-deploy report.
