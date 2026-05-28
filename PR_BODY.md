## Summary

Fixes the 2026-05-11 live incident root cause where market entry could succeed while protective SL/TP placement failed, leaving exchange positions untracked/orphaned.

This PR changes `OrderManager.open_position()` from one broad try/except into explicit phases:

1. market entry
2. protective SL
3. TP1
4. TP2

## Behavior matrix

### Case A — entry order fails

- Return `None`
- Do not rollback, because no entry filled
- Do not open local state

### Case B — entry succeeds, SL placement fails

- Immediately attempt reduceOnly market rollback close using actual filled amount when available
- Do not place TP orders
- Do not append local position
- Return `None`
- Emit critical structured log:
  - `order_manager.entry_rollback_after_sl_failure` on rollback success
  - `order_manager.entry_rollback_failed` if rollback close also fails

### Case C — entry + SL succeed, TP1 fails

- Keep local position tracked because protective SL exists
- Preserve `sl_order_id`
- Leave failed TP order ids empty
- Emit warning structured log: `order_manager.tp_placement_failed_after_sl`

### Case D — entry + SL + TP1 succeed, TP2 fails

- Keep local position tracked because protective SL exists
- Preserve `sl_order_id` and `tp1_order_id`
- Leave `tp2_order_id` empty
- Emit warning structured log: `order_manager.tp_placement_failed_after_sl`

## Layering with PR #42

PR #42 makes orphan positions recoverable after detection via default-off orphan protection.

This PR prevents a major source of orphan creation in the first place by handling partial order-placement failures immediately inside the entry path.

## Tests run

Baseline before changes:

```text
python3 -m pytest backend/tests/test_order_manager_v2.py \
       backend/tests/test_order_manager_slippage.py \
       backend/tests/test_orchestrator_order_bridge.py \
       backend/tests/test_orphan_protection.py \
       backend/tests/test_position_guard_pause.py \
       backend/tests/test_reconcile_algo_orders_visibility.py -v
→ 80 passed, 4 warnings
```

RED phase:

```text
python3 -m pytest backend/tests/test_order_manager_atomicity.py -v
→ 8 failed, 2 passed
```

The two passing tests covered existing behavior; the 8 failing tests were the missing atomicity behavior.

GREEN phase:

```text
python3 -m pytest backend/tests/test_order_manager_atomicity.py -v
→ 10 passed
```

Final regression:

```text
python3 -m pytest \
  backend/tests/test_order_manager_atomicity.py \
  backend/tests/test_order_manager_v2.py \
  backend/tests/test_order_manager_slippage.py \
  backend/tests/test_order_manager_clock_unification.py \
  backend/tests/test_orchestrator_order_bridge.py \
  backend/tests/test_reconcile_algo_orders_visibility.py \
  backend/tests/test_orphan_protection.py \
  backend/tests/test_position_guard_pause.py \
  backend/tests/test_position_guard_quirks.py \
  backend/tests/test_position_guard_fp_regression.py \
  backend/tests/test_position_guard_tz_tolerance.py -v
→ 116 passed, 13 warnings
```

Compile:

```text
python3 -m py_compile exchange/__init__.py
→ pass
```

## Risk assessment

This is a behavior-changing safety PR. Unlike PR #38/#42, it is **not default-off**.

- Merge alone changes code on `master`.
- If an auto-deploy exists, behavior may become active after merge.
- If there is no auto-deploy, behavior becomes active on next manual container recreate/deploy.

Deploy mode observed on production earlier:

- No visible cron/systemd auto-deploy entries found.
- Current production container was created before PR #42 merge and is image-based, not bind-mounted source.
- Still, Hermes/Utku should treat merge as behavior-changing and review carefully.

## Production impact

- Does not touch current open positions directly.
- Only affects future `open_position()` attempts.
- If future entry fills but SL placement fails, bot will try to flatten immediately via reduceOnly market order.
- If TP placement fails after SL exists, bot keeps local tracking instead of orphaning the protected position.

## Rollback

Revert this PR. Main code behavior change is isolated to `exchange/__init__.py`; tests are in `backend/tests/test_order_manager_atomicity.py`.

## Related issues

- #43 — entry+SL+TP atomicity root cause
- #42 — orphan protection default-off recovery layer
- #45 — strategy SL from CHoCH/BOS break range with ATR fallback
- #46 — FIL reduceOnly close PnL mismatch

## Security & Scope Check

- [ ] **Live config touched?** (Check if config.yaml, .env, docker-compose.prod.yml, VPS deploy or mainnet risk settings were modified)
- [ ] **Research-only?** (Check if changes are fully isolated to candidate, backtest, or research/learning layers with zero production execution path impact)

## Approval gates

- [ ] Claude as-shipped review
- [ ] Hermes/Utku diff review
- [ ] Explicit merge decision
- [ ] Separate production deploy/recreate decision
