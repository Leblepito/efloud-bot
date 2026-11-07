# ADR-0004: SMC v2 goes live only through an explicit symbol list; a missing shadow key means shadow

**Date**: 2026-11-07 (backfilled; v2 went live by operator approval 2026-07-07, fail-safe default from audit H2)
**Status**: accepted
**Deciders**: operator, claude-code

## Context

SMC v2 (`engine/smc_v2/`) replaced v1 signal generation on the live bot. Audit H2 found two
problems: the shadow switch defaulted to *live* when the key was absent, and
`smc_v2_symbols: ["*"]` made the whitelist a no-op.

## Decision

v2 places real orders only when all three conditions hold: `smc_version: v2`, the symbol is in an
explicit `smc_v2_symbols` list, and `smc_v2_shadow` is `false`. A missing `smc_v2_shadow` is
treated as `true` (shadow: log only, no orders). The v1 entry path is muted on symbols where v2 is
active.

## Alternatives Considered

### Alternative 1: Global v2 switch (`["*"]`)
- **Pros**: one setting.
- **Cons**: no phased rollout; one typo puts every symbol live.
- **Why not**: rejected by audit H2.

### Alternative 2: v1 and v2 side by side on the same symbol
- **Pros**: direct comparison.
- **Cons**: double exposure and conflicting orders.
- **Why not**: the shadow log already gives the comparison without placing orders.

## Consequences

### Positive
- Rollout is per symbol and reversible by config, and a dropped key fails safe.

### Negative
- Two engines to maintain until v1 is retired.

### Risks
- A config edit could drop the list. Mitigation: `TEST-AUDIT-H2` in `TESTS.md`.
