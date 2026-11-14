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
| Confluence score ("conf") | **SMC v1 only.** 0–100 score from `calc_confluence`, compared with `risk.min_confluence`. Post-cap bonuses are added afterwards; the pre-bonus value is the **structural score** (`meta["structural_score"]`). Inert on SMC v2 symbols because v1 entries are muted there (`engine/safe_orchestrator.py:1486-1495`). | "confidence"; mixing it up with the LuxAlgo concept count | `engine/confluence.py`, audit H1 |
| LuxAlgo concept count | **Live SMC v2 path.** The number of extra concept tags on the break's OB (`SWING_OB`, `OTE`, `EQ`, `FVG`, `SWEEP`), compared with `smc_v2.luxalgo.min_confluence` (`configs/config.phase2_1k.yaml:205`). `SWING_OB` is added automatically for every swing (non-internal) break, so in practice the gate only filters internal breaks. | "confluence score" (that is v1's 0–100 score) | `engine/smc_v2/luxalgo.py:477-478,549-551` |
| Confirmation | After the zone retest, the entry waits for an **engulfing candle to close** inside the zone on the entry TF (mid profile: 15m); only then is a **MARKET** order sent. There is no entry at market on the break bar (`require_confirmation`). | "fill"; "limit entry" (the live entry is a market order) | `engine/smc_v2/confirmation.py:23`, `engine/safe_orchestrator.py:2260-2263`, `exchange/__init__.py:1151-1153`, ADR-0009 |
| Discovery | A setup with no structural target in range, where TP1 is a Fibonacci extension (1.272, floored at `min_rr`). | "breakout" | `engine/signals.py`, audit H7/M1 |
| Range deviation | The last bar sweeps beyond a range extreme and closes back inside; it is the range-play trigger. | "fakeout" | `engine/smc.py` `range_info`, bug-hunt #5 |
| R / RR | R = the entry-to-SL distance; RR = target distance ÷ R. `min_rr` is the minimum TP1 RR. | "risk %" (that is account risk) | `engine/signals.py` |
| Circuit breaker states | **OPEN** = normal: trading allowed. **TRIPPED** = temporary pause. **HALTED** = full stop that needs a manual reset. | Electrical usage ("open breaker = no flow"). Here OPEN means trading. | `engine/safety/breaker.py` `BreakerState` |
| Kill switch | An operator action that halts the bot and persists the HALT immediately. | "stop" (a stop does not persist the halt) | `backend/tests/test_kill_switch_persist.py` |
| Orphan position | A live exchange position that the bot is not tracking. Reconcile logs it as `ORPHAN POSITION DETECTED`. | "bare position" (different, see next row) | `exchange/__init__.py` reconcile |
| Bare / unprotected position | A live position with no working SL (and possibly no TP) on the exchange. A tracked position can be bare too (SL placement or repair failed → the SL alerts). | "orphan" | incident 2026-05-14, `ops/alerter/rules.py` `SlUnprotectedRule` |
| Orphan protection | For an **orphan** position that is also **bare**, it places a close-position STOP_MARKET SL (`mode: place_missing_sl`; `warn_only` only logs). It never adopts the position into lifecycle state, never places a TP, and never cancels orders. | "auto-close" | `engine/safety/orphan_protection.py` |
| Shadow | A path that computes and logs but places **no** orders. Engine-level: `smc_v2_shadow: true` (off in prod, `configs/config.phase2_1k.yaml:95`). Feature-level shadows inside the live engine: `smc_v2.touch_entry: shadow` (`[touch shadow]` log, `:211`) and `smc_v2.fvg_entry: shadow` (`[fvg shadow]` log, `:216`; report `tools/fvg_shadow_report.py`). Neither has a `live` value in code. | "observation" (that is the agent team) | ADR-0004 |
| Observation mode | The LLM agent team reviews every opened trade and writes a verdict to the journal; it never gates (`agent_team.gating: false`). | "shadow" | ADR-0002 |
| Live / mainnet | A bot using a config with `dry_run: false` against Binance mainnet. Prod V1 uses `configs/config.phase2_1k.yaml`; the root `config.yaml` is inert. | "testnet" | `EFLOUD_CONFIG_PATH` |
| NET-cost backtest gate | A backtest including fees and slippage that an edge or scoring change must pass before going live. | "backtest" without costs | ADR-0003 |
| Wave-1 / Wave-2 | Pine product generations under `pine/u2algo/`. Wave-1 = the shipped indicator; Wave-2 = the dropped premium redesign. | "v1/v2" | ADR-0005 |

