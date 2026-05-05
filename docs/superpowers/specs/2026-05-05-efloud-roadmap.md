# efloud-bot — Master Roadmap to Binance Lead Trader

**Author:** Leblepito + Claude
**Date:** 2026-05-05
**Status:** Active planning artifact (not a build spec — each Epic gets its own spec/plan)
**Related specs/plans:** see §6

> **For agentic workers:** This is a planning/decomposition artifact, not an implementation spec. When you act on a specific Epic, locate its dedicated spec/plan under `docs/superpowers/{specs,plans}/` and follow it. Use `superpowers:brainstorming` before writing any new Epic spec; use `superpowers:writing-plans` before implementing; use `superpowers:executing-plans` or `superpowers:subagent-driven-development` to execute.

---

## 1. Vision (Sonuç)

Become a **Binance Futures Copy Trading Lead Trader.** efloud-bot remains a single-operator engine; copy-trading users follow it via Binance's official program. Regulatory burden stays on Binance. No multi-tenant SaaS, no custodial handling of user funds, no client API key storage.

**Why this path was chosen** (other paths considered, decisions logged in §7):
- Lowest legal/operational overhead vs. building a full SaaS
- Engineering work compounds the existing single-operator engine; no rewrite
- Clear external eligibility criteria (track record, account verification) — measurable progress
- Path Y (open-source) optionally runs in parallel and feeds reputation/community

## 2. Current State (Giriş, 2026-05-05)

**Live infrastructure (Epic 0 — done):**
- Mainnet bot on Hetzner CX22 + Caddy + LE; Supabase persistence; manual start (`EFLOUD_AUTOSTART=0`)
- Single strategy (`phase2_1k`, $2000 wallet, 5x leverage, 10 symbols, isolated/cross margin)
- Breaker, position_guard, audit_log, equity_history all wired
- ~3 days live trading (insufficient as a track record)

**Epic 1 — Backtest subsystem: implemented, not validated**
- Worktree: `C:/Users/utkuc/Downloads/efloud-bot-backtest` on `feature/backtest-subsystem`
- 20+ commits; Phase A (1y validation) + B (live-vs-backtest reconciliation) + C (grid search) all merged
- Performance optimizations done (59x speedup on SMC slice; `step_every_n_bars=4`)
- ⚠️ Plan checkboxes never marked — tracking artifact stale; `reports/backtests/` empty → **no validation run has actually been executed**
- Spec: `docs/superpowers/specs/2026-05-04-backtest-design.md`
- Plan: `docs/superpowers/plans/2026-05-04-backtest-implementation.md`

**Other state:**
- `superagentv3.py` standalone (in repo root, not integrated; superseded by `superagent_mcp_v2`)
- No self-maintenance / watchdog / observability beyond basic logs
- No multi-AI advisory layer wired to bot

## 3. Staged Path (Gelişme)

```
Aşama 1 — Backtest validation run                        [Epic 1b, ~3-5 gün]
            │  Goal: answer "phase2_1k is profitable historically — yes/no"
            ▼
Aşama 2 — Self-maintenance + Observability               [Epic 3 + Epic 4, 4-6 hafta paralel]
            │  Goal: bot runs unattended for 60-90 days without intervention
            ▼
Aşama 3 — Track Record period (live, hands-off)          [30-90 gün]
            │  + Paralel: SuperAgent advisory layer       [Epic 2, 5-7 gün dev + bekleyiş]
            │  + Paralel: optional Pathway Y (open-source [Epic Y, ayrı brainstorming]
            │    publication) — community kazanımı
            ▼
Aşama 4 — Lead Trader application prep + submit          [2-4 hafta]
            │  Marketing materials, public profile, Binance KYC + Lead Trader application
            ▼
Sonuç — Approved as Binance Futures Lead Trader
```

**Critical-path rationale:**
- **Aşama 1 first**: a track record on a strategy that doesn't backtest profitably is meaningless. If Phase A says no, iterate strategy (Epic 6 enters).
- **Aşama 2 before Aşama 3**: Lead Trader applications require stability proof. Bot crashing mid-track-record disqualifies. Self-maintenance + observability are *load-bearing*.
- **Epic 2 (SuperAgent) demoted to parallel**: advisory, not on critical path. Implement during Aşama 3 when bot is hands-off and engineer time is free.

## 4. Epic Catalog

