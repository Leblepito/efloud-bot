## Summary

Fixes critical bugs causing SL/TP orders to sometimes fail delivery after successful entry placement.

## Root cause

### BUG #1 — `main.py` OrderManager wiring incomplete (CRITICAL)
CLI mode (`python main.py`) constructed OrderManager with only `dry_run` and `trade_journal` params, ignoring config.yaml values for:
- `hedge_mode` — default false, even when config has `hedge_mode: true`. In hedge mode Binance expects `positionSide` parameter on SL/TP orders (not `reduceOnly`). Wrong mode → SL/TP silently rejected.
- `state_dir` — crash recovery disabled; duplicate SL/TP stacking on restart.
- `orphan_protector` — orphan positions not detected.

### BUG #2 — SL placement had no retry (unlike TP)
`open_position()` placed TP orders via `_retry_tp_order` (3 attempts, exponential backoff), but SL used a single try/except. Transient API error → immediate rollback or unprotected orphan.

### BUG #3 — `_repair_missing_protection_orders` repaired TP only
Reconcile's safety net caught missing TP1/TP2 but NOT missing SL. An exhausted SL placement left the position permanently unprotected.

### BUG #4 — `_move_sl_to_breakeven` had no retry, no recovery
After TP1 hit, old SL cancelled and new SL at entry placed. If new SL failed, the remaining half-position was left SL-less.

## Fix

| Area | Change |
|------|--------|
| `main.py` | Mirror `bot_runner.py` wiring (hedge_mode, state_dir, orphan_protector, on_position_change) |
| SL initial placement | Reuse `_retry_tp_order` (3 attempts, backoff) |
| `_repair_missing_protection_orders` | Add SL repair branch (highest priority) |
| `_move_sl_to_breakeven` | Retry wrapped; exhaustion sets `sl_order_id=''` for reconcile repair |

## Tests

- **13 new tests**: `test_main_om_wiring.py` (4) + `test_sl_retry.py` (9)
- **272 tests pass** across all OrderManager suites, 0 regressions
- TDD: all tests RED'd before implementation, GREEN'd after

## Files changed

- `.hermes/plans/2026-05-28_sltp-delivery-bugfixes.md` (NEW, +1015)
- `backend/tests/test_main_om_wiring.py` (NEW, +109)
- `backend/tests/test_sl_retry.py` (NEW, +257)
- `exchange/__init__.py` (+151, -40)
- `main.py` (+15, -2)

## Commits (atomic)

1. `bf430f2` fix(main): wire OrderManager with hedge_mode, state_dir, orphan_protector
2. `9c8b3c0` fix(exchange): add SL retry + repair mechanism for initial placement and breakeven
3. `8574825` docs: add SL/TP delivery bugfix implementation plan

## Risk assessment

- ✅ Non-breaking — `bot_runner.py` (production FastAPI path) unaffected; it was already correctly wired.
- ✅ Dry-run mode behavior unchanged.
- ⚠️ CLI mode (`python main.py`) behavior changes — now matches production wiring.

## Deploy path (requires Hermes/Utku approval per CLAUDE.md §3)

1. Code review (diff inspection)
2. Testnet dry-run: observe a few cycles
3. Merge: `git merge --no-ff fix/sltp-delivery-reliability`
4. VPS deploy: `cd /opt/efloud-bot && git pull && docker compose up -d`
5. Monitor logs 1-2h for `order_manager.repair_missing_sl` / `be_sl_placement_failed` events

## Security & Scope Check

- [x] Live config touched? **No** — config.yaml, .env, docker-compose unchanged.
- [x] Research-only? **No** — behavior-changing runtime fix.
- [x] Risk/safety parameters modified? **No** — pure order-plumbing reliability fix.

## Related

- Fixes root cause behind user-reported intermittent missing SL/TP orders
- Complements PR #42 orphan protection layer (default-off recovery)
- Complements PR #38 TP retry/atomicity work

Investigation triggered by user observation: "pozisyon entry oluyor ancak bazen SL veya TP emirleri iletilmiyordu."
