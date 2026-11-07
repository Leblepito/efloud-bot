# ADR-0009: Entries require confirmation; immediate market entry on signal is rejected

**Date**: 2026-11-07 (backfilled; decided 2026-06-15 after the entry-slippage backtest)
**Status**: accepted
**Deciders**: operator, claude-code, Gemini (consensus)

## Context

Entry slippage looked costly, and the hypothesis was that dropping confirmation (entering at market
on the signal) would help. The backtest gate compared the two modes: with confirmation PF 1.41 over
685 trades, without it PF 0.62 over 26 trades.

## Decision

`require_confirmation` stays `true` (the code default in `engine/safe_orchestrator.py`). Both a
mainnet flip and a testnet shadow of the no-confirmation mode were rejected.

## Alternatives Considered

### Alternative 1: Market entry on signal
- **Pros**: more fills and fewer missed moves.
- **Cons**: destroys the measured edge.
- **Why not**: it failed the backtest gate.

## Consequences

### Positive
- The strategy keeps the edge it actually has.

### Negative
- Slippage cannot be measured in the backtest (fill = signal price). Only a testnet shadow could
  measure it.

### Risks
- Someone sets the key to `false` for "more trades". Mitigation: this ADR, plus ADR-0003.
