# ADR-0012: Pause new V1 mainnet entries; resize to the real exposure cap at go-live; V2/V3 stay out of trading

**Date**: 2026-11-14
**Status**: accepted (2026-11-14)
**Deciders**: operator (approved decisions K1, K7, K8 of the ECC revision spec; K1 executed by the operator's own
command), claude-code (proposal and execution)

> **Operatör notu (TR):** K1 uygulandı (2026-11-14 12:30 UTC): V1 mainnet'te yeni girişler durdu, açık
> pozisyon / SL-TP / reconcile yönetimi ve gölge loglar sürüyor. K7 ve ADR-0011'deki **ileri tarihli runtime
> maddeleri** (go-live'da `max_open_positions`, `starting_balance` güncellemesi, %75 bakiye tabanı, $25 → $50
> notional) bu ADR ile kararlaştırıldı ama **uygulanmadan önce ayrıca operatör onayı alınır**; bu ADR o onayın
> yerine geçmez.

## Context

The live V1 flow (SMC v2 LuxAlgo mode, `configs/config.phase2_1k.yaml:187-188`) was measured NET negative:
−0.30 R/trade, PF 0.65, n=217 over 60 days (`collab/outputs/claude-code/2026-11-04-lux-gate-counterfactual.md:42`)
and gross PF 0.69, NET −$181.9 (−0.91 %, n=137) over 41 days (`collab/outputs/claude-code/2026-11-07-backtest-live-parity.md:21-24`).
The operator's own checkpoint of 2026-11-07 ("if it is still negative after 20-30 trades, we change it") had
passed with no owner. The emergency balance halt is off (`configs/config.phase2_1k.yaml:424`) and max-hold is off
(`:407`). The effective position cap is lower than the documented one: the exposure check
(`engine/safety/position_guard.py:271-282`) allows ⌊`safety.max_total_exposure` (`:403`) × balance /
notional⌋ positions, with notional = `risk.fixed_position_usdt` (`:299`) × `exchange.leverage` (`:71`); at
`safety.starting_balance` (`:375`) that is 4, not the `risk.max_open_positions` of 10 (`:272`). The long and
scalp bots (V2/V3) run configs with known gaps (proxy ATR, missing gates, inconsistent breaker calibration, no
alerter or canary coverage — `docs/audit/2026-11-14-ecc/00-FABLE-sentez.md` §2 X28, X29).

## Decision

**K1 — pause new V1 entries (applied 2026-11-14 12:30 UTC).** `EFLOUD_PAUSE_NEW_ENTRIES=true` is set in the
VPS `.env.production` (a backup copy was taken first), and only the `efloud-bot` service is recreated with
`docker compose -f docker-compose.prod.yml up -d --no-deps efloud-bot`, with no image rebuild. The env value
overrides `safety.pause_new_entries` (`configs/config.phase2_1k.yaml:458`; precedence in
`engine/safety/position_guard.py:62-117`). The gate (`engine/safety/position_guard.py:175-206`) blocks only new
entries and is also checked on the v2 order path (`engine/safe_orchestrator.py:3146-3158`); reconcile,
lifecycle, exchange-side SL/TP, breaker updates, notifications and shadow logs continue. V1 runs with
`EFLOUD_AUTOSTART=0` (`backend/main.py:74-87`), so after the recreate the loop was started with
`/api/bot/start` while the pause was already active. Verified at application: log line
`pause_new_entries config loaded: effective=True source=env` (event `position_guard.pause_config_loaded`),
0 open positions, breaker OPEN, mainnet (record: `collab/STATUS.md`). No guard is weakened.

**K7 — exposure and sizing.** While paused, exposure and sizing do not change. At the go-live of a model that
passed ADR-0011: `risk.max_open_positions` is set to ⌊`max_total_exposure` × balance / notional⌋ (the cap is
not raised to reach 10), subject to a separate operator approval at go-live (not authorised by this ADR);
`safety.starting_balance` is updated to the balance on that day, subject to a separate operator approval at
go-live (not authorised by this ADR); an absolute floor "TRIP + Telegram", default OFF (GATED item Ö12,
`safety.balance_floor_trip_usdt: null`, not in code), is turned on at 75 % of that day's balance, subject to a
separate operator approval at go-live (not authorised by this ADR). A permanent HALT is not reintroduced (operator decision `b2154c5`).

**K8 — V2/V3.** The long and scalp bots must not trade with their current configs. When K1 was applied their
state was read: containers up, no order log lines in the previous 7 days, pause env not set (snapshot
2026-11-14 12:12 UTC, `collab/STATUS.md`). If they are seen trading, the operator applies the same env pause
to them after confirming that they are trading (no agent applies it on its own).
Restarting them for trading needs the per-profile backtest and fixes listed as GATED item Ö14.

## Alternatives Considered

### Alternative 1: Keep the live flow running and review after 20-30 trades
- **Pros**: more live data; no operational change.
- **Cons**: keeps a measured −0.30 R/trade flow on mainnet with the emergency halt off; the checkpoint had no
  owner and had already passed.
- **Why not**: shadow logs keep collecting data without live risk.

### Alternative 2: Reduce position size and continue
- **Pros**: smaller losses while collecting live fills.
- **Cons**: still negative expectancy; changes sizing, a risk change that needs its own review.
- **Why not**: pausing uses an existing guard and is reversed with one env line.

### Alternative 3: Raise `max_total_exposure` so 10 positions fit
- **Pros**: matches the documented "10 positions" and the "more trades" request.
- **Cons**: enlarges a NET-negative flow; weakens a guard.
- **Why not**: rejected (Karpathy-3, `docs/audit/2026-11-14-ecc/00-FABLE-sentez.md` §6.3 N2).

## Consequences

### Positive
- No new mainnet losses from a flow measured negative; protection of open positions is unchanged.
- At go-live, the configured position count matches what the exposure guard really allows.

### Negative
- No live fills for the LuxAlgo flow while paused; forward evidence comes from shadow logs only.
- The pause is read once at process start; a change needs a container recreate, not `docker restart`
  (`engine/safety/position_guard.py:33-39`).

### Risks
- The pause is forgotten when a model passes ADR-0011. Mitigation: the go-live PR lifts it explicitly, and
  `collab/STATUS.md` carries the K1 row.
- **Rollback:** restore the `.env.production` backup (or remove the line / set it to `false`), run the same
  `up -d --no-deps efloud-bot`, then `/api/bot/start`; confirm `effective=False` in the log.
