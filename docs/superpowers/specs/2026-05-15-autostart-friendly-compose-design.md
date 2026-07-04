# Autostart-friendly compose orchestration — design

**Status:** Draft (in-flight during 2026-05-15 VPS rebuild redeploy).

## Problem

After the VPS rebuild incident, the redeploy plan set `EFLOUD_AUTOSTART=0` so the operator could open the dashboard, verify state, and press Start manually. In practice, this state is incompatible with the rest of the compose orchestration:

- `healthz` returns 503 with `["loop_tick_never", "exchange_ping_never"]` while the bot is idle (correct behavior — bot has not yet ticked).
- Docker healthcheck flags `efloud-bot` as `unhealthy`.
- `efloud-caddy` depends on `efloud-bot.condition: service_healthy` → never starts → dashboard unreachable → operator cannot press Start. **Deadlock.**
- `efloud-autoheal` restarts unhealthy containers every 60s after `AUTOHEAL_START_PERIOD=120s` → restarts a working-but-stopped bot in a loop.

Bot is operating correctly. The orchestration was tuned for `AUTOSTART=1`.

## Constraints

- Cannot change healthz semantics in this redeploy (would require code change + tests; we are mid-deploy).
- Cannot enable `AUTOSTART=1` with 3 orphan positions on the exchange (BTC/ADA/OP from the previous run, now with manual TP/SL) — `pos_guard` uses `lifecycle.positions` only; orphans don't block new opens, so an incoming signal could double up or auto-flip under Binance hedge-off.
- Must remain rebuild-safe: future operators should not have to remember this nuance.

## Approach (chosen)

Three single-line edits to `docker-compose.prod.yml`:

1. `caddy.depends_on.efloud-bot.condition`: `service_healthy` → `service_started`
   - Caddy comes up alongside the bot, so the dashboard is reachable even while the bot is idle.
2. `efloud-bot.healthcheck.start_period`: `120s` → `600s`
   - Docker treats failing healthcheck as "still starting" for the first 10 minutes — gives the operator a window to log in, verify state, and press Start without autoheal interference.
3. `autoheal.environment.AUTOHEAL_START_PERIOD`: `120` → `600`
   - Matches the bot's start_period. After 10 min, if the bot is still 503, autoheal kicks in (restart loop becomes visible; operator must address).

Both `start_period` values are deliberately matched. After 10 min, autoheal resumes normal duty.

Trade-off: a 10-minute window where a genuinely sick bot would not auto-restart. Acceptable because:

- Overseer (now wired) detects bot_unhealthy at 3 consecutive failures and pages (currently DRY_RUN, but the heartbeat-stale rule will become signal-bearing).
- The 10-minute window applies only on fresh start (initial deploy / reboot), not mid-run restarts.
- The previous 120s window was tuned for `AUTOSTART=1`; matching the operational reality (operators need time) is reasonable.

## Rejected alternatives

- **Runtime-only fix** (stop autoheal, `--no-deps` caddy start): leaves no trace in git; future deployers will hit the same wall. Skipped.
- **Healthz code change** (return 200 when bot intentionally stopped): meaningful design work, needs tests, separate PR. Skipped for this redeploy; can be revisited.
- **Orphan reconcile + AUTOSTART=1**: most rigorous but ~30 min of work plus operational risk during the redeploy window. Out of scope for this incident.

## Acceptance

After patch:
- `docker compose ps` shows `caddy` running while `efloud-bot` is `(unhealthy)` but `running`.
- `https://<VPS-IP>.nip.io` reachable (Let's Encrypt may take ~30s on first hit).
- Operator presses Start → bot ticks → healthz 200 → all healthy.
- After Start, autoheal behaves normally (10-minute warmup elapsed by then).

## Out of scope (deferred)

- Healthz endpoint semantics for "intentionally stopped" state. Worth doing if `AUTOSTART=0` becomes the long-term posture; for now it's only used in incident recoveries.
- Orphan reconcile workflow / safe-import path. Hermes call.
