# ADR-0006: Production state is file-based in named volumes; Postgres is optional

**Date**: 2026-11-07 (backfilled; prod has run DB-less since at least 2026-06-01)
**Status**: accepted
**Deciders**: operator, claude-code

## Context

The bot must keep trading through database outages, and its critical state (breaker, positions,
trade journal) is small. `backend/db.py` initialises lazily: when `DATABASE_URL` is unset or the
database is unreachable, the pool is `None` and the bot runs without persistence.

## Decision

The authoritative live state is files in the bot's state volume (for example `breaker.json` and
`trade_journal.jsonl` under `state_1k/`). The Postgres mirror and migrations are optional extras
and are never on the trading critical path.

## Alternatives Considered

### Alternative 1: Postgres as the source of truth
- **Pros**: queries, multi-instance isolation (`bot_id`, migration 012).
- **Cons**: a database outage becomes a trading outage, and the VPS gains one more stateful service.
- **Why not**: at this scale the availability cost outweighs the query convenience.

## Consequences

### Positive
- Fewer moving parts, and the sidecars read the same files (ADR-0007).

### Negative
- Analytics read JSONL files, and DB-backed features (the migration 010 mirror) are inert in prod.

### Risks
- File corruption on crash. Mitigation: atomic writes (`tests/test_persist_crash_safety.py`).
