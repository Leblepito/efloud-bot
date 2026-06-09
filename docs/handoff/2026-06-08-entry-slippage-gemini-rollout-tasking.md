# Gemini tasking — Entry-slippage rollout (PR split + backtest gate + testnet)

> Context: the engine implementation is DONE and Claude-audited (all 5 bugs fixed, telemetry
> wired, 108 tests green). Claude also added the measurement tool
> `scripts/analyze_entry_slippage.py`. Your remaining job is **rollout + measurement**, not
> more engine code. Full spec: the updated `implementation_plan.md`.

## Hard rules
- DO NOT re-edit the engine fixes (they are verified). DO NOT touch breaker / pos_guard /
  orphan-protection / lifecycle cost-basis / entry-drift guard.
- `engine/agents/*` stays additive advisory; never gate unless `agent_team.gating=true`.
- Committed mainnet configs keep the SAFE default `require_confirmation: true`. No config flip
  inside any code PR.
- TDD where you add code. Keep `python -m pytest tests/engine/ tests/scripts/ -q` green.

## TASK A — Atomic PR split + cleanup
Split the current working tree into 3 atomic PRs. EXCLUDE these stray files (do not commit):
`test_db.py`, `test_db_conn.py`, `test_postgres_only.py`, `pooler_test.py`, `region_scan.py`,
`dns_check.py`, `check_dns_rest.py`, `check_env.py`, `check_schema.py`, `combined_migrations.sql`,
`sb_vars.json`, and the runtime change to `state/ai_sentiment_registry.json`.
- **PR-A (telemetry, no behavior change):** `engine/journal.py` (TradeSnapshot fields),
  `engine/safe_orchestrator.py` `_journal_record_entry` + V1/V2 telemetry wiring,
  `scripts/analyze_entry_slippage.py`, `tests/engine/test_telemetry_slippage.py`,
  `tests/scripts/test_analyze_entry_slippage.py`.
- **PR-B (async review hardening):** the executor/dedup/defensive-attr/try-except/gating-preserve
  changes in `engine/safe_orchestrator.py` + `engine/agents/team.py` RLock +
  `tests/engine/test_async_agent_review.py`.
- **PR-C (require_confirmation fix):** the `_advance_setup_state_tick` zone-gate + clamp +
  `effective_pullback_timeout_bars` + `tests/engine/test_zone_touch_entry.py`. Configs unchanged
  (stay `true`).

## TASK B — Phase-4 backtest baseline gate
Run `scripts/evaluate_backtest_gates.py` (or the project backtest harness) on the SAME universe +
window, twice: WITH `require_confirmation` (baseline) vs WITHOUT. Produce a markdown verdict
comparing `win_rate`, `profit_factor`, `expectancy (R)`, `Sharpe`, `max_drawdown`, `trade_count`,
and mean/median signed `slippage_pct`. State clearly whether the flip is justified
(expectancy / PF / Sharpe not materially worse).

## TASK C — Testnet/shadow experiment config (off-mainnet)
Create `configs/config.zone_touch_experiment.yaml` (separate file) with
`smc_v2.require_confirmation: false` and v2 active, for TESTNET only. After a run, execute
`python scripts/analyze_entry_slippage.py --journal <testnet journal> --summary slip_after.md`
and compare against a baseline run to show the zone→fill gap shrank. Do not flip mainnet configs.

## TASK D — (optional) latency semantics
`latency_ms` currently measures bar-open → fill (includes the candle period). Either stamp a
wall-clock `decision_ts` at signal-promotion and use it, or add a one-line comment documenting
the current semantics. Low priority, advisory-only.

## Verification (paste in each PR)
```
python -m pytest tests/engine/ tests/scripts/ -q
python scripts/analyze_entry_slippage.py --journal state/trade_journal.jsonl
```
When A–C are done, the operator will run `/ultrareview` for the final cloud review.
