# Aşama 2 — Self-Maintenance + Observability — Design (Epic 3 + Epic 4)

**Date:** 2026-05-07
**Author:** Leblepito + Claude
**Status:** Revised post-review (subagent code-reviewer pass applied 2026-05-07)
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

**Healthz semantics (sharpened):**

Returns 200 only when ALL conditions hold:
- `last_loop_tick_ms` is within last 90s (bot's main orchestrator loop is alive)
- `last_exchange_ping_ms` within last 60s (bot has confirmed exchange connectivity)
- `fatal_exception_state` is clean — defined explicitly: any uncaught exception bubbling out of `SafeOrchestrator.run_once()` flips a persistent flag in `state/runtime.json`. Flag clears only after 5 min of clean ticks. Flag survives process restart (does NOT reset on Docker restart, otherwise crash-loop bots report green between restarts)
- `breaker_state.halt_active != true` (a halted bot is not "healthy" even if alive)

Returns 503 if any of the above fails. Endpoint reads cached values (no fresh probes; latency must be <50ms even on slow disk).

**Crash-loop protection:** the `fatal_exception_state` flag persists in `state/runtime.json` across restarts. After 3 consecutive unhealthy starts within 30 min, Docker restart is suspended and a CRITICAL alert fires (see §6 event `health.crash_loop`).

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

**Dedup + rate limit (persistent state):**

Dedup window is stored in a SQLite file at `state/alerter_dedup.sqlite` (file-backed, survives Docker restart). Schema: `(alert_key TEXT PRIMARY KEY, last_fired_ts INTEGER, fire_count INTEGER)`. On startup, alerter reads existing dedup state — does NOT reset on container restart.

- Same `alert_key` → max once per 30 min (configurable per event in §6)
- 50 messages/min hard cap (Telegram API limit ~30/sec; we stay conservative)
- If the SQLite file is missing or corrupt on startup, alerter logs a WARNING, recreates empty file, and accepts that the first hour after restart may produce 1-2 duplicate alerts. Documented behaviour, not a bug.

**Alerter heartbeat (dead-man's switch):**

If the alerter sidecar dies silently, no alerts fire — including the alert that the alerter died. Mitigation:
- Alerter writes `alerter_heartbeat_ts` to `state/runtime.json` every 60s
- The daily-report cron (§4.4) checks heartbeat age. If >2h since last heartbeat → daily-report emits a CRITICAL email subject prefix "ALERTER DOWN" and includes the heartbeat-age value
- Optional Phase 2.2: a second tiny watchdog cron polls heartbeat every 30 min and posts to Telegram if dead. Deferred — daily-report check is sufficient for Phase 2.1.

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

**Failure-to-send wrapper:**

`docker compose run --rm daily-report` can fail silently if (a) image pull is mid-progress, (b) Supabase is unavailable, (c) SMTP rejects. Wrap the cron entry:

```
0 8 * * * cd /opt/efloud-bot && (docker compose run --rm daily-report || (echo "daily-report FAILED at $(date)" | tee -a /var/log/efloud-cron-errors.log; curl -s "https://api.telegram.org/bot$TOKEN/sendMessage" -d "chat_id=$CHAT_ID" -d "text=⚠️ daily-report cron FAILED $(date)"))
```

Wrapper sends Telegram WARNING on failure so the owner notices. The Telegram credentials must already be available in env (alerter uses them).

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

**What:** Python's stdlib `RotatingFileHandler` with maxBytes=50MB, backupCount=10. Native rotation does NOT gzip. Two implementation options:

(A) Custom rotator class: subclass `RotatingFileHandler`, override `doRollover` to gzip the rotated file before storing. Same Python process, no system dependency. Recommended.

(B) Use system `logrotate` via Hetzner cron: configure `/etc/logrotate.d/efloud` with `compress` directive. Decouples rotation from Python. More resilient, but Docker mount semantics complicate this (logrotate runs on host, log file is in container volume — accessible but state coordination is fiddly).

**Recommendation:** option (A). Total cap with gzip: ~150-200MB compressed (vs 500MB raw). Gzipped backups named `efloud.log.1.gz` through `.10.gz`.

**Files:**
- `utils/logging.py` (modify) — custom `GzipRotatingFileHandler` class + handler config

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
| balance.unexpected_change | Balance changed >10% with no trade attributable in last 5 min | Telegram | CRITICAL | 1× per occurrence |
| health.crash_loop | 3 consecutive unhealthy starts in 30 min — Docker restart suspended (§4.1) | Telegram | CRITICAL | 1× per occurrence |
| health.unhealthy_15min | Healthz failing >15 min despite watchdog | Telegram | CRITICAL | 1× per occurrence |
| daily.summary | 08:00 daily | Email | INFO | always (not deduplicated) |

**INFO** events go to email only. **WARNING** and **CRITICAL** go to Telegram. **CRITICAL** Telegram message format: 🚨 prefix + bold + link to last 50 log lines.

## 7. Failure modes — what STOPs deploy

If any of these are observed during the 14-day shadow run (§8), DO NOT promote to track record:

- Healthz returns 200 while bot is actually stuck (false negative)
- Watchdog restart leaves orphan position on exchange (state desync)
- Crash-loop suppression (§4.1) fails to engage — Docker keeps restarting a stuck container indefinitely
- Telegram alerter spams (>10 alerts/hour for non-spam events) OR alerter dies silently with no daily-report follow-up (§4.3 heartbeat must catch this)
- Daily email fails to deliver AND failure-to-send wrapper (§4.4) fails to notify
- Trace ID propagation breaks at any layer (broken correlation)
- Log rotation deletes a file that's still being written (data loss)
- **Supabase pooler unavailability >5 min**: bot must continue trading + log locally (in-memory ring buffer + write-through to local file); trace_id persistence falls back to local-only with retry-flush when pooler recovers. If the bot HALTS or LOSES TRADES during pooler outage, that's a failure
- **NTP time skew >5s**: bar-time persistence and "stuck position >6h" timer become unreliable. Hetzner CX22 must run `chronyd` or `systemd-timesyncd`; spec §3 deployment requires verification at install time + a daily NTP-drift metric in `/healthz` extended response
- **Disk-full event** during a critical write (trade persistence, log write): if not handled gracefully (see §16), trade can be lost. Disk-full handling must be exercised during shadow run (synthetic fill of 90% disk)
- **Alerter SQLite corruption** is acceptable on first occurrence (auto-recreate); persistent corruption (recurring within same week) is a failure

## 8. Acceptance criteria

Aşama 2 is **DONE** when ALL of:

1. Bot runs **14 consecutive days** on Hetzner with no manual intervention. (Extended from initial 7d to capture weekly cycles: Sunday Binance maintenance window, weekend low-liquidity behavior, weekly DD breaker trigger conditions, monthly funding-rate anomalies that often cluster on first/last weekday).
2. During those 14 days:
   - At least 1 simulated crash (kill bot process) is auto-recovered within 60s, with Telegram CRITICAL alert sent
   - At least 1 simulated breaker trip produces correct Telegram alert
   - Daily email arrives 14/14 days
   - All structured logs are JSON-parseable; no plain-text logs
   - Trace IDs correlate at least 90% of trades end-to-end across log layers
   - **At least 1 simulated Supabase pooler outage (5 min)**: bot keeps logging locally, no trades lost
   - **At least 1 disk-full simulation** (fill /var to 90%): bot detects, alerts, refuses new trades but does NOT crash; recovers when disk freed
   - **Alerter heartbeat verified 14/14 days** (no "ALERTER DOWN" daily-report subjects)
3. Manual chaos test (run on day 7 or 8): pull network for 30s. Bot recovers, alerts fire, no orphan positions.
4. Code review of all new components passes
5. `docs/runbooks/operational-recovery.md` exists with: how to read logs, how to manually restart, how to disable alerter, how to rotate keys, how to recover from a corrupted alerter SQLite, how to manually flush queued local logs to Supabase after a pooler outage
6. **Owner acknowledgment loop** (§17) verified: a CRITICAL Telegram alert is sent and `/ack` reply is received and registered

After §8 acceptance → Aşama 3 (track record period) begins.

## 9. Telemetry / privacy considerations

- API keys, secrets, balance figures, trade PnL are in logs. **Logs do NOT leave the Hetzner box** — alerter and daily-report are local processes; only the alert TEXT (sanitised) goes out via Telegram/SMTP.
- Telegram messages must redact: API keys (never log them in the first place), Supabase passwords (never log), full account balance (use deltas/percentages instead of dollar amounts).
- Email full balance is acceptable since it's owner-only.
- **Acknowledged tradeoff — Telegram message body content:** events `position.stuck_over_6h` and `exchange.error_burst` must include `symbol` to be useful. Combined with the owner's eventual public Lead-Trader profile (which exposes positions on a delay), this is mild positional leakage. The mitigation is: Telegram chat is owner-only DM (not a group); chat_id is an env secret; the bot is single-user. Net residual risk accepted as low. If a third-party group or shared chat is ever added, this analysis must be re-done.

## 10. Open questions (post-review)

1. **SMTP host choice:** Gmail (simple) vs SendGrid (reliable). Recommend Gmail to start; revisit if delivery fails. Quota: see §18.
2. **Telegram chat:** Resolved — personal DM with bot (single-user, owner-only). Group/multi-user requires re-doing privacy analysis (§9).
3. **/healthz return 200 criteria:** the 90s loop-tick threshold is a guess. Calibrate against actual loop frequency in first 24h of shadow run; tune if false-positive rate is high. (Resolved: spec now defines explicit `fatal_exception_state` flag — see §4.1.)
4. **Watchdog vs Docker compose healthcheck:** Resolved — Docker only; crash-loop suppression added (§4.1).
5. **Log retention:** Compressed 150-200MB covers ~30+ days. Sufficient.
6. **trace_id storage in Supabase:** `trades.trace_id varchar(12)` with INDEX on the column (added in migration 002). Index needed because alerter and post-mortem queries filter by trace_id. Confirmed sufficient bit-space (uuid4 hex truncated to 12 chars = ~62 bits, collision risk negligible at this scale).
7. **NTP daemon choice:** chronyd vs systemd-timesyncd on Hetzner. Either is fine; pick whichever is already installed on the CX22 image. Verify via `chronyc tracking` or `timedatectl status` before shadow run begins.
8. **Backtest engine bar_ts capture (resolved — deferred):** The live engine adds `bar_ts_ms` via Tasks 2 + 7 of `2026-05-07-asama-2-step1-foundational-refactor.md`. The backtest equivalent (modifying `backtest/engine.py` in `feature/backtest-subsystem`) is tracked as a follow-up plan, to be written after Aşama 2 Step 1 merges to master and `feature/backtest-subsystem` rebases. Until that follow-up lands, Phase B reconcile (which needs both sides to use bar-time) remains blocked.

## 11. Implementation order (priority for plan-writing) — REVISED

Original §11 had Step 1 (timestamp fix) and Step 2 (trace IDs) modifying the same files (`engine/order_manager.py`, `state/repository.py`). Merged to avoid two refactors of the same code paths:

```
1. Foundational refactor: schema migrations + structured JSON logs +
   trace_id propagation + bar-time persistence. Single coordinated change
   touching engine/order_manager.py, state/repository.py, utils/logging.py,
   backtest/engine.py + migrations 002 (trace_id), 003 (bar_ts).
                                          ─── foundation for everything
2. /healthz endpoint + crash-loop persistence in state/runtime.json
                                          ─── unblocks 3
3. Docker compose healthcheck + restart-unless-stopped + crash-loop suppression
                                          ─── completes watchdog
4. Telegram alerter + SQLite dedup + heartbeat
                                          ─── reads 1 to fire alerts
5. Daily email report + failure-to-send wrapper + alerter-down detection
                                          ─── reads Supabase + heartbeat from 4
6. Log rotation (custom GzipRotatingFileHandler)
                                          ─── parallel to all of above
─── Phase 2.1 done, run 14-day shadow ───
7. /metrics endpoint                     ─── independent
8. DB backup automation                  ─── independent
9. API key rotation reminder             ─── independent
10. Slack channel                        ─── extends 4
─── Phase 2.2 done ───
```

Steps 1-4 are the critical path. Step 5 depends on Step 4 (heartbeat detection), but otherwise independent. Step 6 parallel. Steps 7-10 are Phase 2.2 — done after track record begins.

Each step gets its own writing-plans pass when its turn arrives.

## 12. What this unblocks

After Aşama 2 acceptance:
- **Aşama 3 (track record):** bot runs unattended 60-90 days with operational confidence
- **Aşama 4 (Lead Trader application):** application requires evidence of stable operation; Aşama 2's logs + daily reports + chaos-test result are the evidence

## 13. Estimated effort — REVISED

Original estimate (5-7 weeks) was optimistic. Honest re-estimate after factoring in: existing safety/breaker code recently shipped (4b2e25c, 8593914) requires careful integration testing; Step 1's combined refactor of 4 files + 2 migrations + tests is substantial; integration surprises with engine state coupling are likely.

- **Phase 2.1 (steps 1-6):** 4-6 weeks for one engineer
  - Step 1 (foundational refactor + migrations): 1-1.5 weeks alone
  - Steps 2-6: 3-4.5 weeks combined
- **Phase 2.2 (steps 7-10):** 2-3 weeks, low priority, can be deferred indefinitely
- **14-day shadow run + acceptance:** 2.5 weeks (calendar, mostly waiting; includes chaos tests + simulated outages)

**Total to track-record start: ~7-9 weeks calendar.**

If a critical issue surfaces during shadow run (§7), expect 1-2 additional weeks for fix + re-shadow.

## 14. Rollback plan

Phase 2.1 deploys add new components (alerter, daily-report) and modify existing ones (engine logging, healthz endpoint, schema). If a deploy goes bad, rollback paths:

**Rollback scope by step:**
- **Step 1 (foundational refactor + migrations):** Migrations 002 (trace_id) and 003 (bar_ts) are additive — can be left in place; no destructive rollback. Code rollback: `git revert` of the foundational commit; engine reverts to plain logger + wall-clock timestamps. Side effect: new alerter (Step 4) breaks because it expects JSON logs; mitigation = revert Steps 1-4 together as a unit if rolling back Step 1.
- **Step 2-3 (healthz + Docker healthcheck):** Disable via Docker compose — comment out `healthcheck:` stanza, redeploy. Bot reverts to "always-restart-on-crash" without health-awareness. No data risk.
- **Step 4 (alerter):** Stop the alerter container (`docker compose stop alerter`). Bot continues operating; only alerts stop. Owner must manually monitor logs. Acceptable interim state.
- **Step 5 (daily-report):** Disable cron entry. No bot impact, only owner loses daily summary. Acceptable interim state.
- **Step 6 (log rotation):** Revert custom rotator → use stdlib RotatingFileHandler without gzip. Slight disk usage increase, no functional impact.

**Feature flags:**
- `EFLOUD_LOGGING_FORMAT` env var: `json` (new) or `plain` (rollback). `utils/logging.py` reads at startup; switching requires restart but no code change.
- `EFLOUD_HEALTHZ_ENABLED` env var: if `false`, healthz returns 200 unconditionally (effectively disables health-aware watchdog without breaking compose).
- `EFLOUD_TRACE_ID_ENABLED` env var: if `false`, generated trace_id is `null` everywhere. Engine still works; correlation features off.

**Master kill switch:** revert to commit `dc04ca8` (current master HEAD) restores pre-Aşama-2 state. The new Hetzner sidecars (alerter, daily-report) just won't start — Docker compose handles missing services gracefully.

## 15. Test strategy for new components

Every component in §4 has dedicated tests. Tests are part of the Step's PR, not deferred.

**Healthz endpoint (4.1):** unit tests for each unhealthy condition (stale loop, exchange ping miss, fatal exception flag set, halt active); integration test simulating crash + flag persistence across restart.

**Structured logger + trace_id (4.2):** unit tests for JSON formatter (no plain text leaks, all fields present); contract test that trace_id propagates through `OrderManager.open_position()` → `Repository.persist_trade()` end-to-end; property-based test that every trade row in DB has a non-null trace_id.

**Alerter (4.3):** synthetic log fixture suite — feed crafted JSON log lines through alerter rules, assert correct alert fires (or doesn't); SQLite dedup test — fire same alert key 5× in 5 min, assert 1 message; restart test — kill+restart alerter, fire same key, assert dedup state preserved; heartbeat test — daily-report flagged with "ALERTER DOWN" when heartbeat stale.

**Daily-report (4.4):** mock Supabase + SMTP; golden-output test against committed sample data; failure-to-send test (kill SMTP container during run, assert Telegram fallback fires).

**Trade-timestamp fix (4.5):** unit test that `bar_ts_ms` matches the bar's actual timestamp in backtest; live-engine test that fill-time is recorded (mocking exchange).

**Log rotation (4.6):** unit test of `GzipRotatingFileHandler.doRollover` produces valid gzip; integration test that rotation under high write load doesn't lose lines.

**End-to-end:** the 14-day shadow run (§8) is the integration test. No staging environment required; shadow runs against a separate Hetzner container with a paper-trading config.

## 16. Disk-full handling

Hetzner CX22 has ~40GB SSD. Risk vectors:
- Log growth (capped to ~200MB by §4.6 — not the problem)
- Docker images / layers (a stale `docker system prune` can recover GBs)
- Supabase journal cache (small)
- Backup files if §5.2 runs (each ~50-100MB)
- `state/` directory (small JSON files)

**Detection:** healthz endpoint extension — return 503 if `/var/lib/docker` or `/opt/efloud-bot` partition >90% full. Triggers Docker unhealthy → restart, but restart doesn't help with disk-full. So:

**Behaviour at disk-full:**
- Bot detects via OSError on persist write
- Bot enters HALT state (stops opening new positions; existing positions managed normally)
- Telegram CRITICAL alert fires: `disk.full` event (new event in §6 matrix; add it)
- Daily-report subject prefix: "DISK FULL — INTERVENTION REQUIRED"
- Owner runbook step: SSH in, run `docker system prune -af --volumes` to recover space; verify `df -h`; run `docker compose restart efloud-bot`

**Acceptance §8.2 includes:** simulated disk-full (fill `/var` to 90% via `dd`), verify bot HALTs gracefully + alert fires + recovery procedure works.

## 17. Owner acknowledgment loop

CRITICAL alerts need to be acknowledged so the system knows the owner saw them. Without ack, repeated identical alerts spam the owner OR genuine ongoing issues get muted.

**Mechanism:**
- Telegram bot accepts `/ack <alert_key>` reply command
- Alerter records ack in SQLite: `(alert_key, acked_at, acked_by_chat_id)`
- A CRITICAL event that fires within 4h of ack of same `alert_key` is suppressed (with a one-line note "(suppressed; ack received Xh ago)")
- After 4h, ack expires; same event fires again

**Default behaviour if no /ack received:**
- Same CRITICAL alert re-fires every 30 min for up to 8 messages, then 1× every 6h until acknowledged or condition clears
- Daily-report includes a "Pending acknowledgments" section listing unacknowledged CRITICALs from past 24h

**Acceptance §8.6** requires: simulate a CRITICAL event during shadow run; verify ack flow works; verify no-ack escalation works.

**Implementation:** alerter sidecar polls Telegram getUpdates for replies. Lightweight; no webhook required. ~50 lines added to alerter.

## 18. Cost / quota considerations

Phase 2.1 components — quota and cost notes:

| Component | Service | Quota | Cost | Risk if exceeded |
|-----------|---------|-------|------|-------------------|
| Telegram alerts | Telegram Bot API | ~30 msg/sec; 1000s/day per chat | Free | Rate-limit error → message dropped. We cap at 50/min (§4.3). |
| Daily email | Gmail SMTP | 500 messages/day soft limit | Free with Gmail account | Daily-report = 1 msg/day; failure-to-send wrapper = 1 msg per failure. ~2-5/day worst case. Far under quota. |
| Alerter overflow → email fallback | Gmail SMTP | 500/day | Free | If alerter ever falls back to email (not in current spec; deferred to Phase 2.2 if added), worst-case storm could exhaust Gmail quota. **Recommendation:** if email fallback added, add hard cap of 50 emails/day. |
| /metrics scraping | Prometheus (Phase 2.2) | N/A | Free, local | None |
| DB backup (Phase 2.2) | Hetzner volume | ~7×100MB = 700MB | Free (already paid for VM) | None |
| Supabase pooler | Supabase | tier-dependent | Existing — already paid | If trace_id writes increase log volume by >2× during normal ops, could hit tier limit. Monitor row count growth in first 48h of shadow. |
| Docker pulls | Docker Hub | 100 pulls/6h anonymous | Free if logged in | Daily-report uses `docker compose run --rm` which may pull image if local cache missing. Pre-pull in deploy script to avoid runtime pull. |

**Net cost of Phase 2.1: $0/month.** (All within free tiers; Hetzner + Supabase already paid.)

If switching to SendGrid for SMTP (recommended only if Gmail proves unreliable): SendGrid free tier is 100 emails/day for the first 30 days, then 100/day permanent — exceeds our needs.
