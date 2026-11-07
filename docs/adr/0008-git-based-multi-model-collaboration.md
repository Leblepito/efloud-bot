# ADR-0008: Multi-model collaboration goes through git (`collab/`), PR-only

**Date**: 2026-11-07 (backfilled; adopted 2026-11-04, #266/#268)
**Status**: accepted
**Deciders**: operator, claude-code, Hermes, Abacus

## Context

Three AI models (claude-code, Hermes, Abacus) work on the same public repo from different
machines. Earlier coordination through ad-hoc handoff files caused duplicated work and overwritten
changes in shared checkouts.

## Decision

Coordination lives in `collab/` on master: task files (`collab/tasks/open/`), one append-only log
per model (`collab/log/<model>.md`), `STATUS.md` and `SHARED.md`. Every change lands through a PR
from a `collab/<model>/<task-id>-slug` branch. The log line `- VPS:` uses a fixed vocabulary that
`tests/collab/test_collab_layout.py` enforces.

## Alternatives Considered

### Alternative 1: External tracker only (Issues/Linear)
- **Pros**: real tooling.
- **Cons**: not every model has API access, and the context does not travel with the code.
- **Why not**: git is the one channel every model already uses.

### Alternative 2: Shared working directory
- **Pros**: instant.
- **Cons**: stashes and branch switches clobber other sessions' WIP.
- **Why not**: it caused real incidents; worktrees plus PRs replace it.

## Consequences

### Positive
- Every change is reviewed and auditable, and the logs union-merge cleanly.

### Negative
- Ceremony: a task file and a log entry for each PR.

### Risks
- Untrusted text lands in a public repo. Mitigation: exploit-level detail goes only to the
  private store.
