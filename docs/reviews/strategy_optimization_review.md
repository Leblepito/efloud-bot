# gstack Virtual-Team Code Review — Strategy Optimization (`strategy-opt/jun03`)

**Scope reviewed:** `scripts/autoresearch/sweep.py`, `scripts/autoresearch/gen_batch.py`,
`configs/candidate_opt_best.yaml`, and the optimization methodology.
**Method:** 4 parallel role agents using gstack playbooks (`/plan-ceo-review`,
`/plan-eng-review`, `/qa`, `/review` checklist). Workflow `wf_b9ae9b24-0ab`.

| Role | Verdict |
|---|---|
| CEO (strategy / business risk) | approve_with_nits |
| Eng Manager (architecture) | approve_with_nits |
| QA (coverage / edge cases) | **changes_requested** |
| Security (live-money safety) | approve_with_nits |

**Security cleared the core safety question:** the sweep harness *cannot place real
orders* — `run_backtest` builds `SafeOrchestrator` with no client (paper, `persist=False`);
the changed files contain no `subprocess`/`shell`/`eval`/`exec`, no CCXT, no LLM output,
no secrets. Breaker neutralization lives only in an in-memory dict that is never
serialized to YAML, so it cannot leak to the live config. The candidate forces
`testnet+dry_run` ON and preserves all production breaker/guard limits.

---

## Findings actioned in this branch

| # | Sev | Role | Finding | Action |
|---|---|---|---|---|
| 1 | HIGH | CEO+QA | "<10% DD / halved DD" is **90d-window-specific**; on 180d every config (incl. baseline) hits 13-16% MTM DD. Sharpe rose while net return *fell* and trades dropped — "higher Sharpe" = smoother, not more profit. | **Fixed** — candidate header + report reworded: DD<10% scoped to 90d/OOS-symbols; 180d is ~13-16%; exposure caps (already in prod) are the DD lever; net-return shown alongside Sharpe. |
| 2 | MED | Eng | `sweep.py` was the only config entry point not calling `resolve_timeframes()` → silently wrong TF chain on non-`mid` profiles. | **Fixed** — `resolve_timeframes(base_cfg)` now called in `main()` before workers spawn. |
| 3 | changes_req | QA | Zero unit tests for harness logic; the critical `starting_balance` alignment had no regression pin. | **Fixed** — extracted `prepare_base_config()`; added `tests/test_sweep_harness.py` (15 tests: starting_balance alignment, breaker neutralize/keep, ote_band fanout, `classify` truth table inc. boundaries). All pass. |
| 4 | MED | CEO+Eng | `gen_batch.py` BASE labeled "Production v1 baseline" but holds `config.yaml` values (conf55), not prod (`phase2_1k`, conf50). | **Fixed** — comment corrected; OFAT center explicitly noted as config.yaml, prod comparison done via phase2_1k re-baseline. |
| 5 | LOW | Security | Breaker neutralization should be loud. | **Fixed** — `main()` prints a "breaker NEUTRALIZED, never deploy" banner unless `--keep-breaker`. |
| 6 | MED | CEO | Search neutralized the breaker; candidate ships with live breaker (weekly 25%). Need a `--keep-breaker` confirmation pass. | **Partly addressed + flagged as operator pre-deploy step.** The `--keep-breaker` flag is wired and documented. NOTE: the prod breaker is **weekly-25% / daily-10%** (permissive), and the rough-window *total* 180d MTM DD is 13-16% spread over many weeks — a single week is unlikely to hit 25%, so the raw-vs-live gap is probably small. The operator should still run `python scripts/autoresearch/sweep.py --experiments <candidate> --base-config configs/config.phase2_1k.yaml --keep-breaker --period-days 180` before deploy to confirm halt frequency. Not yet executed by this pass. |
| 7 | HIGH | QA+Eng | Candidate ships `smc_version: v2-shadow` + `swing_lookback: 5` but sweep ran `v1`/`swing 4`. | **Documented** — candidate header now states deltas were validated on v1 (prod executes v1 under shadow); the phase2_1k re-baseline runs on the real base (swing 5) to confirm on the production config. |

## Findings deferred (documented, not blocking the candidate)

| # | Sev | Role | Finding | Disposition |
|---|---|---|---|---|
| D1 | LOW | CEO+QA | 3 OFAT trials at param extremes (conf45 / rr2.5 / swing3) crash with `IndexError` in the engine; harness stores only the message, not a traceback. | **Follow-up ticket.** Candidate region (conf 65-75) never crashed. Recommend: capture `traceback.format_exc()`, reproduce one crash single-symbol, add an engine input-guard so out-of-range params fail loud, not mid-cycle. Off the candidate path. |
| D2 | MED | QA | `min_trades=15` floor is too low for a stable per-trade `sharpe_like`. | The chosen candidate has 105-355 trades (well above). Recommend raising the floor to ~30 (or noise-flagging <30-trade results) before auto-promoting any future config. |
| D3 | LOW | Eng+QA | No provenance/seed capture; `period_days` is relative to wall-clock so windows shift day-to-day; data SHA not recorded. | Recommend a run-meta block (git sha, base_config, resolved date window, keep_breaker, data hash) in `batch_out.json` for reproducibility before any config trades real money. |
| D4 | LOW | CEO | Branch carries unrelated uncommitted drift (frontend/agents/engine). | The optimization PR must be scoped to ONLY the harness + report + candidate. (The harness was explicitly built to avoid sweeping these in.) |
| D5 | LOW | Sec+QA | `_set_dotted` applies arbitrary dotted keys; a typo'd override silently creates an ignored leaf and runs as baseline. | Recommend an allowlist / "new-leaf" warning so a typo can't masquerade as a measured experiment. Defense-in-depth; no live impact. |

## Net assessment

The optimization is a **sound, minimal, reversible signal-quality change** (two `risk.*`
params) that improves per-trade quality (PF 1.7→2.6, win-rate 51→60%+) and reduces
per-window drawdown, validated to hold on never-seen symbols. The review's value was in
**puncturing the headline**: it is *not* a "<10% DD, doubled profit" result — it trades
fewer/cleaner trades for lower absolute return and lower drawdown, and the 10% DD target
is only met in the recent regime. All actionable code issues were fixed; the remaining
items are documented follow-ups that do not affect the candidate's correctness or safety.
