# efloud-bot Algorithm & Setup Audit + Next-Session Plan

**Date:** 2026-06-20 · **Author:** Claude (Opus 4.8) · **Status:** AUDIT COMPLETE (read-only, no fixes applied)
**Scope:** Full 4-lens audit of the LIVE trading algorithm + setup logic (v1 `engine/signals.py` order path; v2 `engine/smc_v2/` shadow).
**Method:** `efloud-explorer` map → 4 parallel lens reviewers (`smc-strategy-reviewer` spec-fidelity, `quant-strategy-analyst` strategy-edge, `efloud-risk-ops-reviewer` risk/safety) + Claude correctness/bug-hunt lens → cross-lens synthesis → **adversarial code verification of all CRITs** (✅VERIFIED = Claude re-read the exact lines).

> **NEXT SESSION GOAL (operator):** Run an **ultrareview based on this report** + **Workflow** orchestration to examine the system end-to-end, AND integrate the `andrej-karpathy-skills` plugin (`c:\Users\utkuc\OneDrive\Utku\CRYPTO\Best_MCP_SKILL\andrej-karpathy-skills-main`) into this project "as if it were made for it." See **Part 3** below.

---

## Part 1 — Consolidated Findings (severity-ranked)

### 🔴 CRITICAL — live capital / edge / safety (fix first)

**C1 — $10k balance fallback → live over-leverage** ✅VERIFIED
`backend/bot_runner.py:487-492` swallows `get_balance()` exceptions → `balance=None`; `engine/safe_orchestrator.py:1230` `actual_balance = balance if balance is not None else 10000.0`. In LIVE mode a single transient Binance balance-fetch error (429/5xx/timeout) sizes the position for a **$10,000** account → 5-10× the intended notional and $-risk on the real ~$1-2k wallet. Breaker keeps a stale balance in that window (`safe_orchestrator.py:1007` skips sync on None) → sizing and breaker disagree. **Direction:** in live mode, `balance is None` must skip the cycle / block new entries (fail-closed); never fall back to $10k. (The $10k default is only sane for dry-run.)

**C2 — Config wallet inconsistency → breaker miscalibrated** ✅VERIFIED
`configs/config.phase2_1k.yaml` header (lines 1-14) + filename "**1k**" describe a **$1000** wallet ($950 emergency, 5% daily, 3x). The `safety:` block uses `starting_balance:2000`, `emergency_balance_threshold:1800`, `daily_loss_limit_pct:10`, leverage 5. `engine/safety/breaker.py:178` computes daily loss as `daily_pnl / starting_balance` (the fixed 2000, NOT live balance). If the real wallet is ~$1000: daily breaker is **2× too loose** (trips at −$200 = −20%, not −10%); `emergency_balance_threshold:1800 > 1000` → **instant HALT at startup**. **Direction:** confirm the REAL Binance Futures balance, then reconcile `starting_balance` / `emergency_balance_threshold` / `daily_loss_limit_pct` to it. (Claude can pull live balance via VPS read-only.)

**C3 — ML regime override silently writes the entry gate, circular-trained** ✅VERIFIED
`engine/regimes/__init__.py:172-173`: when `ml_confidence >= 65`, `regime = ml_regime` — overwriting the deterministic regime that feeds `can_open_new_position` (`regimes/__init__.py:46-51` → entry gate `safe_orchestrator.py:1139`). The model is auto-trained daily (`safe_orchestrator.py:881`) on the **rule detector's own labels** (`train.py` `build_features_and_labels`; the non-circular `build_features_and_forward_labels` is default-OFF) → "zero independent signal" (its own docstring). Can flip a true-RANGING bar to TRENDING and **open entries the deterministic gate would block**. **Direction:** make ML advisory/log-only (never write `regime`), OR switch to forward-labels + regime-conditioned NET-PnL validation before it touches the gate. *Clearest "reject" component.*

