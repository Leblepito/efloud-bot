# ADR-0005: The TradingView product is an indicator only; no Pine strategy is shipped

**Date**: 2026-11-07 (backfilled; decided 2026-06-13, Wave-2 dropped 2026-06-17)
**Status**: accepted
**Deciders**: operator, claude-code, Gemini, Hermes (consensus)

## Context

The original goal was a Pine indicator plus a backtestable Pine strategy. Gate runs (T-003
GATE_RUN_2/3/4) showed that whenever the strategy produced enough trades, its edge was negative.
An out-of-sample walk-forward of a Wave-2 redesign also failed (pooled OOS PF 1.165 < 1.30).

## Decision

`pine/` ships as an indicator that draws setups and places no orders. `pine/efloud_signals.pine` is
the SMC v2 port and must not be overwritten; product-wave scripts live under `pine/u2algo/`.

## Alternatives Considered

### Alternative 1: Ship the Pine strategy
- **Pros**: users can backtest in TradingView.
- **Cons**: it would publish a strategy whose measured edge is negative.
- **Why not**: it failed the gate repeatedly.

### Alternative 2: Wave-2 full redesign
- **Pros**: a chance at a premium tier.
- **Cons**: large effort, and even the Python engine's edge is modest.
- **Why not**: the OOS falsification failed. It reopens only with new evidence.

## Consequences

### Positive
- No misleading performance claims; the marketing copy stays honest (#221).

### Negative
- There is no backtestable product in TradingView.

### Risks
- The Pine indicator can drift from the Python engine. Mitigation: `pine/PINE_SPEC.md` and the
  `pine` runtime edges in `REGRESSION.md`.

## 2026-11 notu

The decision text is unchanged. The Wave-2 PF in Context (OOS 1.165) and the T-003 gate runs belong
to the engine before the LuxAlgo mode (live since 2026-11-01, `configs/config.phase2_1k.yaml:187-188`);
they do not describe today's engine. Today's product source is the Pine Lab (`pine/lab/*` →
`pine/efloud_lab.pine`; `pine/PINE_SPEC.md` §20); the lab strategy is a parity artefact only and is
not published. The lab baseline parity gate failed on 3/3 symbols
(`docs/pine-lab/2026-11-06-ilk-tur.md:177`).
