# TESTS.md — test assets and required test points

This registry answers three questions: which tests exist, which rules need protection, and
where the evidence lives. The test code is the executable truth. This file is only an index.
Module → test-file mapping and rerun rules live in [`REGRESSION.md`](REGRESSION.md) (generated);
this file does not repeat them.

Every `path::node` written in backticks below must exist. `tests/ci/test_tests_registry.py`
checks this in CI, so a renamed or deleted test cannot silently orphan an entry.

## 1. Test entry points

| Execution group | Command | When to run | External dependencies |
|---|---|---|---|
| Default (Python) | `python -m pytest -q` | Before each PR; CI `pytest (py3.11)` | None (exchange, LLM and Telegram are faked) |
| Affected modules only | `python scripts/regression_ledger.py run --base origin/master` | After each change | Same as default |
| Frontend | `npm run typecheck --workspace efloud-frontend && npm run test --workspace efloud-frontend` | `frontend/` changes; CI `frontend` job | Node 20 |
| u2algo-site | `npm --prefix u2algo-site test` | `u2algo-site/` changes | Node 20; deps stubbed (`u2algo-site/scripts/_test_stub_deps.js`) |
| Secret scan | CI `gitleaks (working tree)`; daily `scheduled-review.yml` (full history) | Every PR / daily | gitleaks |
| Post-deploy canary | `python scripts/canary.py` | After every merge/deploy (site auto-deploys on merge) | Network (public URLs only; read-only) |
| Pine compile | TradingView MCP `pine_smart_compile` → 0 errors | `pine/` changes | TradingView Desktop (manual) |
| Edge / backtest gate | `python -m scripts.prefetch_data --config configs/config.phase2_1k.yaml --symbols <S> --days 365` then `python -m backtest.cli single\|portfolio --config configs/config.phase2_1k.yaml --period-days ≥60` (NET: the config's `backtest:` block; exit 3 when >1 % cycles raise). Gate verdict: `scripts/evaluate_backtest_gates.py` | Signal, scoring or parameter changes | Public Binance klines (cache); long-running (manual); slow tests in CI job `backtest (slow)` |

Windows note: before T-20261107-14, importing `main.py` closed pytest's capture stream, so the
local Windows suite crashed before running any test. With the fix the local suite runs
(3091 passed on 2026-11-07). One known Windows-only flaky test remains,
`tests/test_persist_crash_safety.py::test_concurrent_save_never_promotes_corrupt_file`
(file-lock race); it passes on its own.

## 2. Test asset map

Levels: `unit`, `integration`, `contract`, `E2E`, `smoke`. Purposes: `rule protection`,
`critical path`, `regression protection`, `specialized protection`.

| Module or workflow | Level | Purpose | Execution group | External deps | Location | Assessment |
|---|---|---|---|---|---|---|
| Safety: breaker, guards, orphan protection | unit, integration | rule protection, regression protection | default | none | `backend/tests/test_breaker_*`, `backend/tests/test_orphan_*`, `backend/tests/test_position_guard_*`, `tests/test_breaker_*` | required |
| Orders/reconcile (`exchange/`) | unit, integration | critical path, regression protection | default | ccxt faked | `backend/tests/test_exchange_*`, `backend/tests/test_reconcile_*`, `backend/tests/test_tp_*` | required |
| Orchestrator cycle | integration | critical path | default | exchange/LLM faked | `tests/engine/test_orchestrator_*`, `backend/tests/smc_v2/test_orchestrator_*` | required |
| SMC v1 signals + confluence | unit | rule protection | default | none | `tests/test_signals.py`, `tests/engine/` | required |
| SMC v2 | unit, integration | rule protection | default | none | `backend/tests/smc_v2/` | required |
| Position sizing (`risk/`) | unit | rule protection | default | none | `tests/risk/` | required (added 2026-11-07; the scan found no direct test before) |
| Configs (live `config.phase2_1k.yaml`) | unit | rule protection | default | none | `tests/config/` | required |
| Alerter (Telegram rules) | unit, contract | rule protection, regression protection | default | Telegram faked | `tests/test_alerter_*`, `tests/alerter/` | required |
| Backend API / healthz | integration, smoke | critical path | default | DB-less | `backend/tests/test_api_*`, `tests/test_healthz_*` | required |
| Panel | integration | rule protection | default | bot API stubbed | `tests/test_panel_unified.py` | required |
| Live-write hook | unit | specialized protection | default | none | `tests/hooks/` | required |
| CI workflows + ledger | unit | specialized protection | default | none | `tests/ci/` | required |
| Social pipeline | unit, integration | critical path | default | publishers faked | `backend/tests/social/`, `tests/social/`, `backend/tests/test_lane_*` | required |
| Frontend dashboard | unit | critical path | frontend | none | `frontend/` (vitest) | required |
| u2algo-site server | integration | rule protection | u2algo-site | deps stubbed | `u2algo-site/scripts/test_*.js` | required |
| Live E2E (real Binance) | E2E | critical path | — | mainnet | — | missing by design: only the testnet/shadow runbooks, no automated E2E against real money |

## 3. Cross-boundary contract evidence

| Boundary | Single contract source | Contract validation | Consumer evidence | Provider evidence | Integration evidence | Assessment |
|---|---|---|---|---|---|---|
| Bot log events → alerter rules | none (event names in `exchange/__init__.py`) | — | `tests/test_alerter_sl_failure_rules.py` rule tests | same file drives a real `OrderManager` | `tests/test_alerter_sl_failure_rules.py::test_contract_open_sl_failure` | unverifiable (no schema; producer and consumer are tested together on the real path) |
| Frontend / panel → backend `/api/*` | none checked in (FastAPI serves `/openapi.json` at runtime) | — | `frontend/` vitest, `tests/test_panel_unified.py::test_page_reads_real_bot_api_fields` | `backend/tests/test_api_*` | — | missing |
| Content job events | `docs/schemas/content_job-1.0.0.json` | `tests/test_content_jobs.py::test_schema_validation_passes` | consumers `scripts/lane_c_commentary.py`, `scripts/telegram_channel_collector.py`: no schema-driven test | `engine/content_jobs.py` validated by the same test | — | unverified |

## 4. Required test points

States: `missing`, `in progress`, `unverified`, `covered`, `not applicable`. **Prod** shows whether
the protection is active in the live config (`configs/config.phase2_1k.yaml`). A protection can be
`covered` in code and still be inactive in production, because many audit fixes are default-OFF flags.

### 4.1 Algorithm audit 2026-06-20 (C/H/M)

Source: `git show f96b7d8^:docs/handoff/2026-06-20-algorithm-audit-and-next-session-plan.md`
(remediation PR #232). The audit text holds the success criteria; this table holds the evidence.

| TEST-ID | State | Level | Observable expectation | Evidence | Prod |
|---|---|---|---|---|---|
| TEST-AUDIT-C1 | covered | integration | A failed live balance fetch blocks new entries; it never sizes against an invented $10k | `backend/tests/test_balance_unavailable_skip.py::test_live_balance_none_blocks_new_entries` | always on |
| TEST-AUDIT-C2 | covered | unit | Prod breaker calibration (starting balance / emergency / daily %) is internally consistent | `tests/config/test_phase_configs.py::test_prod_config_breaker_calibration_consistent` | live config |
| TEST-AUDIT-C3 | covered | unit | ML regime override cannot widen the entry gate | `tests/engine/test_regime_detector_ml.py::test_ml_override_cannot_widen_entry_gate` | `regime_ml_can_override_gate: false` |
| TEST-AUDIT-C4 | unverified | — | conf=50 operating point | Manual exit: NET-cost backtest gate + operator decision. A unit test cannot decide edge. | operator decision (conf=50) |
| TEST-AUDIT-H1 | covered | unit | `meta["structural_score"]` records the pre-bonus score (telemetry only) | `tests/engine/test_audit_h1_h5_h7_m1_fixes.py::TestH1StructuralScoreTelemetry` | on (telemetry) |
| TEST-AUDIT-H2 | covered | integration | A missing `smc_v2_shadow` key means shadow, with no live order | `backend/tests/smc_v2/test_shadow_mode.py::test_shadow_default_true_when_key_absent` | key explicitly `false` (live v2, operator 2026-07-07) |
| TEST-AUDIT-H3 | covered | unit | v1 SL wider than `max_sl_atr` is hard-rejected when the flag is on | `backend/tests/test_position_guard_wide_sl.py::test_wide_sl_hard_reject_when_flag_on` | `reject_wide_sl: true` |
| TEST-AUDIT-H4 | covered | integration | Entry-drift guard fails closed on a price-fetch error or zero price | `backend/tests/test_entry_drift_guard.py::test_open_position_rejected_when_price_fetch_fails_with_guard_on` | `max_entry_drift_pct: 1.0` |
| TEST-AUDIT-H5 | covered | unit | `meta["htf_bias_source"]` tags structural / slope / range fallback | `tests/engine/test_audit_h1_h5_h7_m1_fixes.py::TestH5HtfBiasSourceTelemetry` | on (telemetry) |
| TEST-AUDIT-H6 | covered | unit | OTE band from a mismatched swing-leg order is rejected | `tests/engine/test_ote_leg_validation.py::test_bull_ote_rejects_mismatched_leg_order` | always on |
| TEST-AUDIT-H7 | covered | unit | `strict_target_reject=True` drops a signal with no real target instead of clamping | `tests/engine/test_audit_h1_h5_h7_m1_fixes.py::TestH7StrictTargetReject` | **inactive**: `generate_signals` parameter, not wired from config |
| TEST-AUDIT-M1 | covered | unit | With the fix on, a real-liquidity ranging TP1 uses `fib_ext`, not 2.618 discovery | `tests/engine/test_audit_h1_h5_h7_m1_fixes.py::TestM1DiscoveryClassificationFix` | **inactive**: not wired from config |
| TEST-AUDIT-M2 | missing | — | Confluence over-counting / collinearity | Parked: needs a NET-cost backtest before any scoring change | — |
| TEST-AUDIT-M3 | covered | unit | OB body filter uses the high-low SMA(14), not true-range ATR (lock) | `tests/engine/test_ob_body_filter_atr.py::test_ob_body_filter_uses_high_low_sma_not_true_range` | always on |
| TEST-AUDIT-M4 | covered | integration | PnL-audit sign flip re-feeds the consecutive-loss counter | `tests/test_breaker_pnl_audit_backcorrect.py::test_audit_sign_flip_re_increments_consecutive_losses` | `breaker_backcorrect_consecutive: false` (audit itself on) |
| TEST-AUDIT-M5 | covered | integration | A position past `max_holding_hours` is force-closed, exchange leg first | `tests/test_max_hold_force_close.py::test_position_past_max_hold_is_force_closed_exchange_leg_first` | `max_holding_hours > 0` (live: 0 = off since 2026-11-08) |
| TEST-RISK-MAXHOLD-OFF | covered | unit | `max_holding_hours <= 0` or null disables the force close (no close, no aging warning, logged at startup); a positive value still closes; live config is 0 (operator 2026-11-08) | `tests/test_max_hold_disabled.py` | `max_holding_hours: 0` |
| TEST-OPS-TG-TRADES | covered | unit | Telegram trade visibility: open/TP1/close come only from the bot's direct notifier (alerter trade rules inactive → no duplicates); `safety.hold_alert_hours` logs one `HOLD_AGE` per position+bucket, never closes, forwarded raw (no AI rewrite) | `tests/test_hold_age_alert.py`, `tests/test_alerter_rules.py` | `hold_alert_hours: 24` |

### 4.2 Trading-core bug hunt 2026-06-05

Source: `git show f96b7d8^:docs/handoff/2026-06-05-trading-core-bughunt-report.md`. Every row
reproduces the original failure shape named in the report.

| TEST-ID | State | Level | Observable expectation | Evidence |
|---|---|---|---|---|
| TEST-BUG-BH01 | covered | integration | SL hit while TP2 is still live → exit = SL, not a phantom TP2 profit; failed fetch → market price | `backend/tests/test_tp_unreachable_sentinel_guards.py::TestEstimateExitPriceAlgoInclusive` |
| TEST-BUG-BH02 | covered | integration | Max-hold close closes the exchange first; on failure the logical position stays open | `backend/tests/test_max_hold_exchange_close.py::test_exchange_close_failure_keeps_logical_open` |
| TEST-BUG-BH03 | covered | integration | Kill switch persists the breaker HALT immediately | `backend/tests/test_kill_switch_persist.py::test_kill_switch_persists_breaker_halt` |
| TEST-BUG-BH04 | covered | unit | Structural SL subtracts the ATR buffer from the swing | `tests/test_signals.py::TestStructuralSLBuffer` |
| TEST-BUG-BH05 | covered | unit | Range deviation is reachable (last bar sweeps and closes inside) | `tests/engine/test_range_info_deviation.py::test_bull_deviation_detected_when_last_bar_sweeps_low_and_closes_inside` |
| TEST-BUG-BH06 | covered | unit | `reverse_from_risk` sizing realizes the full configured max loss | `backend/tests/test_custom_calculator_sizing.py::test_contract_size_realizes_full_max_loss_not_a_leverage_fraction` |
| TEST-BUG-BH07 | covered | unit | `avg_entry_price` reflects remaining inventory after pyramiding past TP1 | `backend/tests/test_avg_entry_cost_basis.py::test_avg_remaining_inventory_after_pyramid_past_tp1` |
| TEST-BUG-BH08 | covered | integration | `_handle_reverse` aborts when an untracked opposite position is live, or when the check errors | `backend/tests/test_handle_reverse_live_check.py::test_aborts_fail_safe_when_live_check_errors` |
| TEST-BUG-BH09 | covered | integration | Orphan protection skips when the algo-order fetch fails (no duplicate SL) | `backend/tests/test_orphan_protect_algo_guard.py::test_orphan_protect_skipped_when_algo_fetch_fails` |
| TEST-BUG-BH10 | covered | unit | Total-exposure guard counts the new position as full notional | `backend/tests/test_position_guard_exposure_units.py::test_exposure_rejects_when_full_notional_exceeds_cap` |
| TEST-BUG-BH11 | covered | unit | Daily-loss window is the calendar day, matching the midnight resume | `backend/tests/test_breaker_daily_window.py::test_daily_loss_uses_calendar_day_not_rolling_24h` |
| TEST-BUG-BH12 | covered | unit | WEAKNESS-exit dust gate compares notional, not asset units | `backend/tests/test_lifecycle_dust_gate.py::test_weakness_not_suppressed_for_high_priced_asset` |

### 4.3 Incidents and operational defects

| TEST-ID | State | Source | Observable expectation | Evidence |
|---|---|---|---|---|
| TEST-INC-20260514-BARE | covered | Incident 2026-05-14: positions found on Binance without TP/SL | A live position with no SL gets a close-position SL placed (prod `mode: place_missing_sl`); SL failure on open raises a CRITICAL alert | `backend/tests/test_orphan_protection.py::test_place_missing_sl_mode_places_on_unprotected`, `backend/tests/test_orphan_protection.py::test_long_orphan_places_sell_close_position_stop_market`, `tests/test_alerter_sl_failure_rules.py::test_contract_open_sl_failure` |
| TEST-INC-20260530-DOUBLE | covered | 2026-05-30: reconcile → breaker double count | A reconciled close is recorded in the breaker exactly once (daemon and CLI) | `backend/tests/test_reconcile_breaker_sync.py::test_reconciled_close_records_pnl_when_logical_open`, `backend/tests/test_cli_reconcile_parity.py::test_main_run_cycle_no_double_count` |
| TEST-BUG-WIN-STDOUT | covered | T-20261107-14 | Importing `main` leaves `sys.stdout`/`sys.stderr` untouched | `tests/test_main_import_keeps_stdout.py::test_import_main_leaves_std_streams_alone` |
| TEST-RISK-001 | covered | REGRESSION.md gap (T-20261107-12) | Size = risk ÷ SL distance; the notional cap wins when smaller; zero distance → 0 | `tests/risk/test_position_size.py::test_notional_cap_wins_when_smaller` |

### 4.4 Telegram protection alerts (T-20261107-03 / -05 / -11)

| TEST-ID | State | Observable expectation | Evidence |
|---|---|---|---|
| TEST-ALERT-TP | covered | TP placement failure after SL → alert (default OFF, on in prod) | `tests/test_alerter_tp_failure_rules.py::test_failed_tp_leg_fires` |
| TEST-ALERT-SL | covered | SL repair failure → CRITICAL "unprotected" alert on the real `OrderManager` path | `tests/test_alerter_sl_failure_rules.py::test_contract_sl_repair_failure_is_unprotected` |
| TEST-ALERT-ORPHAN | covered | An untracked live position keeps alerting hourly per (symbol, side) | `tests/test_alerter_orphan_position_rule.py::test_fires_with_details` |
| TEST-ALERT-CRITICAL-RAW | covered | CRITICAL alerts bypass the LLM formatter; breaker text and LLM fields are HTML-escaped; a Telegram HTML rejection is resent as plain text (LLM audit A3/A4) | `tests/test_alerter_critical_formatting.py::test_critical_alert_bypasses_llm_formatter`, `tests/test_alerter_critical_formatting.py::test_html_parse_rejection_is_retried_as_plain_text` |
| TEST-LLM-002 | covered | The synchronous LLM structure validation is OFF unless `engine.structure_validation.enabled: true`; when off it is not called at all (live: 23,085/23,085 fallbacks) | `tests/test_structure_validation_flag.py::test_default_does_not_call_the_llm` |
| TEST-LLM-001 | covered | LLM macro sentiment never moves the confluence score (telemetry in `sig.meta["macro_sentiment"]`); writer, engine and dashboard use the same `state_dir` | `tests/test_sentiment_telemetry_only.py::test_sentiment_does_not_move_the_confluence_score`, `tests/test_sentiment_telemetry_only.py::test_runner_writes_into_its_own_state_dir` |

### 4.5 Security audit 2026-11-06

Source: `collab/tasks/open/T-20261106-06-security-audit.md` (neutral summary; details are in the
private store). Every finding is fixed and has a test.

| TEST-ID | State | Observable expectation | Evidence |
|---|---|---|---|
| TEST-SEC-01 | covered | Live-write hook asks on scheme-less hosts, `ssh`, and compose verbs; adversarial input stays fast | `tests/hooks/test_live_write_gate.py::test_gate_gaps_found_in_2026_11_06_audit_get_ask`, `tests/hooks/test_live_write_gate.py::test_adversarial_ssh_compose_input_stays_fast` |
| TEST-SEC-02 | covered | u2algo-site serves only allowlisted static paths; waitlist and webhook limits hold | `u2algo-site/scripts/test_server_http.js` (`npm --prefix u2algo-site test`) |
| TEST-SEC-03 | covered | Panel rejects cross-site actions even with the header; repeated wrong passwords → 429 | `tests/test_panel_unified.py::test_cross_site_action_is_rejected_even_with_header`, `tests/test_panel_unified.py::test_repeated_wrong_passwords_get_429` |
| TEST-SEC-04 | covered | The CI reviewer runs base-branch code only; workflow inputs reach the shell only through env | `tests/ci/test_workflow_hardening.py::test_hermes_review_inputs_not_interpolated_into_shell` |
| TEST-SEC-05 | covered | Test fixtures carry no real-looking credentials | CI `gitleaks (working tree)` job; `backend/tests/test_xurl_client.py` uses a synthetic value |
| TEST-SEC-06 | covered | `.mcp.json` npx/uvx servers stay pinned to an exact version (no range, no `latest`) | `tests/ci/test_mcp_pins.py::test_every_mcp_package_is_pinned_exactly` |

### 4.6 Marketing site SEO / share cards (T-20261107-18)

| TEST-ID | State | Observable expectation | Evidence |
|---|---|---|---|
| TEST-SEO-001 | covered | Every sitemap page has a title of 10–65 chars, a description of 50–170 chars, a canonical equal to its sitemap `loc`, one `<h1>`, a 1200×630 PNG `og:image` + `twitter:image`, and no `#fragment` hreflang | `u2algo-site/scripts/test_seo_meta.js` (`npm --prefix u2algo-site test`) |
| TEST-SEO-002 | covered | `www.u2algo.com` page requests get a 301 to the apex with path and query kept; `/healthz` and `/api/*` are never redirected | `u2algo-site/scripts/test_server_http.js` (`npm --prefix u2algo-site test`) |

### 4.7 Social publishing (T-20261107-19)

| TEST-ID | State | Observable expectation | Evidence |
|---|---|---|---|
| TEST-SOCIAL-001 | covered | Operator approval records a digest of caption/thread/alt text/media bytes; a bundle edited after approval, or approved without a digest, is refused (`approval_stale`) | `tests/test_lane_g_publish.py::TestApprovalIsBoundToContent` |
| TEST-SOCIAL-002 | covered | The X coin hashtag follows the post's symbol (`#SOL`, not a fixed `#BTC`); unsafe symbols produce no tag | `tests/test_social_publishing.py::TestBuildCaption` |
| TEST-VIDEO-001 | covered | A voice-over clip lasts as long as the narration (not cut at the 8 s default), an explicit duration still wins, and the voice is normalised to about −16 LUFS | `tests/test_video_render_voiceover.py::test_voiceover_longer_than_default_is_not_cut`, `tests/test_video_render_voiceover.py::test_voiceover_is_loudness_normalised` |

### 4.8 Backtest live parity (spec 2026-11-07)

| TEST-ID | State | Observable expectation | Evidence |
|---|---|---|---|
| TEST-BT-001 | covered | Exits match the exchange: TP1 50 % then the stop moves to break-even, then TP2; single-target closes 100 % at TP1; SL wins a bar that also touches TP1; TP2 is never filled in the TP1 bar | `tests/backtest/test_live_parity.py::TestResolveExit`, `tests/backtest/test_live_parity.py::TestEngineExits` |
| TEST-BT-002 | covered | A plain run uses the live config's `smc_version`; agent team and Kronos are off and the LLM factory is a null client during the run; the live config makes runs NET | `tests/backtest/test_live_parity.py::TestLiveConfigAndOffline` |
| TEST-BT-003 | covered | Backtest trades are reconciled against live trades on simulated bar time, not wall clock | `tests/backtest/test_live_parity.py::test_reconcile_matches_backtest_trades_on_simulated_time` |
| TEST-BT-004 | covered | The breaker runs on sim-time in backtest: closed trades are recorded at the cycle time and the v2 entry gate checks at the cycle time, so an old simulated loss never counts as "today" (repro: SOL/USDT 41d daily-loss trip on the whole run); live (`now=None`) keeps the wall clock ; a TRIPPED pause is judged at the sim-time it was checked (`BreakerStatus.as_of`), so consecutive-loss and daily-loss pauses really block in backtest; the weekly peak is stamped and rebased on sim-time (7 sim-days, as live), not held forever | `tests/backtest/test_breaker_sim_time.py`, `backend/tests/test_breaker_sim_time_gate_gap.py::test_tripped_breaker_blocks_in_sim_time` |
| TEST-BT-005 | covered | Backtest speed (item 12): identical HTF/daily frames are analyzed once (exact `DataFrame.equals` + equal arguments, every hit an isolated copy, patched only during a run); memo on vs off gives a byte-identical backtest on the real engine | `tests/backtest/test_memo.py` |

### 4.9 ECC audit 2026-11-14 gaps (Fable B8)

Source: `docs/audit/2026-11-14-ecc/00-FABLE-sentez.md` §6.1 B8 and §6.2 (Ö1, Ö2, Ö3, Ö13, Ö15).
These rows record protections that have no test yet. The code fixes are GATED (failing test →
surgical diff → risk-ops → operator); a row moves to `covered` only with its reproduction test.

| TEST-ID | State | Observable expectation | Evidence |
|---|---|---|---|
| TEST-GAP-VERIFY-ALGO | missing | When the algo-order fetch raises, `_fetch_protection_order_ids` reports `ok=False`, so protection verify never treats "fetch failed" as "algo SL/TP absent" (no duplicate SL, no wrong close). Today the exception is logged at debug and `(ids, True)` is returned (`exchange/__init__.py:1842-1850`) | — (reproduction test first; Ö1) |
| TEST-GAP-REEMIT | missing | A CONFIRMED (or rejected) v2 setup is not re-added and re-emitted for the same `(symbol, direction, trigger_bar_ts)`. Dedup only compares candidates in `PERSISTED_STATES` (`engine/smc_v2/setup_state.py:121-126`, `:35`), which excludes CONFIRMED; the bug is not yet reproduced | — (reproduction test first, then NET A/B; Ö2) |
| TEST-GAP-V1ONLY-KEYS | missing | A contract test pins which live-config keys act only on the v1 path and are inert on v2 symbols (Fable X6 list, e.g. `risk.min_confluence`, `allow_volatile_entries`, `smc_tp_targeting`, `smc_v2.pullback_timeout_bars`), so docs cannot present them as live gates | — (doc table: `CONTEXT.md`) |
| TEST-GAP-BREAKER-3CFG | missing | The breaker calibration check (starting balance / emergency / daily %) covers all three mainnet bot configs; today it is scoped to the production config only | partial: `tests/config/test_phase_configs.py::test_prod_config_breaker_calibration_consistent` (prod only; `config.phase2_long_1k.yaml` and `config.phase2_scalp_1k.yaml` unchecked; Ö13) |
| TEST-GAP-DOCS-DRIFT | missing | Docs ↔ config/code drift fails CI: CLAUDE.md line cap, STATUS "VPS HEAD" equals the last `DEPLOYED <sha>` in the log, cited repo paths exist, no dated "şu an" heading in constitution/map files (Fable §7 proposal `test_docs_roles.py`) | partial: `tests/test_docs_param_parity.py::test_v1_reference_swing_lookback_matches_engine_default` (one value), `tests/ci/test_tests_registry.py::test_every_evidence_ref_resolves` (this file only; Ö15) |
| TEST-GAP-LEDGER-V2 | missing | With `signal_ledger.enabled`, a v2 entry is recorded in the signal ledger. Today the record hook is reached only from the v1 signal branch (`engine/safe_orchestrator.py:1497→1567`), so v2 symbols produce no ledger rows | — (TDD + byte-identical trade output; Ö3) |

## 5. Evidence run (2026-11-07, Windows, commit `4dd56b6`)

- Every Python file cited in §4: 388 passed, exit 0 (before the 2 new `tests/ci/` registry/MCP files, 6 more passing).
- `npm --prefix u2algo-site test`: `ALL PASS`, exit 0.
- Full suite: 3091 passed, 1 known Windows flaky (§1).

## 6. Next test actions (priority order)

1. Frontend/panel ↔ `/api/*` contract: check in the FastAPI OpenAPI schema and validate the
   consumers against it (backlog item 11).
2. Content-job consumers: validate `scripts/lane_c_commentary.py` input against the schema.
3. TEST-AUDIT-H7 / M1: decide whether to wire the flags from config (needs the backtest gate first).
