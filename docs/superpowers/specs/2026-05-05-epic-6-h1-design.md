# Epic 6 — Strategy Redesign — H1 Design (Trade Frequency Reduction)

**Date:** 2026-05-05
**Status:** Approved (no formal spec-review loop; small focused hypothesis test)
**Parent:** `docs/superpowers/specs/2026-05-05-efloud-roadmap.md`
**Triggered by:** `docs/superpowers/specs/2026-05-05-backtest-validation-results.md` (ITERATE)

> **For agentic workers:** Use `superpowers:executing-plans` for the run loop; `superpowers:verification-before-completion` before claiming a hypothesis result is valid. STOP and surface to owner if any variant fails to produce `portfolio.json`.

---

## 1. Epic 6 Framework — Hypothesis-driven iteration loop

Each hypothesis follows this loop:

```
1. Create variant config → configs/config.phase2_1k_h{N}_{tag}.yaml
2. Run scripts/run_phase_a.py --config <variant>
3. Collect reports/backtests/phase_a_<date>_h{N}_<tag>_<id>/ output
4. Append to comparison table (variants × metrics)
5. DECISION:
   - All GO thresholds met → variant becomes new baseline; advance to next hypothesis
   - Improvement but threshold-fail → hold for combination, advance
   - Regression → hypothesis dead, advance
6. All hypotheses exhausted, still failing → switch to Yaklaşım B (paradigm shift)
```

Driver `scripts/run_phase_a.py` currently hardcodes `CONFIG_PATH`. **Required preliminary patch:** add `--config` argparse argument so the same driver runs every variant. This patch is reused for all of Epic 6's hypotheses.

## 2. Hypothesis catalog (priority order)

From Phase A diagnostics:

| # | Hypothesis | Mechanism | Priority |
|---|-----------|-----------|----------|
| **H1** | Trade frequency too high (1709 in 1y) | Raise `min_confluence` so fewer signals fire | **first** — fee burn is the largest single contributor (≈$1,136 of −$875 net) |
| H2 | LONG signal logic broken (LONG net −$31, SHORT net +$292) | Code audit of LONG-vs-SHORT generators; possibly LONG-disable variant | second |
| H3 | SL-heavy exits (59.6%) | R:R re-tune (wider SL, stricter entry) | third |
| H4 | 9/10 symbols negative; only TRX +0.16% | Per-symbol whitelist for known-survivors | tactical fallback |

H2-H4 each get their own design doc when reached.

## 3. H1 — Confluence threshold sweep

### 3.1 Why H1 first

The largest financial leak is fee/funding/slippage burn at ~$1,136 vs gross PnL +$261 (4×). If trade count is halved while gross PnL/trade stays roughly constant, net moves from −$875 to ≈+$130. This is mathematically the highest-leverage single intervention.

### 3.2 Variants to test

| Variant | `min_confluence` | Expected trades (rough) | Spectrum |
|---------|------------------|-------------------------|----------|
| baseline (`phase2_1k`) | 50 | 1709 (measured) | current |
| `h1a_conf60` | 60 | ~1100-1300 | mild tightening (pre-2026 default) |
| `h1b_conf70` | 70 | ~600-900 | medium tightening |
| `h1c_conf80` | 80 | ~200-400 | aggressive tightening |

Three points (not a full grid) chosen to reveal the **shape** of the dependency, not just one data point. If non-monotonic, sweep result still informs.

### 3.3 Acceptance criteria

H1 succeeds if **at least one** of:
- Any variant produces `total_return_pct > 0%` → that variant becomes new baseline; advance to H2
- Best variant ≤ baseline but materially less negative (e.g., baseline −43.75% vs variant −10%) → hold for combination, advance to H2
- All variants regress vs baseline → H1 dead, advance to H2

### 3.4 Failure modes — STOP

- A variant fails to produce `portfolio.json` (engine error)
- A variant produces 0 trades (signal threshold too tight to fire — note and continue, but record)
- Driver patch breaks baseline reproduction (run baseline once with the patch to verify identical metrics to `phase_a_2026-05-05_2de8bd`)

### 3.5 Execution strategy

Sequential, background:

```
run_phase_a --config h1a_conf60.yaml  # ~3.5h
run_phase_a --config h1b_conf70.yaml  # ~3.5h
run_phase_a --config h1c_conf80.yaml  # ~2-3h (fewer signals → faster)
```

Total wall-clock: ~10 hours. Started in evening, results available next morning.

### 3.6 Deliverables

- `scripts/run_phase_a.py` patched with `--config` arg + variant tag in output dir name (committed to `feature/backtest-subsystem`)
- `configs/config.phase2_1k_h1a_conf60.yaml`, `_h1b_conf70.yaml`, `_h1c_conf80.yaml`
- 3 × `reports/backtests/phase_a_<date>_h1{a,b,c}_*/`
- `docs/superpowers/specs/2026-05-06-h1-confluence-results.md` — comparison table + decision (committed to master)

## 4. What happens after H1

| H1 outcome | Next |
|-----------|------|
| Any variant clears all GO thresholds | New baseline locked; H2 brainstorming under new variant |
| Improvement but no GO | New best variant becomes interim baseline; H2 brainstorming |
| All variants regress | H1 dead; H2 brainstorming starts under original baseline |

Trade-timestamp wall-clock bug (validation-results §6) is **deferred to H2** — H1 doesn't need bar-time data, but H2 (LONG audit) benefits from regime tagging which needs bar-time.

## 5. Out of scope for H1

- Changing any other config parameter (R:R, SL/TP, ATR filters, ADX thresholds)
- Code changes to engine (only the `run_phase_a.py` driver patch is allowed)
- Combining H1 with other hypotheses — combinations are tested only after individual hypotheses are evaluated
- Phase B reconcile — separate Epic, blocked on timestamp bug fix
