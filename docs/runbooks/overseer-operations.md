# Overseer Agent — Operations Runbook

This runbook covers deployment, rollout, troubleshooting, and rollback for the
**Overseer sidecar** (Track 3). The overseer is a long-running asyncio loop
that observes the bot, fires deterministic alerts, and (Week 3+) produces
LLM-backed natural-language summaries and daily reports.

## Overview

The overseer runs as a separate container alongside `efloud-bot`, `efloud-caddy`,
`efloud-alerter`, and `efloud-autoheal`. Its inputs are read-only:

- **Log tail**: `/app/logs/efloud_bot.log` (`EFLOUD_LOG_FILE`)
- **Health probe**: `http://efloud-bot:8080/healthz` (`EFLOUD_HEALTHZ_URL`)
- **Trade journal**: `/app/state_aggressive/trade_journal.jsonl`
  (`EFLOUD_OVERSEER_JOURNAL_PATH`)

Its outputs are:

- **Telegram alerts** (deterministic rules, deduped via SQLite)
- **Heartbeat file** at `/app/state/overseer_heartbeat.json` — watched by
  the alerter's `OverseerHeartbeatStaleRule` (10-min staleness threshold)
- **State DB** at `/app/state/overseer_state.sqlite` — heartbeat + LLM-usage counters
- **Phase 0 evidence** at `/app/reports/phase0/<YYYY-MM-DD>/` (cron-triggered)

The Overseer is **read-only towards the bot**. It cannot place orders, edit
risk config, or restart the bot — those remain Hermes/operator actions.

## Rollout — 4 weeks

| Week | Mode                    | `EFLOUD_OVERSEER_DRY_RUN` | LLM     | Notes |
|------|-------------------------|---------------------------|---------|-------|
| 1    | Observe-only            | `1` (log-only)            | offline | Rules fire to logs, no Telegram |
| 2    | Live deterministic      | `0`                       | offline | Telegram alerts on; LLM disabled |
| 3    | LLM hourly              | `0`                       | hourly  | Saatlik özet + Telegram |
| 4    | Full (LLM + daily)      | `0`                       | full    | Hourly + daily report |

The rollout is **manually advanced** — Hermes flips env vars between weeks
after reviewing logs and confirming no false positives.

## Hetzner deploy steps

```bash
ssh efloud@<VPS_IP>
cd /opt/efloud-bot

# 1) Pull latest image (built by CI or local docker build)
docker compose -f docker-compose.prod.yml pull efloud-bot overseer

# 2) Smoke-test the CLI inside the image (does not start the loop)
docker compose -f docker-compose.prod.yml run --rm overseer python -m ops.overseer self-check

# 3) Bring up the sidecar
docker compose -f docker-compose.prod.yml up -d overseer

# 4) Tail logs to confirm clean start
docker logs -f efloud-overseer
```

Expected first 30s of logs:

```
overseer watch loop starting
```

If you see `overseer watch: missing required env: ...` the `.env.production`
file is missing one of `EFLOUD_LOG_FILE`, `EFLOUD_HEALTHZ_URL`, or
`EFLOUD_OVERSEER_JOURNAL_PATH` — fix the env and re-run `up -d`.

## Environment variables

| Variable                          | Required? | Default                                  | Notes |
|-----------------------------------|-----------|------------------------------------------|-------|
| `EFLOUD_LOG_FILE`                 | yes       | —                                        | Bot's JSON log path |
| `EFLOUD_HEALTHZ_URL`              | yes       | —                                        | Bot's `/healthz` endpoint |
| `EFLOUD_OVERSEER_JOURNAL_PATH`    | yes       | —                                        | Trade journal JSONL |
| `EFLOUD_OVERSEER_STATE_DB`        | no        | `/app/state/overseer_state.sqlite`       | Heartbeat + LLM counters |
| `EFLOUD_OVERSEER_DEDUP_DB`        | no        | `/app/state/overseer_dedup.sqlite`       | SQLite-backed alert dedup |
| `EFLOUD_OVERSEER_HEARTBEAT_FILE`  | no        | unset → file not written                 | Set for alerter watchdog rule |
| `EFLOUD_OVERSEER_LLM_DAILY_CAP`   | no        | `500`                                    | Hard cap on Anthropic calls / UTC day |
| `EFLOUD_OVERSEER_DRY_RUN`         | no        | unset (= off)                            | `1` → log alerts, skip Telegram |
| `EFLOUD_OVERSEER_LLM_OFFLINE`     | no        | unset (= off)                            | `1` → skip API, return placeholder |
| `ANTHROPIC_API_KEY`               | week 3+   | —                                        | Required when LLM is online |
| `ANTHROPIC_MODEL`                 | no        | `claude-haiku-4-5-20251001`              | Override only if pinned model retires |
| `EFLOUD_TELEGRAM_TOKEN`           | yes       | (inherited from bot env)                 | Re-used from alerter pipeline |
| `EFLOUD_TELEGRAM_CHAT_ID`         | yes       | (inherited from bot env)                 | Re-used from alerter pipeline |

## Cron schedules

The `overseer-phase0` and `overseer-daily-report` services live behind the
`overseer-scheduled` profile, so `docker compose up -d` will NOT start them.
Cron triggers each via `docker compose run`:

```cron
# Phase 0 SL-evidence extraction — 03:00 UTC daily
0 3 * * * cd /opt/efloud-bot && /usr/bin/docker compose -f docker-compose.prod.yml --profile overseer-scheduled run --rm overseer-phase0 >> /var/log/efloud/overseer-phase0.log 2>&1

# Daily report — 08:05 UTC (5 min after the existing alerter daily-report,
# so the two summaries don't collide on the SMTP relay)
5 8 * * * cd /opt/efloud-bot && /usr/bin/docker compose -f docker-compose.prod.yml --profile overseer-scheduled run --rm overseer-daily-report >> /var/log/efloud/overseer-daily-report.log 2>&1
```

