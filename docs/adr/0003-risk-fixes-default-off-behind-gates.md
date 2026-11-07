# ADR-0003: Risk and edge changes ship default-OFF or fail-closed; activation needs the backtest gate and operator sign-off

**Date**: 2026-11-07 (backfilled; adopted with the 2026-06-20 algorithm audit and remediation PR #232)
**Status**: accepted
**Deciders**: operator, claude-code (Karpathy development contract in `CLAUDE.md`)

## Context

The bot trades real money. Audit fixes (C1–C4, H1–H7, M1–M5) and bug-hunt fixes change signal,
sizing or exit behaviour, and several "obvious" improvements failed a NET-cost backtest
(ADR-0005, ADR-0009). Merging code and changing live behaviour are separate risks.

## Decision

A change touching `engine/safety/`, `engine/risk/`, `engine/lifecycle.py`, `exchange/` or the config
`safety:`/`risk:` blocks lands behind a flag that defaults to the old behaviour, or fails closed
(rejects) when its input is missing. Turning it on in `configs/config.phase2_1k.yaml` is a separate
step. It needs a passing NET-cost backtest (for edge changes) and operator sign-off.

## Alternatives Considered

### Alternative 1: Ship fixes directly live
- **Pros**: faster.
- **Cons**: a regression goes straight to mainnet, and edge changes go unmeasured.
- **Why not**: incident history (2026-05-14 bare positions, breaker double count) shows the cost.

### Alternative 2: Long-lived branches until fully validated
- **Pros**: master stays pristine.
- **Cons**: drift and painful merges with three models committing in parallel.
- **Why not**: flags let validated code merge early while behaviour stays unchanged.

## Consequences

### Positive
- Merges are reversible by config, and tests cover both flag states.

### Negative
- Some fixes stay dormant. H7 and M1 are `generate_signals` parameters that are not wired from
  config at all (`TESTS.md` §4.1).

### Risks
- Flag sprawl. Mitigation: `TESTS.md` records for each protection whether it is active in prod.
