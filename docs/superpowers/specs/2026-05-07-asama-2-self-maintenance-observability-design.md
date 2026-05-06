# Aşama 2 — Self-Maintenance + Observability — Design (Epic 3 + Epic 4)

**Date:** 2026-05-07
**Author:** Leblepito + Claude
**Status:** Draft (pending spec review)
**Parent:** `docs/superpowers/specs/2026-05-05-efloud-roadmap.md` (Aşama 2)
**Triggers:** A2 baseline (`dc04ca8`) — strategy is Lead Trader competitive; operational gap remains.
**Implements:** Epic 3 (self-maintenance) + Epic 4 (observability) as a single combined spec because their components are tightly coupled (logs feed alerts; healthchecks feed watchdog; trace IDs feed both).

> **For agentic workers:** Use `superpowers:brainstorming` to validate any open question in §10 before implementation. Use `superpowers:writing-plans` to break this into per-task implementation plans. Implementation must NEVER risk live bot stability — every change is deployed only after a 1-day shadow run on a separate Hetzner container or test config.

---

## 1. Goal

Make efloud-bot capable of running unattended on Hetzner for **60-90 consecutive days** with:
- Bot crashes automatically detected and recovered within 60 seconds
- Owner receives a daily summary of what happened
- Owner is alerted within minutes of any operationally significant event (breaker trip, position stuck, exchange error)
- Every event has a structured log + trace ID so post-mortem analysis is possible
- No data loss if the host or Supabase has a transient issue

**Non-goal:** Build a full DevOps platform. We're operationalising one bot, not running a hedge-fund control plane.

## 2. Scope

**In scope (Phase 2.1, critical for track record):**
- Health-aware watchdog (Docker healthcheck + restart-on-unhealthy)
- Structured logs (JSON, severity, trace_id)
- Trace IDs threaded through signal → order → fill → persist
- Telegram alert bot for operational events (5 specific triggers; see §6)
- Daily email report (PnL, trades, breaker history, anomalies)
- Trade-timestamp bug fix (validation-results §6) — bar-time not wall-clock; needed for both alerting and post-mortem
- Log rotation (size-based, gzipped archives)

**In scope (Phase 2.2, after track record begins):**
- Prometheus `/metrics` exposition endpoint (passive — no scraper required)
- Supabase DB backup automation (nightly pg_dump → encrypted local file with 7-day rotation)
- API key rotation calendar reminder (Hetzner cron)
- Slack integration as alternate channel (defer to Telegram-first)

**Out of scope:**
- Building a full Prometheus/Grafana stack (overkill for one bot)
- Web dashboard observability work (already exists at minimum level; revisit during Aşama 5 investor reports)
- Distributed tracing across multiple services (single bot)
- Multi-region failover (single Hetzner box is fine for solo lead trader)
- Kubernetes (single Docker compose is sufficient)

## 3. Architecture overview

```
┌──────────────────────────────────────────────────────────────────┐
│  Hetzner CX22 (single box)                                       │
│                                                                  │
│  ┌──────────────────┐    ┌─────────────────┐                    │
│  │ efloud-bot       │    │ caddy (existing)│                    │
│  │ (Docker)         │    │                 │                    │
│  │ + healthcheck    │    │ TLS + reverse   │                    │
│  │ + JSON logger    │    │ proxy           │                    │
│  │ + /healthz       │    └─────────────────┘                    │
│  │ + /metrics       │                                            │
│  │ + trace IDs      │                                            │
│  └────────┬─────────┘                                            │
│           │ writes structured logs (JSON)                         │
│           ▼                                                      │
│  ┌─────────────────────────┐                                     │
│  │ Docker volume:          │                                     │
│  │ logs/ (rotated, gzipped)│                                     │
│  └────────┬────────────────┘                                     │
│           │ tail-and-alert process reads                          │
│           ▼                                                      │
│  ┌─────────────────────────┐    ┌────────────────────────┐      │
│  │ alerter                 │───▶│ Telegram bot API       │      │
│  │ (small Python sidecar)  │    │ (events 1-5 in §6)     │      │
│  │ - tails logs            │    └────────────────────────┘      │
│  │ - matches alert rules   │                                     │
│  │ - dedup + rate-limit    │                                     │
│  └─────────────────────────┘                                     │
│                                                                  │
│  ┌─────────────────────────┐    ┌────────────────────────┐      │
│  │ daily-report (cron)     │───▶│ SMTP → owner email     │      │
│  │ - reads from Supabase   │    │                        │      │
│  │ - composes markdown     │    │                        │      │
│  └─────────────────────────┘    └────────────────────────┘      │
│                                                                  │
│  Docker compose with healthcheck:                                │
│    restart: unless-stopped                                       │
│    healthcheck: HTTP GET /healthz every 30s, 3-fail = unhealthy │
│    on unhealthy: docker auto-restart                             │
└──────────────────────────────────────────────────────────────────┘
```

