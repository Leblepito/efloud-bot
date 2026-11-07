# ADR-0001: Trading bots run on one VPS with Docker Compose; Railway hosts only the marketing site

**Date**: 2026-11-07 (backfilled; VPS deployment since the 2026-05-15 rebuild, Railway bot services removed 2026-11-07)
**Status**: accepted
**Deciders**: operator, claude-code

## Context

The bots trade on Binance mainnet and need a stable egress IP, persistent state volumes, log files
that the sidecars (alerter, overseer, routines) can read, and manual start (`AUTOSTART=0`). Railway
copies of the bot (`bot.`/`v2.`/`scalp.u2algo.com`) duplicated the deployment and left orphaned DNS
records once they were no longer used.

## Decision

All bot instances and their sidecars run on a single Hetzner VPS from `docker-compose.prod.yml`
behind Caddy. Railway runs only `u2algo-site` (root dir `/u2algo-site`).

## Alternatives Considered

### Alternative 1: Bots on Railway
- **Pros**: push-to-deploy, managed TLS.
- **Cons**: no shared log volume for the sidecars, an ephemeral filesystem for file state, a
  second copy of mainnet credentials, and extra attack surface.
- **Why not**: the services were deleted and their CNAMEs removed on 2026-11-07.

### Alternative 2: Kubernetes / managed containers
- **Pros**: self-healing, rolling deploys.
- **Cons**: operational weight far beyond three bots plus sidecars.
- **Why not**: `autoheal` + Compose covers restart-on-unhealthy.

## Consequences

### Positive
- Credentials and state live in one place; sidecars read the bot log directly (ADR-0007).
- Single-service deploys (`up -d --no-deps <svc>`) leave the bots untouched.

### Negative
- The VPS is a single point of failure (incident 2026-05-15: the VPS was wiped and redeployed).

### Risks
- Losing the host loses file state (ADR-0006). Mitigation: state lives in named volumes, and the
  redeploy path was proven on 2026-05-15.
