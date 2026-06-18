# Live Edge Measurement Core — Design Spec (v2, hardened)

**Date:** 2026-06-18
**Status:** DRAFT v2 — hardened by a 43-agent adversarial review (27 verified corrections folded in); pending user sign-off → writing-plans.
**Track:** "Professional League" #1 — Edge & Track-Record (internal-first)
**Owner:** efloud-bot

> **Review provenance.** v1 was reviewed by 6 independent lenses (quant methodology, data-integrity/look-ahead, architecture-safety, honesty/overfitting, code-anchor accuracy, completeness) → 61 raw → 35 unique → 33 verified findings. The design DIRECTION (additive, default-OFF, read-only shadow measurement) was sound; the defects were **methodology-integrity and design-correctness** (the right things to catch before sign-off), not runtime hazards. v2 below folds in every REAL/PARTIAL correction.

**Coexistence (corrected):** Gemini is on `feat/smc-sl-tp-redesign`, which **also edits `engine/safe_orchestrator.py`** in the same SL/TP region where this spec's recorder choke-point lives (~:1156-1209). The earlier "different files → minimal conflict" claim was **wrong**. Plan: **land/merge Gemini's SL/TP redesign first** (incl. its uncommitted `engine/signals.py` edits) OR rebase this branch on top once it lands; insert the recorder as a single isolated best-effort helper call to minimize diff surface in the shared function.

---

## 1. Problem & Goal

The bot trades Binance Futures (mainnet, live) but has **no proven edge** — live track record ≈**−5.3% (NET)**; the Wave-2 redesign was falsified (OOS PF 1.165) and dropped; shipped indicator-only. Before any GTM push, answer rigorously:

> **Does the bot's SMC signal carry a tradeable NET edge — and if so, where (which confluence band, symbol, direction, with/without Kronos agreement)?**

**Primary (pre-registered) hypothesis:** pooled **NET** expectancy (after fees+funding+slippage) across the **tradeable** universe is > 0 with a margin. All breakdowns are **SECONDARY/exploratory** (subject to multiple-testing control).