| Epic | Status | Owns | Spec/Plan |
|------|--------|------|-----------|
| **0 — Mainnet live infrastructure** | ✅ Done | Hetzner deploy, Supabase persistence, basic dashboard, breaker, position_guard | n/a (delivered) |
| **1a — Backtest subsystem implementation** | ✅ ~Done | `data/`, `backtest/` modules; CLI subcommands (single/portfolio/grid); Phase A/B/C drivers | `2026-05-04-backtest-design.md` + `2026-05-04-backtest-implementation.md` |
| **1b — Backtest validation execution** | ⏳ Next | Run Phase A on 1y; produce `reports/backtests/{run_id}/`; review results; decide go/no-go | TBD — small spec needed (§5) |
| **2 — SuperAgent advisory** (Yaklaşım A) | 📋 Planned | MCP merge of `superagentv3.py` benzersiz parçaları; `efloud_tools.py`; B/C/E features | TBD — own brainstorming after 1b |
| **3 — Self-maintenance / autonomous ops** | 📋 Planned | Watchdog, health checks, auto-restart, periodic reconciliation, log rotation, DB backup, daily report | TBD — own brainstorming |
| **4 — Observability** | 📋 Planned | Structured logs, metrics, trace IDs, alerting, ops bot | TBD — own brainstorming, paralel with Epic 3 |
| **5 — Investor-grade reporting** | 🔒 Deferred | Performance dashboard, monthly reports, audit trail polish, performance attribution | After Aşama 3 produces enough data |
| **6 — Strategy framework + optimization** | 🔒 Deferred | Pluggable strategies, walk-forward optimization, paper A/B | Triggered if 1b says "iterate" |
| **7 — Compliance/governance** | 🚫 N/A for X path | Lead Trader path keeps regulatory burden on Binance; revisited only if Pathway changes | Out of scope |
| **Y — Open-source publication** | 📋 Optional | License, docs polish, install ergonomics, README, release engineering | Optional parallel; own brainstorming when initiated |

## 5. Next Concrete Step — Epic 1b (Backtest Validation)

**Why now:** Implementation exists; validation has not run. Without Phase A output we can't decide whether to start the track-record clock.

**What 1b looks like (rough scope, full brainstorming TBD):**
1. Verify the prefetch script populated `cache/` for the chosen 1y window (or run it).
2. Run Phase A driver on `phase2_1k` config across all 10 symbols.
3. Inspect produced `reports/backtests/{run_id}/{summary.md, trades.csv, equity.json}`.
4. Sanity-check key metrics: total return, Sharpe, max DD, win rate, profit factor.
5. Compare backtest fills against the ~3 days of live trade history (Phase B reconcile) to validate parity.
6. Decide: GO (start Aşama 2) or ITERATE (Epic 6 — strategy adjustments + re-validate).

**Estimated effort:** 3-5 calendar days, mostly compute time + result review (not new code).

**Acceptance:**
- `reports/backtests/{run_id}/summary.md` produced for the validation run with no engine errors
- Phase B fill-parity check shows acceptable agreement (criteria defined when 1b's own spec is written)
- A go/no-go decision recorded in `docs/superpowers/specs/2026-05-XX-backtest-validation-results.md`

## 6. Documentation References

**Existing specs:**
- `docs/superpowers/specs/2026-05-04-backtest-design.md` — Epic 1a backtest design
- `docs/superpowers/specs/2026-05-01-efloud-web-platform-design.md` — earlier dashboard work
- `docs/superpowers/specs/2026-05-05-server-git-bootstrap-design.md` — server bootstrap (today)

**Existing plans:**
- `docs/superpowers/plans/2026-05-04-backtest-implementation.md` — Epic 1a plan (checkboxes stale; treat git log as authoritative)

**Memory pointers:**
- `~/.claude/projects/C--Users-utkuc-Downloads-efloud-bot/memory/efloud_state.md` — current production state snapshot

## 7. Decision Log (this brainstorming session)

| # | Decision | Rationale |
|---|----------|-----------|
| D1 | Vision = Pathway X (Binance Lead Trader) | Lowest legal/op overhead; engineering compounds existing engine; measurable eligibility |
| D2 | Reject Pathway V (multi-tenant SaaS) for now | Regulatory + 6-12 mo build + tek-kişi yük |
| D3 | Pathway Y (open-source) optional parallel | Reputation; possible future trampoline |
| D4 | Epic 2 (SuperAgent) demoted from "first" to "parallel during Aşama 3" | Advisory, not critical path; track-record stability matters more |
| D5 | Epic 3+4 promoted ahead of Epic 2 | Self-maintenance is load-bearing for Aşama 3 track record |
| D6 | `superagentv3.py` will be merged into `superagent_mcp_v2`, not kept standalone | Leverage existing MCP; one source of truth across projects |
| D7 | "Investor-ready" interpreted as Pathway X eligibility, not custodial multi-tenant | Avoids regulatory complexity entirely |

## 8. Open Questions (parked)

- **Q1.** Does Binance Lead Trader still admit new applicants in TR jurisdiction, and what are the exact 2026 eligibility numbers (min track record days, min PnL, max DD ceiling)? → Verify before Aşama 4 prep.
- **Q2.** Should Epic 6 (strategy framework rework) be triggered if 1b shows marginal results, or kept deferred? → Decide after 1b output.
- **Q3.** Should Pathway Y open-source release happen before, during, or after Aşama 3? → Optional; can be deferred.

## 9. Cancellation / Pivot Triggers

This roadmap is invalidated and should be re-brainstormed if:
- Backtest validation (1b) shows the strategy is not profitable and Epic 6 doesn't yield a profitable variant.
- Binance Lead Trader program eligibility rules change beyond reach.
- A regulatory event in TR materially changes the path-X assumption (e.g., SPK reclassifies copy-trading lead status).
- Owner decides to pivot to Pathway V (SaaS) — re-brainstorming required first; legal review precedes engineering.
