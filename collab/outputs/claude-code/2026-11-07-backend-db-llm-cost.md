# Backend + DB and LLM cost/latency — 2026-11-07 (backlog T-20261106-04 items 11 + 13)

Source: master `8f3759b` plus read-only checks in the live containers (`efloud-bot`, `efloud-alerter`)
and on `u2algo.com`. Produced 2026-11-07 ~12:10 UTC · task T-20261107-22.
Measurement window: `/app/logs/efloud_bot.log`, 2026-10-19 12:12 → 2026-11-07 12:00 UTC (19 days).
No code changes in this report.

## Item 11 — Backend + DB

| Check | Result |
|---|---|
| Unauthenticated `backend/api.py` routes | Only `POST /login` and `POST /mobile/login` (rate-limited). Everything else sits behind `require_auth` |
| Session | `itsdangerous` signed cookie, `httponly`, `secure` outside dev, `samesite=lax`. A missing or default `SESSION_SECRET` fails closed outside dev |
| CORS | Explicit `ALLOWED_ORIGINS` list with credentials; no wildcard |
| CSRF on bot actions | Cookie is `samesite=lax`, so a cross-site POST carries no session. The panel adds the header + `Sec-Fetch-Site` check (#309) |
| Migrations | 16 files; two share the `009_` prefix (`009_content_drafts`, `009_trade_warehouse_extension`). Harmless: `migrate.py` tracks the full filename stem in `schema_migrations` |
| Prod DB | DB-less by design (ADR-0006); the Postgres mirror is inert |
| Site waitlist (Railway → Supabase) | `GET /api/waitlist/health` → `database: ready, backend: supabase`. The `CLAUDE.md` note "table not ready / PGRST205, leads go to local JSONL" is **stale** (item 14) |

No backend/DB defect found beyond the dashboard sentiment reader in A2 of the LLM audit, which
waits on the operator decision.

## Item 13 — LLM cost and latency (live)

| Call site | Calls in window | Outcome | Cost / latency |
|---|---|---|---|
| Structure validation (`engine/signals.py`, synchronous, per signal) | **23,085** | **100 % fallback**: `reasoning='Fallback due to API failure or timeout.'`, `confidence=1.00` on every line | $0. It fails in ~5 ms (the log shows two lines 5 ms apart), so there is no hot-path delay *today* |
| Macro sentiment (every 4 h) | 27 triggers | Works (OpenRouter; last 2026-11-07 08:59 RISK_OFF, FGI 25) | ~6 calls/day. The result is unused by the engine (audit A2) |
| Agent team (per opened trade, observation) | 105 journal reviews | Works | 1 call set per opened trade |
| Alerter formatter | — | **Always falls back to raw text** | $0 |

### L1 — Structure validation never ran (root cause)
`validate_signal_with_gemini` calls `make_llm_client({})` without the `llm:` config block. Provider
resolution then falls to `LLM_PROVIDER` (unset in the container), then the default `claude`, and
`ANTHROPIC_API_KEY` is unset. The client returns `{}` immediately, and the advisory pass-through
fires. Only `OPENROUTER_API_KEY` is set. The config comment ("NOTE: this block WINS over
LLM_PROVIDER … the no-config call sites") describes exactly this trap.

**Do not "fix" this by setting `LLM_PROVIDER=openrouter`.** That would turn 23k fast failures into
23k real calls (cost), each with up to `_STRUCTURE_VALIDATION_TIMEOUT_SEC = 5` s synchronously
before the order. That adds entry latency on mainnet for an advisory value that never gates
(C8). Options for the operator:
- **(a) Recommended:** remove the synchronous call, or put it behind an explicit default-OFF
  flag (`engine/signals.py` is trading code, so this needs risk-ops review and sign-off).
- **(b)** Move it post-trade and async, like the agent team, if the verdict is worth measuring.

### L2 — Alerter formatter has the same root cause
The `efloud-alerter` container also has no `LLM_PROVIDER` and no Anthropic key, so
`format_alert_with_ai` always returns the raw text. Since #322 CRITICAL alerts skip it anyway;
INFO/WARNING alerts are effectively raw too. Fine as is: no cost, no latency. Do not enable it
without a reason.

### Spend today
Only the sentiment loop (~6/day) and the agent team (per opened trade) reach OpenRouter
(`deepseek/deepseek-v4.1-flash`). The two highest-volume call sites cost nothing because they
never connect.

## Actions

| # | Action | Who |
|---|---|---|
| 1 | L1: decide (a) remove/flag-off or (b) async post-trade for structure validation | operator (+ risk-ops review) |
| 2 | Update the stale Supabase line in `CLAUDE.md` | item 14 (living docs) |
| 3 | A1/A2 sentiment decision (unchanged) | operator |