## Concept relationships

- A bot instance selects exactly one profile and one SMC engine version (SMC v2 per-symbol via `smc_v2_symbols`).
- There are two setup paths. Which one can place orders depends on the symbol:
  - **SMC v1 path** (muted on SMC v2 symbols, i.e. on every live V1 symbol): v1 signal → `risk.min_confluence` → guards → breaker is OPEN → confirmation. On SMC v2 symbols it is computed and only logged (`engine/safe_orchestrator.py:1486-1495`).
  - **SMC v2 LuxAlgo path** (live): HTF LuxAlgo swing trend (UNDEF → no candidate, `engine/smc_v2/luxalgo.py:524-525`) → entry-TF CHoCH/BOS in the bias direction within `risk.recency_bars` (`engine/safe_orchestrator.py:1235-1236`) → unmitigated break OB → premium/discount → LuxAlgo concept count ≥ `luxalgo.min_confluence` (`engine/smc_v2/luxalgo.py:549-551`) → setup state machine (BT-23 `max_entry_dist_atr`, BT-25 `max_zone_overshoot_atr` at `engine/safe_orchestrator.py:2697-2781`; per-symbol cap `engine/smc_v2/setup_state.py:137`) → zone retest → engulfing close (confirmation) → Po3 gate → entry blocks (stale data / watch-only / balance; `engine/safe_orchestrator.py:2263-2271`) → whitelist + breaker is OPEN → `calc_sl` (too-wide SL rejected, `engine/safe_orchestrator.py:3029`) → TP1 ≥ `risk.min_rr` (`engine/safe_orchestrator.py:3052-3058`) → sizing → position guard (exposure, opposite direction; `pos_guard.can_open_position`) → pause check (`engine/safe_orchestrator.py:3155`) → shadow gate → `OrderManager.open_position` (incl. `max_entry_drift_pct` drift guard) → MARKET order. The v1 regime gate is not applied on this path (`engine/safe_orchestrator.py:1179`).
- Breaker: OPEN → TRIPPED (daily loss or consecutive losses) → back to OPEN after the window; OPEN → HALTED (weekly drawdown, the emergency balance threshold — off when it is 0 — or the kill switch), and HALTED → OPEN only via manual reset (`engine/safety/breaker.py:283-327`).
- An orphan position may also be bare. Orphan protection acts only on orphan + bare positions; the orphan alert covers every orphan; the SL alerts cover tracked bare positions.

## Setup status matrix

One row per setup family. Labels: LIVE = places orders; SHADOW = logs only; MUTED / BYPASSED = computed or present but places no orders; REFUTED = measured negative and not live. Full lineage: `docs/audit/2026-11-14-ecc/00-FABLE-sentez.md` §3.

| Setup | Code | Status | Measured NET edge | Evidence |
|---|---|---|---|---|
| SMC v2 LuxAlgo OB retest + engulfing → MARKET | `engine/smc_v2/luxalgo.py` | **LIVE** (V1 bot) | Negative: −0.30 R/trade, PF 0.65, n=217 (60 d); backtest NET −$181.9 (−0.91 %, n=137, 41 d; gross PF 0.69) | `collab/outputs/claude-code/2026-11-04-lux-gate-counterfactual.md:42`, `collab/outputs/claude-code/2026-11-07-backtest-live-parity.md:21-24` |
| SMC v1 confluence (CHoCH/BOS → MARKET on signal) | `engine/signals.py` | MUTED on SMC v2 symbols | Did not pass the gate (Wave-2 OOS PF 1.165 < 1.30, older engine) | `engine/safe_orchestrator.py:1486-1495`, ADR-0005 |
| SMC v2 efloud triggers (OB/BB, OTE, FVG, origin swing) | `engine/smc_v2/triggers.py` | BYPASSED while LuxAlgo is on | Not measured on its own | `engine/safe_orchestrator.py:2659-2660` |
| Unconfirmed entry at the zone / on the signal | — | REFUTED | June: PF 0.62 (n=26); Nov: −0.75 R/trade, PF 0.27 (n=232) | ADR-0009, `collab/outputs/claude-code/2026-11-04-lux-gate-counterfactual.md:43` |
| Touch / wick entry | `smc_v2.touch_entry` | SHADOW | Not measured | `configs/config.phase2_1k.yaml:211`, `engine/safe_orchestrator.py:2323-2331` |
| FVG pullback limit entry | `engine/smc_v2/fvg_entry.py`, `smc_v2.fvg_entry` | SHADOW | Unproven (offline ≈ 0.00 R, n=85) | `configs/config.phase2_1k.yaml:216`, `engine/safe_orchestrator.py:2333-2340`, Fable §3 |
| Mitigated-OB / breaker retest | — (counterfactual only) | Candidate | +0.24 R, n=30, one window — unproven | `collab/outputs/claude-code/2026-11-04-lux-gate-counterfactual.md:52` |

