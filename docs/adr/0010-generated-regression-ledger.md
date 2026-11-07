# ADR-0010: The module regression ledger is generated from an import scan and checked in CI

**Date**: 2026-11-07
**Status**: accepted
**Deciders**: claude-code (backlog T-20261106-04 item 3, operator-approved backlog)

## Context

"Changing A broke B" happens across the engine, exchange, alerter and backend. A hand-written
dependency list goes stale as soon as an import changes, and the alerter's dependence on log lines
does not show up in any import.

## Decision

`scripts/regression_ledger.py` generates `REGRESSION.md` from a module table, an AST import scan of
tracked files, and declared runtime edges that each carry a `git grep` evidence command.
`run --base origin/master` executes the affected tests, and CI fails if the committed ledger is stale.

## Alternatives Considered

### Alternative 1: Hand-maintained `REGRESSION.md`
- **Pros**: no tooling.
- **Cons**: drifts silently.
- **Why not**: unverified edges are exactly what the ledger exists to prevent.

### Alternative 2: Always run the full suite
- **Pros**: simple and complete.
- **Cons**: about 6 minutes locally, with no attribution of which module broke which.
- **Why not**: CI still runs the full suite; the ledger is for fast, attributable local runs.

## Consequences

### Positive
- Propagation is reproducible, and runtime edges are always included.

### Negative
- Adding a test file means rerunning `python scripts/regression_ledger.py render`; the CI failure
  message says so.

### Risks
- The import scan misses dynamic imports. Mitigation: tests are also matched by string literals
  and tokens, and runtime edges are declared explicitly.
