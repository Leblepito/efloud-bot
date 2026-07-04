# Crash-Loop Recovery Runbook

## What happened?

The bot's `RuntimeState.is_in_crash_loop()` returned True (≥3 crashes in last 30 min).
As a result:
- `BotRunner.start()` skipped creating the trading task. **The bot is alive but not trading.**
- `/healthz` returns `200` with `status: "suspended"` and `failures: ["crash_loop_suspended"]`.
- The autoheal sidecar sees `(healthy)` and does NOT restart the container.
- (Step 4 alerter, when shipped) fires a CRITICAL Telegram alert.

## ⚠️ Auto-recovery does NOT work during suspension

**Read this carefully:** `RuntimeState.update_loop_tick()` is the only auto-clear path for
`crash_count`, and it is called ONLY from the trading loop. When suspension trips, the
trading loop is the FIRST thing that gets shut off (Task 3 guard). So `update_loop_tick()`
never fires during suspension, which means `crash_count` never auto-clears, which means
suspension is permanent until you manually recover.

The 60-min auto-clear only helps if the bot was crashing-then-recovering on its own and
never crossed the threshold into full suspension (e.g., 2 crashes in 30 min — under the
3-crash threshold — followed by 60 min of clean uptime would trigger auto-clear). If you
are reading this runbook, the bot is in suspension and you must use manual recovery below.

## What success vs. silent suspension looks like

The dashboard's "Start" button (POST `/api/bot/start`) returns success even during suspension —
because the guard short-circuits cleanly without setting `last_error`. **A successful click
that doesn't actually resume trading means suspension is active.** Verify by:
- `curl -s https://bot.ualgotrade.com/healthz | python -m json.tool` → look for `"status": "suspended"`
- `docker compose -f docker-compose.prod.yml logs efloud-bot --tail 50 | grep "CRASH LOOP DETECTED"`

If you see suspension, the button doesn't work — proceed with manual recovery below.

## Manual recovery (operator)

### 1. Diagnose

SSH into Hetzner and inspect the recent logs:

```bash
ssh efloud@<VPS_IP>
cd /opt/efloud-bot
docker compose -f docker-compose.prod.yml logs efloud-bot --tail 200 2>&1 | \
    grep -E "fatal_exception|Cycle error|CRASH LOOP|🛑|💥"
```

Identify the recurring exception. Common causes:
- **Config error** (typo in `EFLOUD_CONFIG_PATH`, malformed YAML)
- **Exchange API key invalid / revoked**
- **DB pool failure** (Supabase outage, pgbouncer state corruption)
- **Code regression** (deployed a bad commit; check `git log -5`)

### 2. Fix the underlying issue

Address whatever the logs show. Examples:
- Bad config → fix `.env.production` or the YAML, no redeploy needed if just env
- Bad code → `git revert <bad-commit>` + rebuild + recreate
- Exchange auth → rotate keys via Binance dashboard, update `.env.production`

### 3. Reset crash_count to release suspension

Once the underlying issue is fixed, manually clear the crash-loop state:

```bash
docker compose -f docker-compose.prod.yml exec efloud-bot python -c "
import asyncio
from engine.safety.runtime_state import RuntimeState
rs = RuntimeState(state_dir='./state')
rs.reset_crash_count()
print('crash_count reset:', rs.snapshot())
"
```

This rewrites `state/runtime.json` inside the container's volume. The change persists across
restarts.

### 4. Restart the bot to clear the suspension

```bash
docker compose -f docker-compose.prod.yml restart efloud-bot
```

After ~30s:
- `/healthz` should return `200` with `status: "ok"` (or 503 with `loop_tick_never` until first cycle)
- Trading loop creates normally (no suspension log)
- If `EFLOUD_AUTOSTART=0`, manually start via dashboard or `POST /api/bot/start`

### 5. Confirm

```bash
curl -s https://bot.ualgotrade.com/healthz | python -m json.tool
```

Expected: `status: "ok"`, `failures: []`, `crash_count: 0`.

## Disabling autoheal in an emergency

If autoheal itself is misbehaving (loop-restarting a healthy container, etc.), disable it:

```bash
docker compose -f docker-compose.prod.yml stop autoheal
```

The bot's `restart: unless-stopped` policy still handles process EXIT crashes. You lose
auto-restart on sustained unhealth, which is the only thing autoheal adds.

## Spec deviation note

The original spec §3 architecture diagram said _"on unhealthy: docker auto-restart"_, but
stock Docker compose doesn't support restart-on-unhealthy. The `willfarrell/autoheal` sidecar
fills that gap — it polls Docker's API for unhealthy labeled containers and restarts them.

The spec §4.1 "Returns 503 if any check fails" wording is intentionally bent during crash-loop
suspension: returning 503 would cause autoheal to loop-restart the container instead of
letting suspension stick. Suspension mode returns 200 with `status: "suspended"` and a
`crash_loop_suspended` entry in `failures`. The alerter (Step 4) and daily-report (Step 5)
key off the `failures` field, not just the HTTP status.
