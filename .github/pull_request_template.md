## Summary

<!-- Provide a brief description of the problem, background context, and what the change accomplishes. -->

## Changes

<!-- List files and components modified. Explain critical design decisions. -->

## Behavior & Impact

<!-- Explain behavioral changes, especially in risk, safety or execution paths. -->

## Security & Scope Check

- [ ] **Live config touched?** (Check if config.yaml, .env, docker-compose.prod.yml, VPS deploy or mainnet risk settings were modified)
- [ ] **Research-only?** (Check if changes are fully isolated to candidate, backtest, or research/learning layers with zero production execution path impact)

## Tests & Verification

<!-- State exact tests run, commands executed, and attach pass outputs. -->
```bash
pytest backend/tests/test_...
```

## Approval gates

- [ ] Claude as-shipped review
- [ ] Hermes/Utku diff review
- [ ] Explicit merge decision
- [ ] Separate production deploy/recreate decision