## Live vs inert config keys (V1 bot, `configs/config.phase2_1k.yaml`)

Line numbers are the source of truth; values are not copied here.

| Effect on the live LuxAlgo path | Key (`config:line`) | Why |
|---|---|---|
| Live | `engine.smc_version`, `smc_v2_symbols`, `smc_v2_shadow` (`:90-95`) | Select SMC v2 with orders on every whitelisted symbol |
| Live | `smc_v2.luxalgo.*` (`:187-208`), incl. `min_confluence` (`:205`), `require_premium_discount` (`:199`), `kinds` (`:200`), `pullback_timeout_bars` (`:207`) | LuxAlgo candidates, bias and TP targets |
| Live | `engine.v2_use_real_atr` (`:108`, read at `engine/safe_orchestrator.py:3009`), `po3_gate` (`:131`), `max_entry_dist_atr` (`:141`), `max_pending_per_symbol` (`:158`), `max_zone_overshoot_atr` (`:168`) | State-machine gates (`engine/safe_orchestrator.py:2121-2125,2697-2781`) |
| Live | `risk.min_rr` (`:273`) | LuxAlgo TP1 gate (`engine/safe_orchestrator.py:3058`) — despite its "legacy" comment |
| Live | `risk.recency_bars` (`:293`), `risk.sl_atr_buffer` (`:294`), `safety.min_sl_atr` / `max_sl_atr` (`:412-413`) | Break recency; `calc_sl` buffer and ATR band |
| Live | `safety.daily_loss_limit_pct` … `consecutive_pause_min` (`:371-374`), `max_total_exposure` (`:403`), `max_holding_hours` (`:407`), `pause_new_entries` (`:458`, overridden by env `EFLOUD_PAUSE_NEW_ENTRIES`), `emergency_balance_threshold` (`:424`, 0 = off) | Breaker and position guard |
| Inert | `risk.min_confluence` (`:282`) | v1 score; v1 entries muted (`engine/safe_orchestrator.py:1486-1495`) |
| Inert | `risk.smc_tp_targeting`, `min_rr_tp1`, `blended_rr_target` (`:279-281`) | Only passed to the v1 signal call (`engine/safe_orchestrator.py:1372-1374`) |
| Inert | `safety.allow_volatile_entries` (`:385`) | The regime gate is not applied to SMC v2 (`engine/safe_orchestrator.py:1179`) |
| Inert | `smc_v2.pullback_timeout_bars` (`:151`) | Overridden by `luxalgo.pullback_timeout_bars` (`engine/safe_orchestrator.py:2118-2120`) |
| Inert | `smc_v2.ob_bb_entry` (`:124`), `ob_bb_zone_atr_pad` (`:176`), `origin_swing_lookback` (`:177`), `ote_zone_entry` (`:178`) | efloud triggers path is bypassed by LuxAlgo candidates (`engine/safe_orchestrator.py:2659-2660`) |
| Inert | `safety.reverse_min_profit_pct` (`:457`) | Reverse-on-profit runs only on the v1 path (`engine/safe_orchestrator.py:1736`); on SMC v2 an opposite-direction entry is rejected (`engine/safety/position_guard.py:293-305`) |
| Inert | `signal_ledger.enabled` (`:468`, false) | Flag off and the hook sits on the v1 path (`engine/safe_orchestrator.py:1497→1567`) |
| Inert by default | `smc_v2.anchor_time_axis`, `confirm_last_bar_only` (`:115-117`) | Default OFF |

## Resolved ambiguities

- **"V2"**: "Bot V2" / `v2.` means the long-profile bot instance; "SMC v2" means the engine. Always write the qualifier.
- **Long and scalp chains**: the profiles are long = 1h/8h/**1d** and scalp = 5m/1h/**4h** (`data/timeframes.py`, and the long/scalp configs set `profile:` accordingly). Older inline comments that say 1w / 12h are stale.
- **"1k" in config file names** is legacy and is not the wallet size.

## Needs confirmation

- Whether the V2 (long) and V3 (scalp) instances count as "live" while they place no orders. Their observed run state is tracked in `collab/STATUS.md`, not here. Owner: operator.