The bot itself gains: `/healthz` endpoint, `/metrics` endpoint, JSON logger, trace IDs.
Two new sidecar processes: `alerter` (event matcher → Telegram), `daily-report` (Supabase → SMTP).
No external observability stack. Logs are the persistent layer; alerter and daily-report are stateless tools.

## 4. Components — Phase 2.1

### 4.1 Health-aware watchdog (Docker compose)

**What:** Bot exposes `/healthz` HTTP endpoint that returns 200 only when bot is operationally healthy. Docker compose healthcheck polls every 30s; 3 consecutive failures = unhealthy → Docker auto-restarts.

**Healthz semantics:**
- 200: bot loop has run within last 90s, exchange last-ping < 60s, no fatal exception in last 5 min
- 503: any of the above failed
- Endpoint must NOT block on slow paths (returns from cached state, not a fresh probe)

**Why not just process-alive:** The bot can be a zombie — process alive but main loop stuck. Process-alive misses this; healthz catches it.

**Files:**
- `backend/api/routes/health.py` (new) — exposes `/healthz`
- `engine/safe_orchestrator.py` (modify) — track last loop tick into shared state
- `docker-compose.prod.yml` (modify) — add healthcheck stanza

### 4.2 Structured JSON logging + trace IDs

**What:** Every log line is JSON with fields: `ts`, `level`, `event`, `trace_id`, `symbol` (if relevant), `pnl_usdt` (if relevant), and event-specific fields.

**Trace ID lifecycle:**
- Generated when SafeOrchestrator detects a signal: `trace_id = uuid4().hex[:12]`
- Propagated through: signal_evaluated → order_placed → order_filled → position_opened → position_closed → trade_persisted
- Logged at each step with same trace_id
- Stored in `trades.trace_id` column (Supabase migration needed)

**Files:**
- `utils/logging.py` (rewrite) — JSON formatter, trace_id contextvar
- `engine/safe_orchestrator.py` (modify) — generate + propagate trace_id at signal-detection
- `engine/order_manager.py` (modify) — accept trace_id; log all order events with it
- `state/repository.py` (modify) — write trace_id to trades table
- `database/postgres/migrations/002_add_trace_id.sql` (new)

### 4.3 Telegram alert bot

**What:** Small Python sidecar process. Tails structured logs. On match of one of 5 alert rules → posts to Telegram chat.

**Alert rules (§6 has full matrix):**
1. `breaker.tripped` (any breaker — daily, weekly, consecutive)
2. `position.stuck_over_6h` (position open > 6h with no progress)
3. `exchange.error_burst` (≥5 exchange 5xx in 60s)
4. `balance.unexpected_change` (balance jumps unexpectedly — guards against fat-finger or fund movement)
5. `health.unhealthy_15min` (healthz returned non-200 for 15+ min — warns even though watchdog auto-restarted)

**Dedup + rate limit:**
- Same alert key → max once per 30 min
- 50 messages/min hard cap (Telegram API limit ~30/sec, we go conservative)

**Files:**
- `ops/alerter/alerter.py` (new) — main loop
- `ops/alerter/rules.py` (new) — alert rule definitions
- `ops/alerter/telegram_client.py` (new) — minimal Telegram bot API client
- `docker-compose.prod.yml` (modify) — add alerter service

**Telegram setup (one-time, owner does):**
- Create bot via @BotFather → get bot token
- Get chat_id by messaging the bot, then GET `getUpdates`
- Token + chat_id stored in `.env.production`

### 4.4 Daily email report

**What:** Cron job at 08:00 server time. Pulls last-24h data from Supabase. Composes markdown email with: equity curve text-summary, trade list, breaker events, anomalies. Sends via SMTP.

**Email content:**
```
Subject: efloud-bot daily report — 2026-05-08 — equity $XXXX.XX (+X.XX%)

## PnL summary
- Equity: $X → $Y (+Z%)
- Trades: N (W wins, L losses, win rate ZZ%)
- Best trade: SYMBOL +$X.XX
- Worst trade: SYMBOL −$X.XX

## Trade list
| Symbol | Side | Entry | Exit | PnL | Reason |
| ... |

## Operational
- Breaker trips: N
- Restarts: N (auto-recovered)
- Anomalies (alerter): N (see Telegram for detail)

## System health
- Uptime: HHh MMm
- Avg loop latency: XX ms
```