**C4 — conf=50 is the operating point the repo's own evidence rejects**
`configs/config.phase2_1k.yaml:101-105` documents: conf=80 → PF **2.34**/DD5.4/WR53.7 (dominates EVERY metric) vs conf=50 → PF **1.35** (razor-thin, gross of fees). Net-of-cost ~1.15-1.20 = the fragile band the **Wave-2 falsification already rejected** (OOS pooled PF 1.165 < 1.30). Lowered to 50 only for "trade frequency." **Direction:** NET-cost conf sweep on the Edge Measurement Core (PR #227); raise toward 80 or justify 50 with NET + OOS evidence.

### 🟠 HIGH
- **H1 — Post-cap confluence bonuses distort the threshold + Pine parity break.** `engine/confluence.py:47` returns `min(s,100)`, THEN `signals.py:449-490` adds ±5 sentiment / ±5 daily / +5 major-level / +8 stacked-zone AFTER the cap. Proximity bonuses (~+13) act as a near-constant floor lift → `min_confluence:50` no longer means "structural confluence." PA-level bonuses are **live in Python** but PINE_SPEC §A.7 says they were **dropped from the port** → live bot ≠ Pine port scoring. *(quant CRIT-1 + spec HIGH)*
- **H2 — v2 is one boolean from live + fail-OPEN default + degenerate shadow.** ✅`safe_orchestrator.py:1954` `engine_cfg.get("smc_v2_shadow", False)` — default **False** = if the key is ever dropped, v2 goes LIVE (should be fail-safe `True`). `smc_v2_symbols:["*"]` already whitelists all (no-op gate). The shadow log measures a **degenerate fixed-RR strategy** (empty HTF inputs `:1848-1850` → `RR_PROJECTION` TP; ATR proxy `:1823`), NOT the spec'd liquidity logic → don't read a shadow "pass" as validating v2. **Direction:** default True; require explicit per-symbol whitelist AND `shadow:false` as two independent conditions + operator sign-off.
- **H3 — v1 (live) has NO hard SL-width cap.** `engine/safety/position_guard.py:314-318` only WARNS when `sl_atr_mult > max_sl_atr:5.0`; v2 correctly REJECTS (`smc_v2/sl_calc.py:57-60` `SLTooFarError`). Only the liquidation-distance reject (`:325-334`, ≥18% at 5x) hard-caps v1. **Direction:** make v1 reject on `max_sl_atr` breach, matching v2.
- **H4 — Entry-drift guard fails OPEN on price-fetch failure.** `exchange/__init__.py:1039` sets `live_price=0.0` on `get_price()` error → `_entry_drift_rejection` allows the entry (`:523`). When Binance is flaky (the exact condition that causes drift), the guard disables itself → fills at live price, TP possibly already passed → SL-only naked-TP (-2021) = the 2026-05-31 incident. **Direction:** fail-CLOSED (reject) when drift-protection is on and price is unavailable.
- **H5 — HTF bias fabricated from chop.** `signals.py:305-328`: structural UNDEF → 40-bar ±2% slope → entry-TF (15m) range discount/premium → bias. Scores the +25 "HTF aligned" on a slope in the regime where SMC is least reliable; the range fallback is mean-reversion wearing a trend-following label. Mitigated: `htf_bias_original` routes UNDEF TP to liquidity targets, but the entry gate + +25 score don't de-rate. *(quant HIGH-1 + spec MED)*
- **H6 — OTE band can be built from mismatched legs.** ✅`engine/smc.py:296-304`: uses bare `sh[-1]`/`sl[-1]` with no check they bracket one impulse leg; `if d<=0: return None` silently drops OTE. Feeds +10 confluence AND the entry pullback refinement (`signals.py:433-437`). **Direction:** validate the two swings form the directional leg before building the 0.618-0.786 band.
- **H7 — Forced-RR clamp / dead min_rr gate.** ✅ TP1 is always floored to `≥ price ± risk*min_rr` (liquidity filtered `>= min_tp`, discovery `max(1.272,min_rr)` `signals.py:583/628`, deviation clamp) → the `rr1 < min_rr` reject at `:673` is **dead code (never fires)**. Real liquidity within 1.8R is EXCLUDED, and the discovery clamp launders a no-structural-target setup past the gate. Same fill↔edge tension that killed the Wave-1 strategy track. **Direction:** reject (no real target = no trade) instead of clamping; consider admitting near targets. *(Claude correctness #2 + quant HIGH-2 — independent convergence)*

### 🟡 MEDIUM
- **M1 — `is_discovery` misclassifies ranging setups → TP2=2.618R.** ✅`signals.py:644-653`: `htf_above_targets`/`htf_below_targets` are populated ONLY in the trending branch (`:572-574`); the ranging branch (`:567`, `htf_bias_original=="UNDEF"` + real liquidity TP1) leaves them empty → `is_discovery = not [] = True` → TP2 = 2.618R (too far for a range) instead of 1.618R fib_ext. Live-reachable. **Direction:** derive `is_discovery` from whether TP1 actually came from the discovery formula, not the empty-list proxy. *(Claude correctness #1)*
- **M2 — Confluence component over-counting / collinearity.** OB triple-count (+10/+5 near-swing/+3 at-EQ = +18 for ONE concept, `confluence.py:32-37`); OB/OTE/FVG fire together on "pullback into discount POI" (partial triple double-count); daily +5 echoes HTF +25. Effective DOF ≈ 3, not 8 → conf=80 may fit the dominant in-sample pattern rather than independent edge. **Direction:** single-factor NET attribution + 8-component correlation matrix. *(quant MED-1)*
- **M3 — Dual ATR definitions.** OB body filter uses high-low rolling-mean (`smc.py:195`); SL buffer uses true-range ATR (`signals.py:518`). CLAUDE.md names one "ATR(14)". OB gate is looser than a literal reading in gappy regimes. (PINE_SPEC §A.3 blesses the OB one → CLAUDE.md↔code drift.) *(spec MED)*
- **M4 — Consecutive-loss counter trusts local estimate.** `breaker.record_trade` (`safe_orchestrator.py:1093-1097`) counts on local lifecycle close; the PnL-audit sweep corrects balance but may not re-feed the consecutive counter → a sign-flipped local estimate can weaken `consecutive_loss_limit:3`. **Direction:** verify the audit sweep re-feeds the counter. *(risk MED-1)*
- **M5 — `max_holding_hours:24` force-close path unconfirmed.** Only the open-guard reads it; the reviewer could not find a lifecycle/reconcile force-close → a position may be held indefinitely once open. **Direction:** VERIFY (and add a close path if absent). *(risk MED-2)*

### 🟢 LOW / DOC
- **D1 — swing_lookback: code/config/Pine = 5, only CLAUDE.md says "4".** ⚠️ **Fix the DOC to 5; do NOT change code** (conf=50/min_rr=1.8 backtests ran at lb=5). *(spec — reclassified from CRIT to DOC)*
- **D2 — HTF range-direction fallback undocumented in CLAUDE.md** (`signals.py:319-322`, 15m range → 4h bias inverts the HTF→Entry authority chain; document it).
- Misc LOW: daily slope feeds ±5 bonus; notional-cap units coincidence (`risk/__init__.py:36` vs `position_guard:249`); `manual_reset` zeroes peak (forgives drawdown); weekly-DD (peak) vs daily-loss (starting_balance) denominator mismatch.

### ✅ PASS (verified clean)
- **No repaint / look-ahead on the live entry path** — 3 independent confirmations (spec, quant, Claude). Single choke point `exchange/__init__.py:82 fetch_ohlcv` (C1 forming-bar drop); `backend/audit/klines.py` is a separate audit/PnL subsystem (historical ranges).
- Mainnet guard intact (`engine/safety/guard.py:190-226`); server-side SL/TP; breaker HALT requires manual reset; orphan protection on; OB rule (ob_sequential=5, body>1.5×ATR, near_swing PAST-only) faithful.

**Bottom line:** core trigger (HTF-aligned CHoCH/BOS + structural confluence) is sound and repaint-free. Real risk = (a) capital miscalibration (C1/C2 config↔breaker↔sizing), (b) edge dilution (C4 conf=50, H1 bonuses, H5 chop-bias, H7 forced-RR), (c) v2 fail-open/degenerate shadow (H2). C3 (ML override) is the clearest reject.

---

## Part 2 — Suggested fix order (for next session; operator confirms)
1. **C1 + C2 + C3** — live capital/safety. C1 (fail-closed sizing) and C3 (ML advisory-only) are code; C2 needs the real-balance ground truth first.
2. **H2 + H3 + H4** — fail-safe defaults + hard caps (v2 shadow default, v1 SL cap, drift fail-closed).
3. **C4 + H1 + H7 + M1 + M2** — edge/calibration; gate on NET-cost backtest (Edge Measurement Core), not code-only.
4. **D1** — fix CLAUDE.md swing_lookback to 5.
Each fix is **backtest-gated where it touches edge** and **review-gated where it touches safety** (risk-ops + operator sign-off; flags stay default-OFF on merge).

---

## Part 3 — Next-Session Execution Plan

### 3a. Ultrareview based on this report
- Run `/code-review ultra` (cloud multi-agent) on the branch carrying the fixes, OR drive a Workflow that re-verifies each CRIT/HIGH finding adversarially before any fix lands. The findings above are the checklist.

### 3b. Workflow orchestration (ultracode)
Candidate workflows (one phase each, operator stays in loop between):
- **Verify-then-fix pipeline:** for each CRIT/HIGH, (1) adversarial re-verify the finding, (2) write a failing test reproducing it, (3) minimal fix, (4) risk-ops + quant re-review. Pipeline per finding (no barrier).
- **Edge-calibration workflow:** NET-cost conf sweep (50 vs 80) + single-factor confluence attribution + OB/OTE/FVG collinearity, on the Edge Measurement Core. (Needs the machine awake — see [[reference_machine_compute_limits]]: Modern Standby freezes long compute; `powercfg /change standby-timeout-ac 0` + lid open.)

### 3c. Integrate `andrej-karpathy-skills` plugin "as if made for this project"
**What it is:** a Claude Code plugin (`.claude-plugin/plugin.json`, skill `karpathy-guidelines/SKILL.md`) of 4 behavioral principles to reduce LLM coding mistakes:
1. **Think Before Coding** — state assumptions, surface tradeoffs, ask, don't guess.
2. **Simplicity First** — minimum code, no speculative abstraction/flexibility.
3. **Surgical Changes** — touch only what's needed; no drive-by refactors; don't delete pre-existing dead code (flag it).
4. **Goal-Driven Execution** — transform tasks into tests-first verifiable goals + plan-with-verify steps.

Path: `c:\Users\utkuc\OneDrive\Utku\CRYPTO\Best_MCP_SKILL\andrej-karpathy-skills-main` (local copy; upstream `forrestchang/andrej-karpathy-skills`, MIT).

**Integration plan (tailor to the trading-bot context — "as if made for efloud-bot"):**
1. **Install** as a Claude Code plugin from the local marketplace (`.claude-plugin/marketplace.json`), or merge `CLAUDE.md` content into the efloud-bot project CLAUDE.md. (Decide plugin-install vs CLAUDE.md-append with operator.)
2. **Map the 4 principles onto efloud-bot's existing hard rules** so they reinforce, not conflict:
   - *Goal-Driven* ↔ the existing **backtest-gate / TDD** discipline (every edge change → failing test or NET-cost backtest gate; this audit's findings are pre-written goals).
   - *Surgical Changes* ↔ the existing **atomic-PR + "never weaken a safety guard" + don't-overwrite-SMC-v2-port** rules.
   - *Think Before Coding* ↔ the existing **risk-ops + operator sign-off before mainnet** + "surface risk tradeoffs."
   - *Simplicity First* ↔ directly addresses the audit's over-counting / split-brain confluence / dual-ATR findings (M2/M3/H1).
3. **Make the plugin "manage the project":** use the karpathy principles as the standing development contract for executing this audit's fixes — every fix PR must show (a) a verify step (test/backtest), (b) a surgical diff (only the finding's lines), (c) stated assumptions/tradeoffs. This is exactly the discipline the audit's findings demand.
4. Verify the integration works (skill loads, principles appear in CLAUDE.md / plugin list) before relying on it.

---

## Artifacts & pointers
- This doc: `docs/handoff/2026-06-20-algorithm-audit-and-next-session-plan.md` (repo).
- Subagent transcripts: explorer map + 4 lens reviews (this session; summarized above — the FULL findings are in Part 1).
- Related: [[smc_sl_tp_redesign_initiative]] (prior SL/TP work, the source of the TP1↔TP2 / SL findings), Edge Measurement Core PR #227 (NET-cost harness for C4/H1/M2), [[reference_machine_compute_limits]] (backtest/sleep limits).
