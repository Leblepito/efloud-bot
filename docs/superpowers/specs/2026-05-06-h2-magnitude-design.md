# Epic 6 H2 — Magnitude Push (Risk + Notional Scaling)

**Date:** 2026-05-06
**Status:** Approved (no formal spec-review loop; small focused hypothesis test)
**Parent:** `docs/superpowers/specs/2026-05-05-epic-6-h1-design.md` (Epic 6 framework)
**Baseline:** H1b (`configs/config.phase2_1k_h1b_conf70.yaml`) — see `2026-05-06-h1-confluence-results.md`

> **For agentic workers:** Use `superpowers:executing-plans` for the run. STOP if the variant produces no `portfolio.json`, or DD exceeds 35% (catastrophic), or any engine exception.

---

## 1. Why H2 was re-targeted

The original H2 (LONG signal audit) was based on baseline diagnostics showing LONG net −$31. H1b data overturned that: at conf=70, LONG net +$462, both directions profitable. Original H2 is no longer needed.

**New problem:** H1b returns +4.89% per year, but Binance Lead Trader competitiveness needs ~30-100%/y. Magnitude is the gap. H1b has unused headroom: max DD only 7.17% (well under the 30% Lead Trader-friendly ceiling).

**Hypothesis:** Scaling per-trade risk and notional cap by 3x will scale gross PnL ~3x with DD scaling sub-linearly (portfolio diversification effect should keep DD below 22%).

## 2. Variant: A2

| Knob | H1b (current baseline) | **A2 (this test)** | Multiplier |
|------|------------------------|---------------------|------------|
| `risk.risk_per_trade_pct` | 1.0% ($20/trade) | **2.0%** ($40/trade) | 2× |
| `safety.max_position_notional_pct` | 2.0% ($200 notional) | **6.0%** ($600 notional) | 3× |
| `risk.min_confluence` | 70 | 70 (unchanged) | — |
| Leverage | 5x (unchanged) | 5x (unchanged) | — |
| Symbols | 10 (unchanged) | 10 (unchanged) | — |

Effective per-trade margin: $40/trade margin → 10 simultaneous = $400 active margin (was $200 in H1b). Wallet utilisation rises from ~10% → ~20% peak.

## 3. Why this combination

The two parameters interact. `risk_per_trade_pct` controls SL distance × position size (so trades respect a hard $ risk per trade). `max_position_notional_pct` caps total notional regardless of risk math. At H1b, the notional cap was binding more often than risk cap (most trades hit the $200 notional ceiling, not the $20 risk ceiling). Raising both lifts both ceilings together; raising only one is asymmetric.

A2's 3x notional + 2x risk is intentionally asymmetric — risk per trade goes up only 2x to keep the per-position SL hit cost from dominating, while notional 3x lets profitable signals deploy more capital. This is a more conservative scaling than 3x/3x (which would be 3.33% wallet risk per trade — uncomfortably high).

## 4. Acceptance criteria

A2 succeeds if **all** of:

| Metric | A2 success threshold | H1b reference |
|--------|----------------------|---------------|
| Total return | > 12% | 4.89% |
| Max DD | < 25% | 7.17% |
| Profit factor | > 1.5 | 1.95 |
| Win rate | > 50% | 54.7% |
| Sharpe | > 0.3 | 0.27 |
| Trade count | > 100 (statistical) | 680 |

If A2 succeeds → A2 is new baseline; advance to H3 (per-symbol whitelist) or A3 (further scaling).

If A2 only partially succeeds (e.g., return > 12% but DD > 25%) → record the trade-off curve point; consider trying a less aggressive variant (e.g., risk 1.5%, notional 4%).

If A2 regresses (return < H1b OR DD > 30%) → magnitude push hits non-linear penalty; pivot to H4 (whitelist) or R:R audit.

## 5. Failure modes — STOP

- Engine exception or OOM
- `portfolio.json` not written within 5 min of process exit
- Max DD ≥ 35% during run (catastrophic — the strategy isn't risk-isolated enough for further scaling)

## 6. Execution

**When:** dispatched only AFTER H1c (currently running) finishes — to avoid CPU contention.

**Command (when bf17amo94 finishes):**
```
cd C:/Users/utkuc/Downloads/efloud-bot-backtest
python -m scripts.run_phase_a --config configs/config.phase2_1k_h2a2_risk2_notional6.yaml
```

**Expected runtime:** ~5h (similar to H1b — same trade count expected, just different sizing).

## 7. Deliverables

- `configs/config.phase2_1k_h2a2_risk2_notional6.yaml` (committed to `feature/backtest-subsystem`)
- `reports/backtests/phase_a_<date>_phase2_1k_h2a2_risk2_notional6_<id>/` — full output
- `docs/superpowers/specs/2026-05-07-h2-a2-magnitude-results.md` — comparison vs H1b + decision (committed to master)

## 8. Out of scope for A2

- Multiple variants (A1, A3) — start with A2 mid-point, only sweep if results are unclear
- Whitelist (H4 territory) — orthogonal, runs after A2
- Strategy code changes — config-only test
- Phase B reconcile — still blocked on trade-timestamp bug