**Files:**
- `ops/daily_report/report.py` (new) — main script
- `ops/daily_report/templates/daily_report.md.j2` (new) — Jinja2 template
- Hetzner crontab entry: `0 8 * * * cd /opt/efloud-bot && docker compose run --rm daily-report`

**SMTP options:**
- Gmail with app password (simple)
- SendGrid free tier (more reliable, harder setup)
- Recommendation: start with Gmail app password, switch to SendGrid only if delivery is unreliable

### 4.5 Trade-timestamp bug fix

**What:** Trade `opened_at`, `closed_at` in `portfolio.json` and Supabase `trades` table are wall-clock; should be **bar-time** (the historical bar that triggered the action, in backtest; live exchange fill time, in live).

**Why now:** Required for trace_id correlation across structured logs (alerter checks "position stuck >6h" using bar-time delta), and for Phase B reconcile when we eventually run it.

**Backwards compat:** Add `bar_ts_ms: int` column alongside existing wall-clock fields; do NOT remove wall-clock fields immediately (live data already has them; migration would be destructive).

**Files:**
- `engine/order_manager.py` (modify) — populate bar_ts_ms from current bar
- `state/repository.py` (modify) — persist bar_ts_ms
- `database/postgres/migrations/003_add_bar_ts.sql` (new)
- `backtest/engine.py` (modify) — populate bar_ts_ms in trade dict

### 4.6 Log rotation

**What:** Python `RotatingFileHandler` with maxBytes=50MB, backupCount=10. Older files gzipped via post-rotate hook. Total cap: ~500MB log retention.

**Files:**
- `utils/logging.py` (modify) — RotatingFileHandler config

## 5. Components — Phase 2.2 (after track record begins)

### 5.1 Prometheus `/metrics` endpoint

**What:** FastAPI route exposing standard Prometheus exposition format. Metrics: `efloud_balance_usdt`, `efloud_open_positions`, `efloud_loop_latency_ms`, `efloud_breaker_state`, `efloud_trades_total{symbol,side,exit_reason}`.

**Why later:** Useful for charting but not load-bearing. Daily email + Telegram alerts cover the operational need.

### 5.2 Supabase DB backup automation

**What:** Nightly `pg_dump` via pooler connection → encrypted file → 7-day rotation → optional upload to a hetzner-storage bucket.

**Why later:** Supabase project is paid tier with built-in PITR. Custom backup is belt-and-suspenders, not load-bearing.

### 5.3 API key rotation reminder

**What:** Cron-triggered email at days 60, 75, 89 reminding owner to rotate Binance API key (if a 90-day rotation policy is wanted).

**Why later:** Binance doesn't enforce rotation; this is a hygiene item, not operational.

### 5.4 Slack as alternate alert channel

**What:** Same alerter, additional output channel.

**Why later:** Telegram is the primary; Slack adds redundancy. Add only if Telegram delivery proves unreliable in practice.

## 6. Alert matrix (channel × event × severity × dedup)

| Event ID | Trigger | Channel | Severity | Dedup window |
|----------|---------|---------|----------|--------------|
| breaker.tripped.daily | Daily PnL breaker fires | Telegram | CRITICAL | 1× per day |
| breaker.tripped.weekly | Weekly DD breaker fires | Telegram | CRITICAL | 1× per week |
| breaker.tripped.consecutive | 3-loss consecutive breaker fires | Telegram | WARNING | 30 min |
| position.stuck_over_6h | Open position with no fill movement >6h | Telegram | WARNING | 1× per position lifetime |
| exchange.error_burst | ≥5 5xx from Binance in 60s | Telegram | WARNING | 30 min |
| balance.unexpected_change | Balance jumped >10% with no trade | Telegram | CRITICAL | 1× per occurrence |
| health.unhealthy_15min | Healthz failing >15 min despite watchdog | Telegram | CRITICAL | 1× per occurrence |
| daily.summary | 08:00 daily | Email | INFO | always (not deduplicated) |

**INFO** events go to email only. **WARNING** and **CRITICAL** go to Telegram. **CRITICAL** Telegram message format: 🚨 prefix + bold + link to last 50 log lines.

## 7. Failure modes — what STOPs deploy

