# Bull-Aware Signal Trigger — Design Spec

**Date:** 2026-05-08
**Status:** Approved direction (Approach B, user-selected) — pending implementation plan
**Owner:** uAlgoTrade Project

## Context

### Problem

`aggressive_v1` deployed 2026-05-08 ~02:30 UTC. After 27+ hours live, **0 trades**. Live diagnostic logging (PR #10 follow-up, commit `79589f4`) shows the cause is structural, not market-temporary:

- Only 1 of 10 symbols (FIL/USDT) emits any signal log over a 5-minute window — others early-skip due to HTF bias UNDEF or no entry-TF CHoCH.
- The single active symbol's confluence is **stuck at 60** (98% of 323 reject samples in 24h).
- 60 = `HTF bias 25 + MTF CHoCH 20 + zone 5 + one extra layer 10`. Floor (top tier) is 70 → reject.

Root cause is two structural choices in [engine/signals.py](../../engine/signals.py):

1. **Single-trigger restriction** (line 194): `if brk.kind != "CHoCH": continue` — only CHoCH (trend-reversal) breaks trigger entries. **All BOS (trend-continuation) breaks are discarded**, regardless of confluence quality.
2. **Tight floor** for current market regime: `min_confluence=70` global, 80 mid-tier, 85 XRP.

### Why this matters now

In a bull market, the typical structural sequence on entry TF is:

```
CHoCH(BULL) → BOS → BOS → BOS → ... → CHoCH(BEAR)
```

After the first CHoCH, the trend continues via BOS pullback-then-break patterns — **possibly dozens of high-quality entry opportunities per symbol per uptrend**. The bot ignores all of them. This explains the dramatic gap between backtest expectations (Phase A 2.0: 364 trades / 365 days) and live activity (0/27h).

### Goal

Adapt the signal trigger so it captures both phases of an SMC trend:

- **Phase 1 (initial reversal):** CHoCH — already supported, keep unchanged.
- **Phase 2 (trend continuation):** BOS — currently discarded, **enable as a valid trigger** with appropriate quality controls.

Combined with a recalibrated confluence floor that matches the user's stated minimum-evidence rule ("ChoCH +25 + 2 SMC layers"), the bot should:

- Take 3-5 trades/day in trending regimes (vs 0 currently).
- Stay disciplined in chop (per-symbol dedup + confluence quality bar).
- Not require any change to the position lifecycle, risk gates, or order placement.

## Non-goals

- **No regime-adaptive thresholds.** Approach C (regime-driven confluence) was considered and rejected by the user — keeps complexity manageable for this iteration. May be revisited after 1-week observation.
- **No new SMC primitives.** All structural detections (CHoCH, BOS, FVG, OB, OTE, SFP) already exist in [engine/smc.py](../../engine/smc.py). This is a filter + threshold change.
- **No changes to risk guards.** Max 5 positions, 2% risk/trade, 10% notional, daily-loss/weekly-DD breakers all unchanged.
- **No changes to TP/SL placement or reconcile flow.** The change happens entirely upstream of order creation.
- **No backend API or frontend changes.** Pure engine/config update.

## Approach (B — Bull-aware)

### Key changes

1. **Trigger expansion** ([engine/signals.py:194](../../engine/signals.py#L194)):
   ```python
   # Before
   if brk.kind != "CHoCH" or brk.direction != htf_bias: continue
   # After
   if brk.kind not in ("CHoCH", "BOS") or brk.direction != htf_bias: continue
   ```

2. **BOS-specific recency** (new; immediately after the trigger filter):
   ```python
   # CHoCH: 40 bars (10h on 15m) — rare event, allow longer lookback.
   # BOS:   20 bars (5h on 15m)  — frequent event, tighter freshness reduces stale signals.
   bos_recency = recency_bars // 2  # 40 → 20
   if brk.kind == "BOS" and brk.idx < last_bar_idx - bos_recency: continue
   ```

3. **Confluence floor recalibration** ([configs/config.aggressive_v1.yaml](../../../configs/config.aggressive_v1.yaml)):
   | Tier | Old | New | Rationale |
   |---|---:|---:|---|
   | Top (ETH/SOL/FIL/RENDER) | 70 | **55** | ChoCH(25) + MTF(20) + 1 layer(10) — user's "2 SMC layer" minimum |
   | Mid (BTC/SUI/ADA/OP/LTC) | 80 | **65** | One additional layer over top tier |
   | Selective (XRP) | 85 | **75** | Weak Phase A perf; tighten the gap modestly |

### Why these specific numbers

Confluence-bucket reachability table (live observation: 60-bucket dominant; 65 occasionally; 70+ rare):

| Floor | Reject rate (FIL 24h sample) | Estimated trades/day (10 sym) |
|---:|---:|---:|
| 70 | 100% | 0 (live evidence) |
| 65 | ~98% | <1 |
| **60** | ~98% (CHoCH-only) | 1-2 |
| **55** | ~50% (CHoCH+BOS) | 3-5 (target) |
| 50 | ~30% | 5-8 (too aggressive — risks low-quality signals) |

55 is the smallest floor that satisfies the user's "2 SMC layers minimum" constraint without slipping into 1-layer territory.

### Why BOS recency = CHoCH/2

Live observation: in trending periods, BOS events occur every 1-3 bars on entry TF. A 40-bar lookback would let the bot enter on stale BOS signals (entry placed bars after the actual break, when price has often retraced). Halving to 20 bars (5h on 15m) keeps fills near the breakout point.

CHoCH stays at 40 bars because it's a rare structural event — losing it to a tight recency filter would re-create the current zero-trade problem.

### Risks & mitigations

| Risk | Mitigation |
|---|---|
| BOS spam (multiple BOS per uptrend on same symbol) | Existing per-symbol position dedup ([safe_orchestrator.py:368](../../engine/safe_orchestrator.py#L368)): `_processed_signals[(symbol, direction, entry)]` skips duplicates within 1h. Max 5 open positions enforced. |
| Lower floor lets through marginal setups | 55 still requires CHoCH(25) + MTF onay(20) + at least 1 SMC layer — same evidence bar Efloud philosophy targets, just decoupled from "trend reversal only" |
| Backtest gap (Phase A 2.0 was CHoCH-only with floor 70) | This is a deliberate live-evidence-driven recalibration. Phase B reconcile (1-week post-deploy) will compare new live distribution to backtest, surface actual edge. Production rollback target: revert to `min_confluence=70` and CHoCH-only filter. |
| Fast-trending markets opening 5+ pos in minutes | `max_open_positions=5` enforced gate already blocks the 6th. Daily-loss 10% / 5×SL hits trip the breaker if quality breaks down. |

## Files to modify

- [engine/signals.py](../../engine/signals.py) — trigger filter (line 194) + BOS recency check (new ~3 lines).
- [configs/config.aggressive_v1.yaml](../../../configs/config.aggressive_v1.yaml) — `min_confluence` (line 98) + `symbol_confluence_overrides` (lines 108-114).
- [tests/test_signals.py](../../../tests/test_signals.py) — add tests for BOS trigger acceptance + BOS recency rejection.
- New: short YAML/markdown note in `configs/` documenting the change rationale (optional, for future operators).

## Test plan

### Unit tests (TDD)

1. **BOS in HTF direction within recency → accepted as candidate.** Use existing mock-engine pattern in `tests/test_signals.py::TestRejectSummaryLog`. Construct a BOS break in HTF direction at idx within `last_bar_idx - 20` window; assert it goes through to confluence scoring.
2. **BOS in HTF direction past recency → rejected with new "stale BOS" reason.** Same setup, idx 25 bars old. Assert reject log mentions "stale".
3. **CHoCH recency unchanged at 40 bars.** Regression test — current behavior must not change.
4. **Counter-direction BOS still rejected.** Assert that BOS against HTF bias is still discarded (existing `brk.direction != htf_bias` filter intact).
5. **Confluence floor 55 with BOS + 2 SMC layers passes.** Integration: BOS + MTF + OB → score=55, threshold=55, expect signal generated.

### Live verify (post-deploy)

- New log format already in place (`📉 [SYMBOL] N CHoCH/BOS, X signals. ...`) — extend slightly so the log emits the trigger kind. Trace BOS-driven entries in 24h sample.
- Compare per-symbol trade rate vs backtest baseline (ETH was ~89/365 = 4-day cadence; expect similar or slightly higher in trending periods).
- Watch for breaker trips: if daily-loss 10% hits within 2-3 days, the recalibration was too aggressive — rollback path documented.

## Rollback

Single-commit revert restores prior behavior:

```bash
git revert <merge-sha>
ssh efloud@... "cd /opt/efloud-bot && git pull && bash deploy/deploy.sh"
```

No data migration. No config schema change. Backtest engine unaffected (per-symbol overrides are backwards-compatible per `engine/signals.py:resolve_min_confluence`).

## Open questions for user review

None blocking — all specifics derive from the user's selected approach (B) plus the documented "ChoCH+25 + 2 layers" minimum-evidence rule. Implementation can proceed once spec is approved.

## Follow-up (post-1-week observation)

- Phase B reconcile: feed 1 week of live `[SYMBOL] BOS/CHoCH max=X hist=Y×N` logs into `backtest/compare_live.py`. Validate live distribution matches simulated.
- If live performance significantly diverges from backtest (DD spike, win-rate drop), evaluate Approach C (regime-adaptive thresholds) as next iteration.
- Bonus: per-symbol BOS frequency cap (e.g., max 2 BOS-triggered entries per symbol per 24h) if pyramid-like entry behavior emerges.