Install once: `crontab -e` as the `efloud` user and paste the two lines.
Hetzner timezone should already be UTC (`timedatectl`) — verify before relying
on the cron times.

## CLI reference

```bash
# Smoke / readiness probe — imports + state DB bootstrap. Exit 0 on success.
python -m ops.overseer self-check

# Long-running watch loop (default sidecar command).
python -m ops.overseer watch

# One-shot Phase 0 evidence extraction. Honors EFLOUD_OVERSEER_DRY_RUN.
# Prints JSON status dict to stdout.
python -m ops.overseer extract-phase0

# Hourly summary (Week 3+ placeholder; today prints stub).
python -m ops.overseer summarize

# Daily report (Week 3+ placeholder; today prints stub).
python -m ops.overseer report
```

## Troubleshooting

### Symptom: `overseer.heartbeat_stale` CRITICAL alert from alerter

- **First check**: `docker ps | grep efloud-overseer` — is the container up?
- **Second**: `docker logs --tail 200 efloud-overseer` for crash traces.
- **Third**: `ls -la /var/lib/docker/volumes/<state-volume>/_data/overseer_heartbeat.json`
  to see if the file is present and recent (mtime in last 10 min).
- **Fix if container is unhealthy**: `docker compose -f docker-compose.prod.yml restart overseer`.
- **Fix if file is stale but container is up**: SQLite write blocked? Check
  disk space: `df -h /var/lib/docker`.

### Symptom: Telegram alert volume too high

- Confirm `EFLOUD_OVERSEER_DRY_RUN=1` is **off** only after Week 2.
- Check dedup SQLite size: `du -h /var/lib/docker/volumes/<state>/_data/overseer_dedup.sqlite`.
- If a single rule is spamming, the rule's dedup window in `ops/overseer/rules.py`
  may need lengthening — open a PR rather than hot-patching prod.

### Symptom: `<LLM cap exceeded>` placeholder in summary output

- `EFLOUD_OVERSEER_LLM_DAILY_CAP` was hit (default 500 calls/UTC day).
- Inspect the counter: `sqlite3 /app/state/overseer_state.sqlite 'SELECT * FROM llm_usage;'`
- If legitimate burst, raise the cap via env + recreate (`docker compose up -d overseer`).
- If unexpected, examine logs for runaway loops calling `Summarizer.hourly_summary`.

### Symptom: `<LLM error>` placeholder in summary output

- The Anthropic API call failed (4xx/5xx, network, parse error).
- `docker logs efloud-overseer | grep summarizer` will show the warning line.
- Common causes: stale `ANTHROPIC_API_KEY`, model retired (update
  `ANTHROPIC_MODEL`), or Anthropic outage (check status page).

### Symptom: log tail not advancing

- Confirm `EFLOUD_LOG_FILE` matches the bot's actual log path.
- Permission: the volume must mount as `:ro` for the overseer container
  (`docker inspect efloud-overseer | grep -A 5 Mounts`).
- If the bot rotated its log, `JsonLogTail` is expected to detect the
  shrink and reset its offset — verify by `docker logs efloud-overseer
  | grep -i 'log.*rotat'`.

### Symptom: sink (Telegram) error

- Confirm `EFLOUD_TELEGRAM_TOKEN` / `EFLOUD_TELEGRAM_CHAT_ID` are set in
  `.env.production`.
- The sink shares transport with `ops.alerter.telegram_client`; any failure
  there also breaks the regular alerter. Cross-check
  `docker logs efloud-alerter` first.

## Rollback

Fast rollback (stop overseer, leave the rest of the stack running):

```bash
docker compose -f docker-compose.prod.yml stop overseer
docker compose -f docker-compose.prod.yml rm -f overseer
```

If a bad image is in production, revert to the previous tag:

```bash
# Tag-based rollback (preferred — preserves the previous image locally)
docker tag efloud-bot:previous efloud-bot:latest
docker compose -f docker-compose.prod.yml up -d overseer
```

The overseer is **stateless modulo its SQLite files** (heartbeat + LLM usage
+ dedup). These survive restarts and can be wiped if needed:

```bash
docker compose -f docker-compose.prod.yml stop overseer
rm /var/lib/docker/volumes/<state>/_data/overseer_state.sqlite
rm /var/lib/docker/volumes/<state>/_data/overseer_dedup.sqlite
docker compose -f docker-compose.prod.yml up -d overseer
```

Wiping the dedup DB will cause one burst of alerts as everything currently
"deduped" fires fresh — only do this if dedup logic is buggy.

## Cost monitoring

Daily LLM-call ceiling: `EFLOUD_OVERSEER_LLM_DAILY_CAP` (default 500). When
exceeded, the Summarizer returns `<LLM cap exceeded>` and does not call the
API, so the cap is a hard ceiling — no overage possible.

Inspect today's spend:

```bash
docker exec efloud-overseer sqlite3 /app/state/overseer_state.sqlite \
  'SELECT date, calls, token_in, token_out FROM llm_usage ORDER BY date DESC LIMIT 7;'
```

Expected rough cost (claude-haiku-4-5-20251001, as of 2026-05):

- ~500 calls × ~2k tokens-in / ~600 tokens-out ≈ $1–2 / day at cap.
- Real-world: hourly mode (24 calls/day) → cents per day.

If the bill drifts upward, drop `EFLOUD_OVERSEER_LLM_DAILY_CAP` and recreate.
