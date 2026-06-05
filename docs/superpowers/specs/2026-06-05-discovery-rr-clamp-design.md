# Discovery TP1 R:R Clamp — Design Spec

**Date:** 2026-06-05
**Status:** Approved (brainstorming) — ready for implementation plan
**Scope:** Single atomic fix. Live mainnet → feature-branch + PR + cautious deploy.

## Problem (confirmed live)

`engine/signals.py` (legacy v1 path, active in prod because config `smc_version=v1`)
has a deterministic defect. When a trigger has **no HTF structural target ≥ `min_rr·risk`
away** in the trade direction, the "price discovery" fallback sets the TP1:

```python
# LONG  (signals.py:575)
tp1 = price + risk_tmp * 1.272
# SHORT (signals.py:617)
tp1 = price - risk_tmp * 1.272
```

This yields `rr1 = 1.27`. The R:R gate immediately rejects it:

```python
# signals.py:662
if rr1 < min_rr:        # 1.27 < 1.5 (repo) / 1.27 < 1.8 (live) → ALWAYS true
    reject_rr += 1
    continue
```

Because `1.272 < min_rr`, **every discovery-mode trigger is rejected 100% of the time.**

### Evidence (live, 2026-06-05, `ssh efloud-bot` docker logs)

- Reject lines: `📉 [SYM] N triggers, 0 signals. Rejects: R:R<1.8 (max seen: 1.27)`
- Over 6h: `max seen` was **exactly 1.27 in all 3805 cases** — zero other values.
  Determinist proof, not market noise.
- Symbols with real structure (broad short move on BTC/SOL/etc.) emitted fine at
  R:R 2.0–7.6 via the structural branches; the ~7/10 symbols without a qualifying
  target stayed stuck in discovery and silently missed every entry.

### Why lowering confluence did not help

The R:R gate (`signals.py:662`) is **downstream of and independent from** the
confluence gate (`signals.py:502`). conf=50 lets the trigger reach the R:R gate,
where it dies on the 1.27 vs min_rr contradiction.

### Config reality

Prod loads `configs/config.phase2_1k.yaml` via `EFLOUD_CONFIG_PATH` (NOT root
`config.yaml`). Live values: `min_rr: 1.8`, `min_confluence: 50` (both committed,
rebuild-safe). Root `config.yaml`'s `min_rr: 1.5` is CLI/test-only.

## Design (Approach A — clamp to min_rr)

Clamp the discovery projection so it lands at exactly `min_rr` (a valid
RR_PROJECTION), mirroring what `engine/smc_v2/tp_calc.py:76` already does
(`tp1 = entry ± min_rr * risk`).

```python
# LONG  (signals.py:575)
tp1 = price + risk_tmp * max(1.272, min_rr)
# SHORT (signals.py:617)
tp1 = price - risk_tmp * max(1.272, min_rr)
```

`max(1.272, min_rr)` keeps the 1.272 fib intent when `min_rr < 1.272` and clamps up
to the gate otherwise. With `min_rr = 1.5`, discovery TP1 lands at exactly 1.5R →
`rr1 = round(1.5, 2) = 1.5`, which passes `1.5 < 1.5 == False`.

`risk_tmp` (signals.py:549/591) and `risk` (signals.py:619) are the same value
(both `abs(price - sl)` with the same `sl`), so `rr1` is exactly `min_rr` — no
float drift into rejection.

### Untouched by design

The other three TP branches already clamp to `min_tp` (= `min_rr·risk`):
- Range-deviation play (`tp1 = e_range.eq`, clamped `if tp1 < min_tp`)
- Ranging-liquidity (`tp1 = min(liquidity_targets ≥ min_tp)`)
- Trending-FVG/liquidity (`tp1 = min(htf_above_targets ≥ min_tp)`)

Only the discovery branch is defective. TP2 discovery logic (2.618·risk,
signals.py:642) is unaffected and stays.

## Config change

`configs/config.phase2_1k.yaml:100` — `min_rr: 1.8 → 1.5` (repo-optimized value;
"Optimized from 1.8" per root config.yaml). Rebuild-safe (committed). Affects all
signals, not just discovery: slightly more frequent fills, higher turnover.
This is `risk:` block → triggers risk-ops review.

## Testing (TDD)

Regression test in `tests/test_signals.py`:
- Construct a trigger scenario with **no HTF structural target** ≥ `min_rr·risk`
  in the trade direction (forces the discovery branch), `min_rr = 1.5`.
- **Before fix:** 0 signals (rejected at rr1 = 1.27).
- **After fix:** 1 signal emitted with `rr1 == 1.5` (== min_rr), TP1 on the
  correct side of entry, TP2 beyond TP1.
- Add a mirror case for the opposite direction.

Run full suite (`pytest`) — must stay green (1139+ tests).

## Deploy

- Feature branch + PR (live mainnet rule).
- `engine/signals.py` = trade logic + `configs/config.phase2_1k.yaml` `risk:` block
  → `efloud-risk-ops-reviewer` gate before merge.
- Cautious deploy on a quiet window; rebuild keeps conf=50 + min_rr=1.5 (committed).
- Post-deploy watch: discovery symbols (ADA/ETH/XRP/DOGE/SOL/BNB/LINK) should now
  emit at rr1 = 1.5 instead of `max seen: 1.27` rejects.

## Out of scope (follow-up)

- **Structural target detection:** `max seen` never exceeds 1.27 on flat symbols →
  worth checking whether HTF swing/EQ/FVG target detection ever surfaces a
  qualifying ≥min_rr target on ranging symbols. Separate investigation after this
  clamp lands.
- Broader signal/risk-path logical-error audit → separate atomic PRs.
