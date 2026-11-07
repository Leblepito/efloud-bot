# ADR-0002: The LLM layer is advisory only and can never block or change a trade

**Date**: 2026-11-07 (backfilled; agent team #112 on 2026-06-01, observation mode confirmed by the operator 2026-11-03)
**Status**: accepted
**Deciders**: operator, claude-code

## Context

`engine/agents/` adds sentiment, structure validation, a role-based agent team and Kronos
forecasts. LLM providers have outages, rate limits, latency spikes and non-deterministic output,
and none of them has a measured edge on this strategy yet.

## Decision

Every LLM call is advisory and fail-safe: on any error the deterministic path continues. The agent
team runs in observation mode (`agent_team.gating: false`). Its verdict is written to the journal
for later edge measurement and never gates an order. The provider is a config/env lever
(`llm.provider`, `LLM_PROVIDER`), not code.

## Alternatives Considered

### Alternative 1: LLM veto on entries
- **Pros**: could filter bad setups.
- **Cons**: an unmeasured filter on live capital; an outage would silently stop trading.
- **Why not**: it first needs a recorded shadow period with measured edge, plus operator sign-off.

### Alternative 2: No LLM layer
- **Pros**: simplest.
- **Cons**: no data to ever evaluate whether the agents help.
- **Why not**: observation mode gathers that data at zero trading risk.

## Consequences

### Positive
- An LLM outage cannot halt or distort trading, and providers can be swapped freely.

### Negative
- LLM spend per opened trade, with no trading benefit until gating is approved.

### Risks
- A future change could quietly make a verdict gating. Mitigation: `gating` defaults to false, and
  flipping it requires a new ADR that supersedes this one.

## Known deviation (found and resolved 2026-11-07)

The LLM macro sentiment used to add ±5 to the confluence score before the `min_confluence` gate.
In prod it was dormant (the writer and the engine used different state directories). Resolved by
operator decision 1 (spec 2026-11-07): sentiment is telemetry only (`sig.meta["macro_sentiment"]`)
and the writer, engine and dashboard share the bot's `state_dir`.
