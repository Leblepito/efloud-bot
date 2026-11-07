# CONTEXT.md — domain language

This file defines the vocabulary of the efloud-bot trading system (Binance USDT-M futures, SMC
strategy) and its Pine/marketing side. It holds definitions only. Decisions live in
[`docs/adr/`](docs/adr/README.md), state in `collab/STATUS.md`, tests in `TESTS.md`. SMC indicator
mechanics (OB, FVG, OTE, CHoCH/BOS details) live in `pine/PINE_SPEC.md`.

## Core terms

| Term | Precise definition | Avoid in this context | Evidence |
|---|---|---|---|
| Bot instance | One running trading bot: a Compose service with its own config, state volume, log and Binance key, identified by `EFLOUD_BOT_ID`. Instances: **V1** = `efloud-bot` (mid profile, the main live bot), **V2** = `efloud-bot-long` (`v2-long`), **V3** = `efloud-bot-scalp` (`v3-scalp`). | "v2" on its own (collides with SMC v2) | `docker-compose.prod.yml` |
| SMC engine version | Which signal engine generates setups: **SMC v1** (`engine/smc.py`, `engine/signals.py`) or **SMC v2** (`engine/smc_v2/`), chosen by `engine.smc_version`. This is independent of the bot instance: the V1 bot runs SMC v2. | "Bot V2" for the engine | `configs/config.phase2_1k.yaml` `engine:` |
| Profile | A named timeframe chain (`scalp`, `mid`, `long`) that a bot instance selects. It is not a bot. | "the scalp bot" when you mean the profile | `data/timeframes.py` `PROFILES` |
| Timeframe chain | Entry TF (trigger, SL/TP), MTF (swing structure), HTF (trend/bias), plus the shared Daily (1d) macro filter. scalp = 5m/1h/4h, mid = 15m/4h/12h, long = 1h/8h/1d. | "4h/1h/15m chain" as a fixed fact (that was the historical mid chain) | `data/timeframes.py` |
| Setup / signal | A candidate trade produced by the engine: direction, entry, SL, TP1/TP2, confluence. It becomes an **order** only after the gates (confluence, guards, breaker, confirmation) pass. | "trade" before it is filled | `engine/signals.py` |
| Confluence score ("conf") | 0–100 score from `calc_confluence`, compared with `min_confluence`. Post-cap bonuses are added afterwards; the pre-bonus value is the **structural score** (`meta["structural_score"]`). | "confidence" | `engine/confluence.py`, audit H1 |
| Confirmation | The entry waits for price to come back to the setup's zone (zone touch) instead of entering at market on the signal (`require_confirmation`). | "fill" | `engine/safe_orchestrator.py`, ADR-0009 |
| Discovery | A setup with no structural target in range, where TP1 is a Fibonacci extension (1.272, floored at `min_rr`). | "breakout" | `engine/signals.py`, audit H7/M1 |
| Range deviation | The last bar sweeps beyond a range extreme and closes back inside; it is the range-play trigger. | "fakeout" | `engine/smc.py` `range_info`, bug-hunt #5 |
| R / RR | R = the entry-to-SL distance; RR = target distance ÷ R. `min_rr` is the minimum TP1 RR. | "risk %" (that is account risk) | `engine/signals.py` |
| Circuit breaker states | **OPEN** = normal: trading allowed. **TRIPPED** = temporary pause. **HALTED** = full stop that needs a manual reset. | Electrical usage ("open breaker = no flow"). Here OPEN means trading. | `engine/safety/breaker.py` `BreakerState` |
| Kill switch | An operator action that halts the bot and persists the HALT immediately. | "stop" (a stop does not persist the halt) | `backend/tests/test_kill_switch_persist.py` |
| Orphan position | A live exchange position that the bot is not tracking. Reconcile logs it as `ORPHAN POSITION DETECTED`. | "bare position" (different, see next row) | `exchange/__init__.py` reconcile |
| Bare / unprotected position | A live position with no working SL (and possibly no TP) on the exchange. A tracked position can be bare too (SL placement or repair failed → the SL alerts). | "orphan" | incident 2026-05-14, `ops/alerter/rules.py` `SlUnprotectedRule` |
| Orphan protection | For an **orphan** position that is also **bare**, it places a close-position STOP_MARKET SL (`mode: place_missing_sl`; `warn_only` only logs). It never adopts the position into lifecycle state, never places a TP, and never cancels orders. | "auto-close" | `engine/safety/orphan_protection.py` |
| Shadow | SMC v2 computes and logs signals but places **no** orders (`smc_v2_shadow: true`). | "observation" (that is the agent team) | ADR-0004 |
| Observation mode | The LLM agent team reviews every opened trade and writes a verdict to the journal; it never gates (`agent_team.gating: false`). | "shadow" | ADR-0002 |
| Live / mainnet | A bot using a config with `dry_run: false` against Binance mainnet. Prod V1 uses `configs/config.phase2_1k.yaml`; the root `config.yaml` is inert. | "testnet" | `EFLOUD_CONFIG_PATH` |
| NET-cost backtest gate | A backtest including fees and slippage that an edge or scoring change must pass before going live. | "backtest" without costs | ADR-0003 |
| Wave-1 / Wave-2 | Pine product generations under `pine/u2algo/`. Wave-1 = the shipped indicator; Wave-2 = the dropped premium redesign. | "v1/v2" | ADR-0005 |

## Concept relationships

- A bot instance selects exactly one profile and one SMC engine version (SMC v2 per-symbol via `smc_v2_symbols`).
- A setup moves to an order only through: confluence ≥ `min_confluence` → guards → breaker is OPEN → confirmation.
- Breaker: OPEN → TRIPPED (temporary limit) → back to OPEN after the window; any → HALTED (emergency/kill switch), and HALTED → OPEN only via manual reset.
- An orphan position may also be bare. Orphan protection acts only on orphan + bare positions; the orphan alert covers every orphan; the SL alerts cover tracked bare positions.

## Resolved ambiguities

- **"V2"**: "Bot V2" / `v2.` means the long-profile bot instance; "SMC v2" means the engine. Always write the qualifier.
- **Long and scalp chains**: the profiles are long = 1h/8h/**1d** and scalp = 5m/1h/**4h** (`data/timeframes.py`, and the long/scalp configs set `profile:` accordingly). Older inline comments that say 1w / 12h are stale.
- **"1k" in config file names** is legacy and is not the wallet size.

## Needs confirmation

- Whether the V2 (long) and V3 (scalp) instances count as "live" while they are stopped (`AUTOSTART=0`, not running as of 2026-11-07). Owner: operator.
