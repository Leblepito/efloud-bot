# ADR-0007: Telegram alerting is a separate container that tails the bot log

**Date**: 2026-11-07 (backfilled; alerter since 2026-05-07, TP/SL/orphan rules 2026-11-07)
**Status**: accepted
**Deciders**: operator, claude-code

## Context

Protection alerts (TP placement failed, SL unprotected, orphan position) must reach the operator
even when the bot process is degraded. Adding an alert must not touch mainnet trading code.

## Decision

`ops/alerter/` runs as its own Compose service. It tails the bot log file and polls `/healthz`,
then maps structured log events to rate-limited, deduplicated Telegram messages. A new alert is a
new rule on an existing log event, behind an `EFLOUD_ALERTER_*` flag.

## Alternatives Considered

### Alternative 1: Send Telegram messages in-process from the trading loop
- **Pros**: no log parsing; exact data.
- **Cons**: every new alert changes mainnet code, and a crashed bot cannot report itself.
- **Why not**: it breaks ADR-0003's surgical-change rule and the isolation goal.

## Consequences

### Positive
- Alerts ship and deploy without restarting the bots (`up -d --no-deps alerter`).

### Negative
- The contract is implicit: changing a log message can silently break a rule.

### Risks
- Log-format drift. Mitigation: `REGRESSION.md` declares the alerter ← orchestrator/safety/exchange
  edges, so they always rerun, and contract tests drive the real `OrderManager` path. Today the
  alerter reads only the mid bot's log.
