# M2 — Confluence component over-counting / collinearity (2026-07-08)

**Audit finding:** `docs/handoff/2026-06-20-algorithm-audit-and-next-session-plan.md`
M2 — "OB triple-count (+10/+5 near-swing/+3 at-EQ = +18 for ONE concept,
confluence.py:32-37); OB/OTE/FVG fire together on 'pullback into discount
POI' (partial triple double-count); daily +5 echoes HTF +25. Effective DOF
~3, not 8 → conf=80 may fit the dominant in-sample pattern rather than
independent edge. Direction: single-factor NET attribution + 8-component
correlation matrix."

## What this is

Ran the real production `engine.signals.generate_signals` (unmodified, same
code path as live) with `min_confluence=0` so every aligned CHoCH/BOS trigger
is captured regardless of threshold — this measures the RAW component
firing/co-occurrence pattern the scoring formula is built on. Data: full
locally cached history (~2025-05-15 → 2026-05-14) across all 10 symbols
used in the earlier phase-A validation runs. **4,633 total signals.**
Tool: `scripts/m2_confluence_collinearity.py` (checked into the repo).

This covers the **correlation-matrix** half of M2's stated direction. The
**single-factor NET PnL attribution** half (does component X alone predict
edge) needs a full walk-forward backtest per component subset — this sandbox
hit the same compute ceiling documented in
`docs/results/2026-07-08-c4-net-cost-confluence-sweep.md` (2 CPU cores, ~45s
per command, no persistent background jobs), so that half is **not** done
here and is left for a run on unconstrained hardware.

## Marginal firing rates (n=4,633)

| Component | Bonus | Firing rate |
|---|---|---|
| MTF_CHoCH | +20 | **100.0%** |
| correct_zone | +5 | 68.9% |
| SFP | +10 | 58.4% |
| OB | +10 | 36.2% |
| OB_near_swing | +5 | 33.3% |
| HTF_FVG | +15 | 15.0% |
| OB_at_EQ | +3 | 2.9% |
| OTE | +10 | **0.2%** (11/4633) |
| deviation | +5 | **0.0%** (0/4633) |

## Phi-coefficient (binary correlation) — pairs flagged at \|phi\| > 0.3

| Pair | phi |
|---|---|
| OB ↔ OB_near_swing | **0.937** |
| HTF_FVG ↔ OB | 0.342 |

All other pairs, including SFP and correct_zone against everything else, were
below 0.3 (mostly under 0.1) — these two appear genuinely close to
independent of the OB/FVG cluster in this sample.

## Interpretation

**Confirms the audit's named collinearity precisely.** OB and OB_near_swing
co-fire 93.7% correlated — structurally expected (near_swing is only
meaningful when OB is already true; empirically 1541/1677 = 91.9% of OB
signals are also near_swing) — so the +10/+5 pair is, in practice, almost
always scored together as one event, not two. HTF_FVG/OB at phi=0.34 matches
the audit's "partial triple double-count" note (pullback-into-POI setups
tend to have both an FVG and an OB nearby).

**Two findings beyond what the audit named, both more concerning than the
named collinearity:**

1. **MTF_CHoCH fires on 100% of signals (4633/4633).** A component with zero
   variance provides zero discriminative power — the +20 bonus is not
   "confirming" anything in this sample, it's a constant added to every
   score. This is a bigger contributor to "effective DOF < 8" than the named
   OB triple-count: it's not double-counting one concept, it's a supposedly
   independent confluence factor that never actually varies.
2. **`deviation` (Range deviation, +5) fired on 0/4633 signals.** Dead
   weight — not wrong, just never contributes across a full year × 10
   symbols. **OTE fired on only 11/4633 (0.2%)** — likely tightened further
   by this session's H6 fix (rejects OTE bands built from mismatched swing
   legs), but was already rare before that; either way its +10 bonus is
   contributing almost nothing to the live score distribution.

Combined, of the 9 named components, only 5 (correct_zone, SFP, OB,
OB_near_swing as one event, HTF_FVG) show real, varying, only-mildly-
correlated signal in this sample — closer to the audit's "effective DOF ~3"
estimate than to 8, and for a different reason (near-constant / near-dead
components) than the audit's named cause (double-counting).

## Recommendation

This is evidence for the operator to weigh, not a scoring-formula change
applied here — `engine/confluence.py`'s weights feed the live entry gate, so
any change needs the NET single-factor backtest (not yet run, see above) plus
review-gated sign-off per the standing dev-contract (CLAUDE.md — surgical
changes, backtest-gated, default-OFF until validated). Candidates worth a
NET-cost ablation study before touching weights:
- Collapse OB (+10) / OB_near_swing (+5) into a single bonus, or make
  near_swing/at_EQ sub-bonuses cost-neutral refinements rather than additive.
- Investigate why MTF_CHoCH is a constant in this dataset (a mtf_chochs[-5]
  window that's too lenient? a symbol-set/period bias?) before continuing to
  price it as a +20 independent confirmation.
- Decide whether OTE (+10) and deviation (+5) are worth keeping as-is given
  how rarely they fire, versus loosening their trigger conditions or
  removing them from the additive score entirely.
