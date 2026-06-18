# Edge Measurement Core — Session Handoff (2026-06-19)

For the next session to resume cleanly. This persists the activation checklist and the worktree run-recipe that otherwise lived only in an ephemeral temp file.

## What this is
"Professional League" track #1 = **Live Edge Measurement Core** — an internal, additive, default-OFF system that records every first-sight SMC signal, shadow-resolves its hypothetical outcome (faithful to the bot's real execution), and reports **cost-netted, significance-gated** edge metrics. Answers: *does the bot's signal carry a tradeable NET edge?* (live record ≈ −5.3%).

## Status
- **Branch:** `feat/edge-measurement-core` — **PR #227** (open, base master, pushed).
- **Worktree:** `C:/Users/utkuc/Downloads/efloud-bot/.claude/worktrees/edge-measurement-core` (the shared repo working tree is on Gemini's `feat/smc-sl-tp-redesign` — DO NOT disturb).
- **12 commits + this handoff · 33 tests green · final whole-branch review: ready_to_merge=TRUE, 0 pre-merge blockers.**
- 100% additive · `signal_ledger.enabled=false` (triply inert in prod) · read-only · no order surface · zero trade/safety change.

## Worktree run-recipe (CRITICAL — the worktree has NO .venv of its own)
```bash
WT="C:/Users/utkuc/Downloads/efloud-bot/.claude/worktrees/edge-measurement-core"
PY="C:/Users/utkuc/Downloads/efloud-bot/.venv/Scripts/python.exe"
# run tests from the worktree as cwd with the MAIN venv:
cd "$WT" && "$PY" -m pytest backend/tests/test_edge_*.py backend/tests/test_signal_ledger*.py backend/tests/test_resolve*.py backend/tests/test_routines_registered.py backend/tests/test_timeout_panel_seam.py -q
# commit ONLY in the worktree:
git -C "$WT" add <paths> && git -C "$WT" commit -m "..."
```

## Components (all under the branch)
- `engine/signal_ledger.py` — append-only JSONL; `brk_ts` identity + idempotent dedup (kills re-emission N-inflation).
- `engine/edge_costs.py` — `net_r`: fees + funding + slippage netting in R-units.
- `scripts/routines/resolve_signals.py` — shadow resolver: MARKET-at-confirmation fill (v1 next-bar-open; v2 engulfing **approximation**), per-direction SL/TP race (conservative same-bar=SL), partial-ladder blend, cost netting, heartbeat, AlertRouter, real `OHLCVFetcher` adapter (`result.df`, `funding_rate`), `@register` entrypoint.
- `engine/edge_metrics.py` — min-N gate, Wilson CI, PF-null fix, 3-way timeout robustness panel.
- `scripts/routines/edge_report.py` — status-line-first, conditioned, gross-vs-net disclaimer.
- Tests: `test_edge_e2e.py` (full chain) + `test_timeout_panel_seam.py` (timeout regression).
- Spec: `docs/superpowers/specs/2026-06-18-edge-measurement-core-design.md` (v2, 43-agent review). Plan: `docs/superpowers/plans/2026-06-18-edge-measurement-core.md`.

## ⚠️ GATED — Task 8 (live recorder hook) — NOT in this branch
Place `signal_ledger.record_signal(...)` in `engine/safe_orchestrator.py` immediately after the first-sight dedup insert (`self._processed_signals[sig_key]=now_ts`, ~:1209) **BEFORE** the `is_tradeable` split — so it records BOTH tradeable + read-only signals (the v1 keystone bug was putting it on the read-only-only `_on_signal_readonly` path). Best-effort try/except; `set_trade_id` on fill in the else branch.
- **Precondition:** Gemini's `feat/smc-sl-tp-redesign` (edits the same region) must land + rebase + risk-ops review. NOTE (2026-06-19): that branch got **NO-GO/RERUN** on its backtest review → it is NOT landing soon, so Task 8 stays gated. Re-confirm exact lines after any rebase.
- `brk_ts` from `latest.timestamp` (an ISO **string**) → `int(pd.Timestamp(latest.timestamp).value // 1_000_000)`. Ensure `ts_emitted` is epoch-ms.

## Activation checklist (before flag flip / before any edge verdict is trusted)
A. `runner.py` auto-import (`try: from scripts.routines import resolve_signals, edge_report`) + cadence entries (resolver 300s, report slower). Routines self-register via `@register` but runner.py doesn't import them → scheduler can't see them yet. CLI works: `python -m scripts.routines.resolve_signals`.
B. **Task 8** live recorder hook (above). Until then the ledger is empty.
C. Only finalize `unfilled` once `now >= ts_emitted + fill_window_bars*tf_ms` (else survivorship bias when cadence 300s > fill window). Add an `unfilled` heartbeat counter (the current `still_open` mislabels it).
D. `@register` `_routine_run` should derive ok/breach from `main()`'s counters, not hardcode `ok=True`.
E. **Before any v2 verdict:** replace the v2 `replay_fill` **approximation** (body sign + close beyond prior high/low) with a read-only adapter over `engine/smc_v2/confirmation.py:confirm_entry` + a parity test. Prod runs v2 → current v2 hypo_r is a directional estimate, not a faithful replay (HYPOTHETICAL disclaimer must stay).
F. Numeric BH-FDR + bootstrap CI (Wilson CI is done) before publishing any breakdown verdict. `aggregate()` already labels honestly: "BH-FDR NOT YET APPLIED".
G. Import-guard only screens `resolve_signals.py` top-level; `data.fetcher` transitively imports `exchange` (read-only market data). At activation, route through a read-only data facade or extend the guard.
H. Doc: spec §3.2 "strictly after fill bar" — note v1 INCLUDES the fill bar (next-bar-open); §3.5 timeout now carries mfe/mae (fixed).
I. `build_report`: add an explicit "no signals recorded yet" line when the ledger is empty.
J. Resolver fetches from `rec.brk_ts` but the window keys off `ts_emitted` — assert/document `ts_emitted == brk_ts` at the recorder (Task 8) so the seam is provably equivalent.

## Fixes already applied this session (commit 4f7445d)
- Timeout dropped mfe/mae → 3-way panel degenerate → false `edge_sign_stable` GO. Now `race_sl_tp` returns `{outcome:None, mfe_r, mae_r}`; `resolve_signal` copies into the timeout patch. Regression test added.
- `aggregate()` FDR overclaim "BH applied" → "BH-FDR NOT YET APPLIED"; report header made honest.

## Other open threads (operator-gated, not Edge-related)
- **Alpaca MCP:** `alpaca-docs` HTTP MCP added (user-scope, connected, no key). Trading MCP (`uvx alpaca-mcp-server`) awaits the operator's **paper** API key — command ready in memory. Alpaca shows NO Binance/futures data; read Binance via bot CCXT or the TradingView MCP on a Binance symbol.
- PR #227 awaits review/merge.

## Suggested next-session entry points
1. If PR #227 merged → start activation checklist item C/D (cheap correctness) while Task 8 stays gated.
2. If Gemini's SL/TP branch resolves → do Task 8 (rebase first, re-verify the choke-point line).
3. Or move to "Professional League" track #2 (engineering maturity) or #3 (GTM) per the decomposition.
