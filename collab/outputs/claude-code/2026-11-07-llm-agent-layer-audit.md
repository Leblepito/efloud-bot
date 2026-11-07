# LLM agent layer audit — 2026-11-07 (backlog T-20261106-04 item 6)

Source: master `2122a42` · produced 2026-11-07 ~16:45 UTC · task T-20261107-16

Scope: every place an LLM output can reach a trading decision, an operator alert, or the
dashboard, checked against the `llm-trading-agent-security` checklist. Read-only audit at master
`2122a42`. No code was changed by this report. The fixes are separate PRs or operator decisions,
listed at the end.

## Map: where LLM output goes

| Call site | Input to the prompt | Output used for | Can it change a trade? |
|---|---|---|---|
| Macro sentiment (`engine/ai/sentiment.py`, every 4 h from `backend/bot_runner.py`) | Fear & Greed number (`float()`-cast) | `macro_sentiment` → ±5 confluence in `engine/signals.py` | **Yes, by design (A1). Dormant in prod (A2)** |
| Structure validation (`validate_signal_with_gemini`, `engine/signals.py`) | Symbol, direction, entry/SL/TP, OHLC summaries | `sig.meta["gemini_structure_validation"]` only | No: it annotates and never drops (C8). 5 s timeout, then pass-through |
| Agent team (`engine/agents/team.py`) | Trade context (numbers) | Journal `agent_review`; veto only when `gating: true` | No (`gating: false` in prod) |
| Kronos advisory | Price series | Advisory endpoint/telemetry | No (not referenced by signals, orchestrator entry, or exchange) |
| Alerter formatter (`ops/alerter/formatter.py`) | **Raw alert text, including log-message content** | Replaces the Telegram message body | No trade effect, but it **rewrites CRITICAL safety alerts** (A3) |

## Findings

### A1 — HIGH — The LLM sentiment moves the entry gate (design ↔ documentation mismatch)
`engine/signals.py` (after `structural_score`): `RISK_ON`/`RISK_OFF` adds or subtracts 5 points
**before** the `min_confluence` comparison. With `min_confluence: 50`, the sentiment can lift a 47
to a 52 (it enables an entry) or drop a 52 to a 47 (it blocks one). The config comment ("Advisory
only & fail-safe … never blocks a trade") and ADR-0002 both say otherwise. This is the same family
as audit H1 (post-cap bonuses), whose fix was telemetry-only and did not remove the bonus.
- Failure is safe: on an outage, a schema error, or a stale registry → NEUTRAL → 0 points.
- The effect is bounded: an unknown enum value does nothing, and the magnitude is fixed at 5.

### A2 — HIGH — Sentiment writer and reader use different state directories
- Writer: `fetch_and_save_sentiment` → `<repo>/state/ai_sentiment_registry.json` (`/app/state`,
  volume `efloud_state`).
- Engine reader: `SafeOrchestrator.load_ai_sentiment` → `self.store.dir` = `operation.state_dir`
  = `./state_1k` in prod (`/app/state_1k`, volume `efloud_state_1k`).
- Dashboard reader: `backend/api.py` `/api/ai/sentiment` → `./state/…` (the writer's file).

Effect: the V1 engine most likely always loads the NEUTRAL fallback, so **A1 is dormant in prod**.
Meanwhile the dashboard shows the LLM's RISK_ON/RISK_OFF as if it were in use. (Code and config
evidence. VPS confirmation is `ls /app/state_1k/ai_sentiment_registry.json` inside the container;
it waits for the Claude SSH setup.)

**Do not fix the path on its own.** That would silently switch on an LLM effect on mainnet
entries (ADR-0003). This needs an operator decision; options below.

### A3 — MEDIUM — CRITICAL safety alerts are rewritten by the LLM
`Rule.ai_format` defaults to `True`. The breaker daily/weekly, crash-loop, breaker-HALTED,
unhealthy-15-min and overseer-heartbeat rules (all CRITICAL) therefore go through
`format_alert_with_ai`. The LLM writes `summary`, `details` and `action_required`, and the raw
text does not survive. The prompt also embeds the raw log message, which carries exchange error
strings and symbols. A hallucinated or injected "no action required" on a HALT is the failure mode.
Each alert also adds up to an 8 s synchronous LLM call. The newer TP/SL/orphan rules already set
`ai_format=False`.

### A4 — MEDIUM (plausible) — Telegram HTML is not escaped on those paths
`send_message` uses `parse_mode=HTML`. `render_alert_html` interpolates the LLM fields unescaped,
and the breaker rules interpolate the raw `msg` unescaped. The emergency-HALT reason contains
`balance $X < $Y`. A stray `<` or `&` can make Telegram reject the message (HTTP 400). When that
happens, `send_message` returns `False`, the alert is not marked fired, and it only retries on the
next matching log line. The breaker-HALTED healthz rule repeats every 6 h, but the daily and weekly
log-based rules fire once.

### A5 — LOW (dormant) — The agent-team gating path still has the $10k balance fallback
`engine/safe_orchestrator.py` (agent-team pre-review): `actual_balance = balance if balance is not
None else 10000.0` feeds `size_notional_pct` to the RiskReviewer. This affects the LLM's input
only, not sizing, and only when `gating: true`. If gating is ever enabled, the reviewer would see
a wrong notional %. Exceptions in this path fail closed (veto), which is correct.

### Passed checks
- No LLM has order, sizing, SL/TP or exchange authority. No tool/function calling reaches
  `exchange/`.
- The trading prompts contain only numbers and OHLC data, with no social/news/user text. The
  unused `evaluate_single_news` is not on any trading path.
- Outages, timeouts and schema errors fall back deterministically: sentiment → NEUTRAL,
  validation → pass-through, team → no veto when gating is off.
- The sentiment registry has a freshness guard (stale → NEUTRAL).
- Keys come only from env (`OPENROUTER_API_KEY`, …) and are never in config or logs (security
  audit 2026-11-06).
- Spend and loss limits are independent of model output (breaker, position guard). They are not
  LLM-controlled.

## Recommended actions

| # | Action | Who | Status |
|---|---|---|---|
| 1 | A3 + A4: CRITICAL alerts bypass the LLM formatter; escape HTML; retry as plain text when Telegram rejects HTML | claude-code (alerter only, no trading code) | separate PR (T-20261107-17) |
| 2 | A1 + A2: choose one: **(a) recommended** — make sentiment telemetry-only (keep it in `meta`, drop the ±5), then align the paths so the dashboard and the journal show the real value; **(b)** align the paths and keep the ±5, which needs a NET-cost backtest with and without sentiment plus sign-off (ADR-0003) | operator | decision pending |
| 3 | A5: when gating is ever proposed, pass the real balance (skip the review when it is None) | whoever proposes gating | note in ADR-0002 |