If any of these are observed during the 7-day shadow run (§8), DO NOT promote to track record:

- Healthz returns 200 while bot is actually stuck (false negative)
- Watchdog restart leaves orphan position on exchange (state desync)
- Telegram alerter spams (>10 alerts/hour for non-spam events)
- Daily email fails to deliver (no fallback)
- Trace ID propagation breaks at any layer (broken correlation)
- Log rotation deletes a file that's still being written (data loss)

## 8. Acceptance criteria

Aşama 2 is **DONE** when ALL of:

1. Bot runs **7 consecutive days** on Hetzner with no manual intervention
2. During those 7 days:
   - At least 1 simulated crash (kill bot process) is auto-recovered within 60s, with Telegram CRITICAL alert sent and acknowledged
   - At least 1 simulated breaker trip produces correct Telegram alert
   - Daily email arrives 7/7 days
   - All structured logs are JSON-parseable; no plain-text logs
   - Trace IDs correlate at least 90% of trades end-to-end across log layers
3. Manual chaos test: pull network for 30s. Bot recovers, alerts fire, no orphan positions.
4. Code review of all new components passes
5. `docs/runbooks/operational-recovery.md` exists with: how to read logs, how to manually restart, how to disable alerter, how to rotate keys

After §8 acceptance → Aşama 3 (track record period) begins.

## 9. Telemetry / privacy considerations

- API keys, secrets, balance figures, trade PnL are in logs. **Logs do NOT leave the Hetzner box** — alerter and daily-report are local processes; only the alert TEXT (sanitised) goes out via Telegram/SMTP.
- Telegram messages must redact: API keys (impossible — never log), Supabase passwords (impossible — never log), full account balance (use deltas/percentages instead of dollar amounts).
- Email full balance is acceptable since it's owner-only.

## 10. Open questions

1. **SMTP host choice:** Gmail (simple) vs SendGrid (reliable). Recommend Gmail to start; revisit if delivery fails.
2. **Telegram chat:** Personal DM with bot, or owner-only group? Personal DM is simplest; group enables "watch with collaborator" later.
3. **/healthz return 200 criteria:** the 90s loop-tick threshold is a guess. Should be calibrated against actual loop frequency once we instrument it.
4. **Watchdog vs Docker compose healthcheck:** Docker has built-in healthcheck and `restart: unless-stopped`. Is anything else needed (e.g., a separate watchdog container)? Recommend: Docker only initially; add separate watchdog only if Docker behaviour is insufficient.
5. **Log retention:** 500MB cap (10 × 50MB) covers ~14-21 days. Sufficient for now; revisit if track record reveals analysis needs longer windows.
6. **trace_id storage in Supabase:** `trades.trace_id varchar(12)` — confirmed sufficient (uuid4 hex truncated to 12 chars = ~62 bits, collision risk negligible at this scale).

## 11. Implementation order (priority for plan-writing)

The implementation should sequence components by dependency:

```
1. Trade-timestamp bug fix              ─── unblocks 2 + downstream observability
2. Structured logs + trace IDs          ─── foundation for 3, 4, 5
3. /healthz endpoint                    ─── unblocks 4
4. Docker compose healthcheck + restart ─── completes watchdog
5. Telegram alerter                     ─── reads 2 to fire alerts
6. Daily email report                   ─── reads Supabase (independent of 2-5)
7. Log rotation                         ─── parallel to all of above
─── Phase 2.1 done, run 7-day shadow ───
8. /metrics endpoint                     ─── independent
9. DB backup automation                  ─── independent
10. API key rotation reminder            ─── independent
11. Slack channel                        ─── extends 5
─── Phase 2.2 done ───
```

Steps 1-5 are the critical path. Steps 6-7 can be parallel. Steps 8-11 are Phase 2.2 — done after track record begins.

Each step gets its own writing-plans pass when its turn arrives.

## 12. What this unblocks

After Aşama 2 acceptance:
- **Aşama 3 (track record):** bot runs unattended 60-90 days with operational confidence
- **Aşama 4 (Lead Trader application):** application requires evidence of stable operation; Aşama 2's logs + daily reports + chaos-test result are the evidence

## 13. Estimated effort

- Phase 2.1 (steps 1-7): ~3-5 weeks for one engineer
- Phase 2.2 (steps 8-11): ~2-3 weeks, low priority
- 7-day shadow run + acceptance: ~1.5 weeks (calendar, mostly waiting)

**Total to track-record start: ~5-7 weeks calendar.**
