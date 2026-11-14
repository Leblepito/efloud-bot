# ADR-0011: Edge GO criterion — offline NET-cost gate first, forward shadow as a sanity check, staged go-live

**Date**: 2026-11-14
**Status**: accepted (2026-11-14)
**Deciders**: operator (approved decision K6 of the ECC revision spec), claude-code (proposal)

> **Operatör notu (TR):** Bir setup/edge değişikliği canlı emre ancak bu ADR'deki üç adımı sırayla geçerse
> gider: (1) offline NET-cost kapısı, (2) forward gölge sağlaması, (3) $25 → $50 kademeli canlı. "Canlıdaki
> akıştan iyi" tek başına yeterli değildir, çünkü canlı akışın kendisi NET negatif ölçüldü. Bu ADR kapıyı
> tanımlar; runtime değişikliği (sizing, notional) uygulanmadan önce ayrıca operatör onayı alınır (ADR-0012).

## Context

Every setup initiative so far wrote its own GO bar: Wave-2 used OOS PF ≥ 1.30 and ≥ 4/5 symbols, T-09 used
n ≥ 30 with IS and OOS NET > 0, and the FVG shadow uses "≥ 30 closes, NET > 0, better than live v2"
(`docs/superpowers/specs/2026-11-14-fvg-entry-shadow-design.md:106-111`,
`engine/safe_orchestrator.py:2333-2339`). Four different cost models are in use (`backtest/slippage.py:6-10` plus
the `backtest:` config block, `engine/edge_costs.py`, `engine/smc_v2/fvg_entry.py:25-27`, the T-09 harness), so
NET R values are not comparable. The live LuxAlgo flow went live without a NET measurement and was later
measured negative: −0.30 R/trade, PF 0.65, n=217 over 60 days
(`collab/outputs/claude-code/2026-11-04-lux-gate-counterfactual.md:42`), and PF 0.69 over 137 trades / 41 days
(`collab/outputs/claude-code/2026-11-07-backtest-live-parity.md:21-24`). With a negative baseline, "better than
live" is a weak test, and 30 forward trades are too noisy to judge PF.

## Decision

A setup or edge change may place live orders only after it passes, in order:

1. **Offline gate (the main gate)** — `python -m backtest.cli` on the live config
   (`docs/runbooks/backtest-gate.md`):
   - window ≥ 180 days × the 10 live symbols, n ≥ 100 closed trades per arm;
   - **canonical cost** = the backtest config model: `backtest.commission_pct` and `backtest.funding_pct_per_8h`
     (`configs/config.phase2_1k.yaml:480-482`) plus the per-leg slippage in `backtest/slippage.py:6-10`; for a
     limit entry only the entry leg may be counted as maker;
   - IS **and** OOS NET average R > 0;
   - OOS NET PF ≥ 1.30;
   - ≥ 60 % of symbols NET positive;
   - absolute thresholds above **and** better than the baseline arm on the same window; "better than live"
     alone never passes;
   - the report states a fixed window end, the git SHA (`provenance.json`), the cost line, and the number of
     variants tried on that window (multiple-testing note).
2. **Forward shadow (sanity check)** — log-only shadow with the same cost model: n ≥ 30 closed trades, NET > 0,
   and average NET R ≥ half of the offline average NET R.
3. **Staged go-live** — the first 30 live trades at $25 notional, then $50, through a separate PR with risk-ops
   review and operator sign-off (ADR-0003).

## Alternatives Considered

### Alternative 1: Forward shadow as the gate (n ≥ 30, NET > 0, PF ≥ 1.30, better than live v2)
- **Pros**: measures real fills on live data; the bar the FVG and touch shadows already state.
- **Cons**: at n = 30 a PF estimate is too noisy to separate an edge from luck; "better than live v2" compares
  against a NET-negative baseline; shadow books are lost on restart.
- **Why not**: forward data is kept as a sanity check, not as the deciding test.

### Alternative 2: Relative improvement only (beat the baseline arm)
- **Pros**: easy to meet, matches past per-initiative bars.
- **Cons**: every measured baseline is NET negative, so a "better" arm can still lose money.
- **Why not**: absolute thresholds are required as well.

### Alternative 3: Gross (commission-free) backtest
- **Pros**: faster comparisons, more variants pass.
- **Cons**: the measured loss driver is cost per R; gross results near zero hid it.
- **Why not**: the canonical cost line is mandatory.

## Consequences

### Positive
- One bar for every setup, the same cost model in every report, and reproducible results (window end + SHA).
- Supersedes the forward-only go-live bars in the FVG / touch shadow docstrings and spec as the deciding gate;
  they remain valid as the forward sanity step.

### Negative
- Slower path to live: 180-day multi-symbol runs are long on the laptop, and few variants will pass.
- The CLI has no window-end argument yet (`backtest/cli.py:35-36` uses the wall clock); until it does, reports
  must record the run date and cache state (GATED item: CLI `--end` and a gate script).

### Risks
- Overfitting by trying many variants on one window. Mitigation: the variant count is reported, and OOS plus
  the forward step must also pass.
- The shadow cost model (`engine/smc_v2/fvg_entry.py:25-27`) differs from the canonical one. Mitigation: forward
  NET R is recomputed with the canonical model before it is compared (GATED item Ö5).
