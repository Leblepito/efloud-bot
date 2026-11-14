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

## 2026-11 notu

The decision text is unchanged. The PF 1.41 / 0.62 measurement above belongs to the June engine;
the live engine has been the v2 LuxAlgo mode since 2026-11-01 (`configs/config.phase2_1k.yaml:187-188`).
The 60-day NET-cost counterfactual on the LuxAlgo engine
(`collab/outputs/claude-code/2026-11-04-lux-gate-counterfactual.md:42-43`): confirmed flow (P1,
engulfing close) −0.30 R/trade, PF 0.65, n=217; unconfirmed limit entry (P2) −0.75 R/trade,
PF 0.27, n=232. The value of confirmation is **contested**: base P1 −0.30 vs P2 −0.75 favours
confirmation, but on touches that never confirmed a limit entry is ≈ break-even (−0.04 R, PF 0.95,
n=407; same file `:54`); the source states there is no evidence confirmation adds value as
implemented (`:22`). Decision unchanged pending a dedicated A/B. The confirmed flow's **absolute
NET edge is negative**; "keeps the edge it actually has" does not hold for the current engine.