**Goal (this iteration):** an **internal-first edge measurement core** — record *every first-sight signal* (tradeable **and** read-only), resolve its *hypothetical* outcome (shadow-resolution faithful to the bot's actual execution), unify bot/Kronos/agents verdicts per signal, and compute **honest, cost-netted, significance-gated** edge metrics. Output = private CLI report.

**Non-goals (this iteration):** public research-log, SEO, frontend dashboard, Supabase publish, real-time resolver, `/api/metrics/edge` endpoint, real-vs-shadow execution-cost analysis. (Deferred.)

---

## 2. Existing Substrate (what we build ON)

The bot has a **trade-centric** ledger; we add the missing **signal-centric** layer.

- **Trade outcome ledger (backbone):** `engine/journal.py:25` `TradeSnapshot` → `state/trade_journal.jsonl`. Entry context, exit/PnL, MFE/MAE, `agent_review`, slippage/latency (`actual_fill_price`, `slippage_pct`, journal.py:46-48). `:114` `TradeJournal`; `:281` `stats()` live win_rate/PF/avg. **Only records signals that became positions.**
- **First-sight dedup + orchestrator choke-point (the RIGHT hook):** `engine/safe_orchestrator.py:240` `_processed_signals: dict`, key **`(symbol, direction, round(entry,2))`** (safe_orchestrator.py:1197), inserted at `:1209` (`self._processed_signals[sig_key]=now_ts`), 1h window-clear (`:1200-1203`), restart-restore (`:362`), pop-on-reverse-fail (`:1338`). The `is_tradeable` split is at `:1216/:1219/:1231`.
- **`_on_signal_readonly` is NOT a universal choke-point (key v1 error):** `backend/bot_runner.py:910`; its only call site `safe_orchestrator.py:1222` is **strictly inside `if not is_tradeable:` (:1219)** → fires ONLY for non-tradeable symbols (the *complement* of the tradeable universe). It is also wired only when `kronos.enabled AND 'readonly' in run_on` (both default-OFF in `configs/config.phase2_1k.yaml:142-143`) and returns early (bot_runner.py:926) unless Kronos prewarmed → **dead code in prod.** Must NOT be the recorder hook.
- **Kronos:** `engine/ai/kronos.py:166` `synthesize_signal_with_kronos` returns only `{comment, confidence, source}` (`:251-255`); the structured `{predicted_direction, change_pct, confidence_band, range}` lives in a local `kronos_data` (bot_runner.py:1007-1011) and is **never returned**. On the readonly path it is **async-scheduled** (`run_coroutine_threadsafe`) → result does NOT exist when a synchronous record runs; gated OFF + sampled (per-(symbol,direction,bar) cooldown + drop-if-busy semaphore `:973-975`).
- **Agents:** `engine/agents/team.py:96` `review_trade` → `{team_verdict, team_confidence, agents:[…]}`. Sync pre-trade gating → `latest.meta['agent_review']` (safe_orchestrator.py:1180-1181); async post-fill → trade-journal. Runs only on the **tradeable** flow; `gating` default OFF.
- **Live metrics (trade-level):** `journal.stats()`; `scripts/routines/equity_report.py:6 build_report` (+`@register:70`); `ops/daily_report/monthly.py`; `backend/api.py:253 /equity` (JSONL-first, DB-optional; `:272` UR-003 "never public").
- **DB reality:** `backend/db.py:19 Database` no-ops when `DATABASE_URL` unset (prod) → JSONL is the de-facto store.

### Gaps this spec closes
1. No raw signal ledger (rejected/unfilled signals lost; `_processed_signals` keeps only a dedup tuple).
2. No unified per-signal verdict (Kronos→Telegram-only & async; agents→two disjoint, tradeable-only sinks).
3. No Kronos field on the outcome record.
4. No signal→outcome correlation id (`trade_id`=`pos.id` only exists post-fill).
5. Unpopulated journal fields — `htf_bias`/`intent_score_entry`/`confluence_score` written as `0`/`""` at `safe_orchestrator.py:583-586`, and `timeframe=""` at `:576` (all in the same `TradeSnapshot(...)` constructor, :572-597).
6. No per-signal, cost-netted, significance-gated edge metric.

---

## 3. Methodology — Shadow-Resolution of ALL first-sight signals

Edge is measured on **every first-sight signal** (tradeable + read-only), replaying forward price to its *hypothetical* outcome — isolating **signal edge** from execution and yielding a large sample.

### 3.1 Fill model (MUST match the bot's ACTUAL execution — there is NO limit-entry path)
Live entry is a **MARKET order** (`exchange/__init__.py:1072`) gated by `_entry_drift_rejection` (`:508`, prod `max_entry_drift_pct=1.0`).
- **PRIMARY — MARKET-at-confirmation:** for prod `smc_version:v2`, fill = **close of the engulfing confirmation bar** (`confirmation.py:74,82`; `safe_orchestrator.py:1691-1707`). The resolver **replays the zone-pullback + engulfing confirmation** (reuse `confirm_entry`) to get the would-be fill bar/price, then races SL/TP from the bar **strictly after** the fill bar. For `v1`, fill = next-bar open after emission, subject to the same drift rejection.
- **BASELINE — MARKET-at-emission:** fill = next-bar open after `ts_emitted` (no-confirmation model), for comparison.
- **DIAGNOSTIC only — limit-touch:** clearly labelled counterfactual for the "fill-rate-if-resting" question, branched on a persisted `entry_is_retrace` flag (whether `signals.py:433-440` fired). **Not** a primary edge model.
- Store the **emitted entry** AND the **model-specific fill price** separately (never overwrite one with the other). Report expectancy under **all** models; **if the edge sign flips across models, declare NO verdict.** Cross-check shadow fill vs real `TradeSnapshot.actual_fill_price`/`slippage_pct` on the filled subset.

### 3.2 SL/TP race + resolution
- **Granularity:** resolve on **1m klines** (intrabar precision). Add `resolved_at_granularity` to the record. Resolve the **entire sample on one granularity** OR report aggregates **separately** by granularity — **never silently pool** (a silent 1m→entry-TF fallback is liquidity-correlated bias). Run a 1m-only-vs-all **sensitivity check**; if the verdict differs, the conservative-SL × granularity interaction is driving it, not edge.
- **Per-direction orientation:** LONG → SL when `bar.low ≤ sl`, TP when `bar.high ≥ tp`; SHORT inverted. The conservative tie-break applies identically in both.
- **Same-bar precedence ladder:** `SL-and-anyTP` → **SL** (conservative, prevents inflation); `TP1-and-TP2 (no SL)` → **TP1** (nearest; TP1<TP2 invariant). 1m granularity minimizes how often ties fire.
- **Look-ahead:** the bot places its order at signal-fire time, so the resolution window is `[ts_emitted, min(now, ts_emitted+max_horizon)]` (faithful — do NOT start at `brk.ts`). The SL/TP race uses only bars **strictly after** the fill bar. Batch resolver runs after bars close → no forming-bar repaint.

### 3.3 Exit economics (MUST match the partial-exit ladder, not full-position)
Live dual-target lifecycle closes **50% at TP1** (`exchange/__init__.py:1008`; `lifecycle.py:518-520`), moves SL to **breakeven** (`:411-414`), takes 25% weakness slices (`:537-558`); single-target mode (`tp2=None`, produced for v2, `tp_calc.py:14`) full-closes at TP1.
- Add `exit_model ∈ {single_target, partial_ladder}` (from whether `tp2` is numeric/None).
- `single_target` → full-close at TP1 (clean rule).
- `partial_ladder` → blended `hypo_r = 0.5·(TP1 R) + 0.5·(runner outcome ∈ {+rr2 if TP2 after TP1, ≈0 if breakeven-stopped, −1R only if SL before TP1})`. The 25% weakness slices are un-modeled (note as unknown-direction bias).
- Report BOTH a simplified single-target R and the blended partial-ladder R; label the blended figure as the honest expectancy comparable to `journal.stats()`.

### 3.4 Cost netting (CONFIRMED requirement — moved out of "open questions")
`hypo_r` MUST be netted before any verdict. With `R = |entry − sl|`, subtract from the numerator in R-units:
1. **Round-trip taker fees** = 2 × taker_rate (default 0.04% Binance USD-M; reuse the backtest commission constant, `backtest/engine.py:267-276`).
2. **Funding** = sum of 8h funding marks over the holding window, signed by direction (reuse `backtest/funding.py compute_funding_delta`; resolver already fetches klines → add the funding series).
3. **Slippage** = a **conservative haircut / sensitivity band** calibrated from the live `slippage_pct` distribution (`scripts/analyze_entry_slippage.py`) — NOT a measured net (shadow slippage is structurally 0 at the fill).

Report **BOTH gross and net** expectancy. Gate the "edge exists" label on **NET** expectancy with margin (net E[R] > threshold AND lower CI bound > cost hurdle), **never gross**. The headline MUST state shadow R is GROSS-or-NET explicitly and that the comparison baseline is the live **NET −5.3%**.

### 3.5 Timeout/expiry (CONFIRMED: report 3 ways)
If neither SL nor TP within `max_horizon` (default **48h** = 192×15m bars): compute expectancy **three ways** — mark-to-market R, hard 0R, and excluded — as a **mandatory robustness panel**; require the **sign of expectancy to be stable across all three** before any "edge exists" claim (else NO edge — timeout-marking artifact). Surface **timeout-RATE** (alongside fill-rate) as a first-class headline metric; report the timeout bucket's count + MFE_r/MAE_r distribution.

### 3.6 Sample identity & independence (prevents N-inflation)
A break stays eligible for `recency_bars` (prod 40 @ 15m ≈ 5-10h; `signals.py:373,392`) while the bot re-runs ~30s and the orchestrator dedup prunes at 3600s (`:1202`) — so after ~1h the **same break (identical `brk.ts`)** passes dedup as NEW.
- **Mint `signal_id` from `brk_ts_ms`** (derived from `Signal.timestamp = brk.ts`, `signals.py:719`, via the existing `_bar_ts_to_ms` helper) + `short_hash(entry,sl,tp1)` — **NOT wall-clock `ts_ms`.**
- **Dedup the LEDGER on `(symbol, direction, brk_ts)` with NO time expiry** (independent of the 1h-pruned `_processed_signals`); **persist the seen-set** so a restart cannot re-mint a row. Use an **asset-relative price tolerance** (tick-fraction / sig-figs) for the dedup key on sub-cent symbols (DOGE/TRX/XRP/1000PEPE) instead of `round(entry,2)`.
- In `edge_metrics`, **cluster temporally-overlapping re-fires as a single observation** (embargo / block-bootstrap); report **effective independent N** alongside raw N.

---

## 4. Components (isolated units)

### 4.1 `SignalLedger` — `engine/signal_ledger.py` (new)
Append-only JSONL (path derived from `state_dir`, §10), mirroring `TradeJournal`. `SignalRecord`:
- **Identity:** `signal_id` (=`{symbol}-{direction}-{brk_ts_ms}-{short_hash(entry,sl,tp1)}`), `ts_emitted` (**int epoch-ms UTC**), `brk_ts`, `symbol`, **`direction`** (`'LONG'|'SHORT'` — NOT `side`/buy-sell), `emitted_entry`, `sl`, `tp1`, `tp2`, `confluence`, `rr1`, `rr2`, `timeframe`, `htf_bias`, `regime`, `reasons`, `was_tradeable` (bool), `entry_is_retrace` (bool), `exit_model`.
- **Verdicts:** `kronos_verdict` (nullable — recorded null, attached later, §4.2), `agents_verdict` (nullable/sparse — present only for tradeable signals when `agent_team.enabled` is on; documented caveat).
- **Resolution (resolver fills):** `status ∈ {open, filled, resolved, timeout, unfilled, unresolved_data}`, `disposition ∈ {opened, readonly, vetoed, guard_blocked, deduped}`, `outcome ∈ {tp1, tp2, sl, timeout, unfilled}`, `fill_price`, `hypo_r_gross`, `hypo_r_net`, `ts_filled`, `ts_resolved` (int epoch-ms UTC), `bars_to_fill`, `bars_to_resolve`, `mfe_r`, `mae_r`, `resolved_at_granularity`.
- **Link:** `trade_id` (nullable — reserved for a future shadow-vs-real join; population deferred with that out-of-scope analysis).

### 4.2 Recorder hook — `engine/safe_orchestrator.py` ~:1208-1213 (NOT `_on_signal_readonly`)
Place `signal_ledger.record_signal(...)` **immediately after the first-sight dedup insert** (`self._processed_signals[sig_key]=now_ts`, :1209), **BEFORE the `is_tradeable` split** (:1216) — captures BOTH tradeable and read-only first-sight signals, reuses the live `sig_key` (byte-identical idempotency to the trade path). Read in-scope locals: `latest` Signal (`signals.py:116-124`), `htf_bias` (:1044), `regime_analysis.regime` (:1016), resolved TF chain, `latest.meta.get('agent_review')`, `permission_mgr.is_tradeable(symbol)` → `was_tradeable`. Behind an **independent `signal_ledger.enabled` flag** (default OFF), **decoupled from `kronos.*`**, added to the **LIVE** config `configs/config.phase2_1k.yaml` (a flag in the inert root `config.yaml` is silently dead). **Own `try/except … log-and-continue`** (the `NotificationManager` wrapper no longer applies here). In the tradeable `else` branch, after `open_position()` returns `pos`, call `signal_ledger.set_trade_id(signal_id, pos.id)` to back-link. **Zero change to trade/safety logic.**

### 4.3 `shadow_resolver` — `scripts/routines/resolve_signals.py` (new), SEPARATE PROCESS
Periodic batch (cron/loop, `@register` pattern). For each `open`/`filled` signal: **windowed/paginated range fetch** of klines (since-cursor loop over `ccxt fetch_ohlcv(symbol,tf,since,limit)` or `data/fetcher.py:30 OHLCVFetcher.fetch_ohlcv_range`), capped `[brk_ts/ts_emitted, min(now, +max_horizon)]` — **NOT** the count-based `BinanceClient.fetch_ohlcv(limit=…)` which can't reach old signals. Apply §3 fill model + SL/TP race + cost netting; write outcome back (idempotent).
- **Isolation:** runs as a **separate process** with its **own public/unauthenticated ccxt instance** (`OHLCVFetcher`), imports **no order-placing surface** (enforce with an import-guard test). **Order isolation is guaranteed; data-plane is NOT** — kline fetches share the **per-IP REQUEST_WEIGHT** pool with the live loop, so add a **weight budget** (batch large limits, bounded concurrency) to avoid 418/429 degrading the trading client.
- **Survivorship:** on fetch failure / gap-refusal mark `status='unresolved_data'` (distinct from `timeout`; NOT dropped/unfilled), **EXCLUDE** from edge metrics, and **REPORT** per-symbol/per-band unresolved counts. Add a **minimum-resolution-coverage gate** that suppresses/asterisks a symbol's cell below threshold.

### 4.4 `edge_metrics` — `engine/edge_metrics.py` (new)
Over **resolved** signals. **Statistics are acceptance criteria, not polish:**
- **Pre-register** the primary hypothesis (pooled NET expectancy, tradeable universe); all breakdowns SECONDARY.
- **Min-N gate:** suppress cells with `n<30` → print `insufficient sample (n<K)` (no PF/expectancy); require `~n≥100` before any cell is called an "edge".
- **CIs:** Wilson CI on win-rate, bootstrap CI on expectancy/PF, per cell. Claim edge only when the lower CI bound clears the cost hurdle.
- **Multiple-testing:** Benjamini-Hochberg FDR (or Bonferroni) across all reported cells (and note it applies to any operator cross-tab).
- **Independence:** use effective independent N (§3.6 clustering), not raw N.
- Breakdowns: confluence band, symbol, direction, **was_tradeable**, Kronos-agreement (sparse — its sampling caveat). Fix the `journal.stats()` **PF=0-when-no-losses footgun** → emit `null`/`n/a`.
- `agree` (Kronos) is defined against the signal's OWN direction/horizon (Kronos direction matches trade direction AND forecast range reaches TP1 within `max_horizon`) — documented as a **directional hint**, not a TP-before-SL statement (different horizon/source: 1h yfinance `-USD`).

### 4.5 Read surface — `scripts/routines/edge_report.py` (new) + observability
- **Report contract** (not a bare dump): LEAD with a plain-language **STATUS line** from an explicit decision rule (e.g. `INSUFFICIENT EVIDENCE — n=23 resolved, gross-of-costs, readonly universe`), NOT a metrics grid. Every metric cell carries its resolved-sample **N + CI**; below min-N emits `null`/`insufficient_n`. Every headline number is **labelled with its active conditioning** (universe, conf-floor, regime, gross/net). Fixed disclaimer: shadow `hypo_r` is hypothetical (fill model + conservative same-bar=SL) and is NOT the live NET record (≈−5.3%). Print the full **status breakdown** (total + % resolved/open/unfilled/unresolved_data) so the denominator is honest.
- **Observability (part of DoD):** write `state/…/signal_resolver_heartbeat.json` via the existing `write_snapshot()` with per-pass counters `{scanned, newly_filled, resolved, timed_out, still_open, fetch_failed}`; emit an **AlertRouter** breach when fetch-failure rate > `resolver.fetch_fail_alert_pct` (default ~20%) OR no successful pass within N minutes. Without telemetry, "no edge" is indistinguishable from "resolver silently failed" (survivorship → false GO).
- `/api/metrics/edge`: **OUT OF SCOPE this iteration** (§8). If ever added it MUST use `dependencies=[Depends(require_auth)]` (operator-only, never public per UR-003) + the `/equity` JSONL-first read pattern.

---

## 5. Data Flow

```
SMC first-sight signal → safe_orchestrator.py:~1209 (after dedup insert, BEFORE is_tradeable split)
   → SignalLedger.record_signal(direction/entry/sl/tp1/tp2/confluence/rr/reasons/htf_bias/regime/tf/was_tradeable/exit_model;
                                kronos_verdict=null; agents_verdict=latest.meta['agent_review']?)   [own try/except]
   → (tradeable else branch) open_position → set_trade_id(signal_id, pos.id)
   → (async) _run_kronos_analysis completes → attach_kronos(signal_id, structured forecast + agree)
        ↓ state/<state_dir>/signal_ledger.jsonl
   [SEPARATE PROCESS, cadence] shadow_resolver: read open/filled → windowed range klines (public ccxt, weight-budgeted)
        → fill model (MARKET-at-confirmation primary) → SL/TP race (1m, per-direction, conservative same-bar=SL, after fill bar)
        → cost-net (fees+funding+slippage band) → write {status/outcome/hypo_r_gross/hypo_r_net/mfe/mae} (idempotent)
        → heartbeat + fetch-fail AlertRouter
        ↓
   edge_metrics(ledger): NET expectancy + min-N gate + Wilson/bootstrap CI + BH-FDR + effective-N + breakdowns
        ↓
   edge_report.py: STATUS line first, conditioned + CI'd, gross-vs-net disclaimer   [+ /api/metrics/edge DEFERRED]
```

---

## 6. Safety / Error Handling

- **100% additive**, **default-OFF** (`signal_ledger.enabled`), **zero change** to trade/safety/lifecycle logic.
- **Order isolation guaranteed** (resolver = separate process, public ccxt, import-guard test → no order surface). **Data-plane NOT isolated** — per-IP REQUEST_WEIGHT shared with the live loop → weight budget required (§4.3). The v1 "read-only ⇒ cannot affect trading" claim is **too strong** and corrected here.
- **Best-effort recorder:** at the relocated choke-point, `record_signal(...)` in its own `try/except Exception: log.warning` (no re-raise). Regression test: a recorder that raises does NOT abort the orchestrator step or block trade execution. (Worst case without it: skip one symbol for one ~30s cycle — the per-symbol loop at `bot_runner.py:476-511` catches — but we wrap explicitly anyway.)
- **DB-less friendly:** JSONL-first; optional Postgres mirror only via the `db.py` no-op pattern; never required.
- **Honesty guards** (code AND report-surface): conservative same-bar=SL; look-ahead window faithful + race after fill bar; fill-rate & timeout-rate & unresolved_data reported; cost-netted NET headline; min-N/CI/FDR gates; Kronos/agents sparsity caveats.
- **Coexistence:** both this and `feat/smc-sl-tp-redesign` edit `engine/safe_orchestrator.py` near the same region → sequence merges (§ header) and keep the recorder a single isolated helper call.

---

## 7. Testing (hermetic, no live exchange / no live trading)

- `SignalLedger`: record/persist round-trip; **brk_ts-based first-sight dedup** (cross-epoch re-emission of the same break → NO duplicate row; persisted seen-set survives restart); sub-cent tolerance; `signal_id` stability.
- `shadow_resolver` on synthetic klines: SL-first, TP1-first, TP2-first, **LONG and SHORT same-bar → SL**, `TP1-and-TP2-no-SL → TP1`, **unfilled** (entry/confirmation never occurs), **timeout**, **look-ahead** (ignores pre-fill bars), **unresolved_data** (fetch fail → excluded, not dropped), partial-ladder vs single-target `exit_model`, cost-netting math.
- `edge_metrics`: min-N suppression, Wilson/bootstrap CI, BH-FDR, effective-N clustering, PF-null-when-no-losses, all-timeout + **sign-flip-across-timeout-marking** → NO-edge, was_tradeable breakdown.
- Safety: **recorder-raise does not abort orchestrator**; resolver **import-guard** (no order surface).
- Run: `.venv\Scripts\python -m pytest backend/tests/test_processed_signals_persistence.py engine/agents -q` + new tests. **Do not run live.**

---

## 8. Out of Scope (YAGNI — this iteration)

Public research-log / SEO, frontend dashboard, Supabase publish, real-time resolver, forcing Kronos on every signal (capture opportunistically/attach-after), `/api/metrics/edge` endpoint, real-vs-shadow execution-cost analysis (next iteration once shadow core is trusted).

---

## 9. Confirmed Decisions (open questions resolved by the review)

| # | Decision |
|---|----------|
| Fill model | **MARKET-at-confirmation primary** (+ MARKET-at-emission baseline; limit-touch diagnostic only). Sign-flip across models → NO verdict. |
| Costs | **Netted into `hypo_r` (fees+funding+slippage band)**; verdict gated on NET, never gross. |
| Same-bar tie | Conservative **= SL first** (both directions); `TP1&TP2-no-SL → TP1`. |
| Granularity | **1m**, never silently pooled with fallback; 1m-vs-all sensitivity required. |
| Timeout | **3-way panel** (m2m / 0R / excluded); require sign-stability; timeout-rate first-class. |
| Identity | `signal_id` from **`brk_ts`** (not wall-clock); ledger dedup `(symbol,direction,brk_ts)` no-expiry, persisted, asset-relative tolerance. |
| Min-N / significance | per-cell **n≥30 to print, ~n≥100 to claim edge**; Wilson+bootstrap CI; **BH-FDR**; effective independent N. |
| Timestamps | **integer epoch-ms UTC** everywhere; never stdlib `.timestamp()` on naive ISO (local-tz shift); use `pd.Timestamp(s).value`/`_bar_ts_to_ms`. |
| Field naming | **`direction` ('LONG'/'SHORT')**, not `side` (buy/sell). |

---

## 10. Config Schema (new — pinned to the LIVE config)

Add to `configs/config.phase2_1k.yaml` (the FastAPI/bot_runner path does NOT read root `config.yaml`):

```yaml
signal_ledger:
  enabled: false            # bool — master flag (decoupled from kronos.*)
  fill_window_bars: 8       # int  — bars after emission within which MARKET-at-confirmation must occur, else 'unfilled'
  max_horizon_hours: 48     # int  — SL/TP race expiry
  resolution_tf: "1m"       # str  — resolver kline granularity
  resolver_cadence_sec: 300 # int  — batch pass interval
  max_symbols: 25           # int  — per-pass open-signal cap (weight budget)
  fetch_fail_alert_pct: 20  # int  — AlertRouter breach threshold
```
Derive ledger/heartbeat paths in Python from `cfg['operation'].get('state_dir','./state')` (like `TradeJournal`, bot_runner.py:272) — NOT a literal `state/…` path (live `state_dir:./state_1k`) and NOT YAML `${state_dir}` interpolation (unsupported).

---

## 11. Definition of Done

**ENGINEERING DONE:** ledger records BOTH tradeable + read-only first-sight signals live behind the flag (no duplicate rows across re-emissions); resolver runs on cadence as a separate process with heartbeat + fetch-failure reporting; `edge_report` emits all §4.4 breakdowns with the §4.5 report contract; all §7 hermetic tests green; **zero trade-path regression** (recorder-raise test + import-guard test pass).

**RESEARCH READY (gates any verdict):** the stated minimum N (overall and per-cell) and significance/effect bar are met before `edge_report` prints any "edge exists/absent" verdict; until then it prints `INSUFFICIENT SAMPLE — n=<n> < <min_N>`. The "edge exists" label requires **NET** expectancy with lower-CI margin, **sign-stable across fill-models and timeout-markings**, after BH-FDR.

---

## Appendix — anchor corrections vs v1
`_on_signal_readonly` is read-only-subset + Kronos-gated, NOT a universal hook (recorder relocated to `safe_orchestrator.py:~1209`). Dedup key is `(symbol, direction, round(entry,2))` at `:1197` (not `(symbol, side, round(entry))`). Gap #5: `timeframe=""` at `:576`, others at `:583-586` (same constructor :572-597). All other v1 anchors (journal `:25/:114/:281`, `_processed_signals:240`, `team.review_trade:96`, `db.py:19`, `equity_report:6/@register:70`, Kronos `bot_runner.py:1072`) verified correct.
