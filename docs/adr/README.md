# Architecture Decision Records

Hard-to-reverse decisions for efloud-bot, written in the `template.md` format. ADRs 0001–0009 were
backfilled on 2026-11-07, and each one records its original decision date.

| ADR | Title | Status | Date |
|-----|-------|--------|------|
| [0001](0001-single-vps-docker-compose-for-bots.md) | Bots on one VPS with Docker Compose; Railway only for the site | accepted | 2026-11-07 (backfill) |
| [0002](0002-llm-layer-is-advisory-only.md) | LLM layer is advisory only; never blocks or changes a trade | accepted | 2026-11-07 (backfill) |
| [0003](0003-risk-fixes-default-off-behind-gates.md) | Risk/edge changes default-OFF; activation needs backtest + sign-off | accepted | 2026-11-07 (backfill) |
| [0004](0004-smc-v2-explicit-symbol-whitelist.md) | SMC v2 live per explicit symbol list; missing shadow key = shadow | accepted | 2026-11-07 (backfill) |
| [0005](0005-pine-indicator-only-product.md) | TradingView product is indicator-only | accepted | 2026-11-07 (backfill) |
| [0006](0006-prod-file-state-db-optional.md) | Prod state is file-based; Postgres optional | accepted | 2026-11-07 (backfill) |
| [0007](0007-alerter-tails-bot-log.md) | Alerter is a separate container tailing the bot log | accepted | 2026-11-07 (backfill) |
| [0008](0008-git-based-multi-model-collaboration.md) | Multi-model collaboration through git, PR-only | accepted | 2026-11-07 (backfill) |
| [0009](0009-entry-confirmation-required.md) | Entries require confirmation | accepted | 2026-11-07 (backfill) |
| [0010](0010-generated-regression-ledger.md) | Generated, CI-checked regression ledger | accepted | 2026-11-07 |
