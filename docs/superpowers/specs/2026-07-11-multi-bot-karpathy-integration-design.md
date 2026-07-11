# Multi-Bot Karpathi Integration + Audit Fix Design

**Date:** 2026-07-11  
**Status:** APPROVED - Ready for Implementation Planning  
**Scope:** Karpathy prensiplerini 3-bot sistemine entegre etme + PARKED audit fixlerini tamamlama

## Context

### Current System Architecture
- **3 Active Trading Bots**: 5m (scalp), 15m (mid), 1h (long/swing)
- Her botun ayrı bias/trend analizi ve timeframe characteristics
- **Single Config Problem**: Currently `config.phase2_1k.yaml` controls all bots
- **Audit Findings**: C4/H1/H5/H6/H7/M1/M2 PARKED pending backtest gates

### Karpathi Principles Integration
The 4 Karpathi principles need active enforcement, not just documentation:
1. **Think Before Coding** → Safety/risk path assumptions explicit
2. **Simplicity First** → No speculative abstraction, minimal code
3. **Surgical Changes** → Touch only needed lines, no drive-by refactors
4. **Goal-Driven Execution** → Test-first, verifiable success criteria

## Design

### Phase 1: Multi-Bot Configuration Architecture

#### 1.1 Bot-Specific Config Structure

**New Config Files:**
```yaml
configs/
├── config.shared.yaml           # Common settings (DB, API keys, safety limits)
├── bot_5m_scalp.yaml            # 5m entry TF, conf: 50-55
├── bot_15m_mid.yaml             # 15m entry TF, conf: 60-70  
└── bot_1h_long.yaml             # 1h entry TF, conf: 75-80
```

**Config Schema:**
```yaml
# bot_*_scalp.yaml example
bot_id: "5m_scalp"
entry_timeframe: "5m"
mtf_timeframe: "1h" 
htf_timeframe: "4h"
confluence:
  min_confluence: 50              # Bot-specific threshold
  max_confluence: 100
  post_cap_bonuses: false        # H1 fix
safety:
  starting_balance: 1000
  emergency_balance_threshold: 900
  daily_loss_limit_pct: 5
  leverage: 3
  max_sl_atr: 4.0                # H3 fix
risk:
  max_holding_hours: 12          # Scalp-specific
  consecutive_loss_limit: 3
```

#### 1.2 Confluence Threshold Strategy

**Risk-Profile Based Calibration:**
- **5m Scalp**: conf=50-55 (higher frequency, lower conf per trade)
- **15m Mid**: conf=60-70 (balanced frequency/quality)
- **1h Long**: conf=75-80 (highest quality, lower frequency)

**Rationale:** Higher timeframe = more structural analysis = higher confidence threshold required.

### Phase 2: Karpathi Active Enforcement

#### 2.1 Pre-commit Hook: Karpathi Compliance

**Implementation:** `.claude/hooks/pre-commit`
```bash
#!/bin/bash
# Karpathi compliance check before commits

# Check 1: Safety/risk paths require assumptions log
if git diff --cached --name-only | grep -E "(engine/safety|engine/risk|engine/lifecycle)"; then
    if ! git log -1 --pretty=%B | grep -q "ASSUMPTIONS:"; then
        echo "❌ Think-Before-Coding: Safety changes require ASSUMPTIONS documentation"
        exit 1
    fi
fi

# Check 2: No over-complication (function length < 100 lines)
for file in $(git diff --cached --name-only | grep '\.py$'); do
    if python -c "
import ast
with open('$file') as f:
    for node in ast.walk(ast.parse(f.read())):
        if isinstance(node, ast.FunctionDef) and node.end_lineno - node.lineno >= 100:
            print(f'Complex function: {node.name} at line {node.lineno}')
            exit(1)
"; then
        echo "❌ Simplicity-First: Function >100 lines detected"
        exit 1
    fi
done

# Check 3: Surgical changes (no unrelated file edits)
# Check 4: Goal-driven (test requirements for features)
```

#### 2.2 PR Template Integration

**New PR Template Section:**
```markdown
## Karpathy Principles Checklist

- [ ] **Think-Before-Coding**: 
  - [ ] Assumptions documented (for safety/risk changes)
  - [ ] Trade-offs explicitly stated
  - [ ] Operatör onayı required for mainnet changes
  
- [ ] **Simplicity-First**:
  - [ ] No speculative features
  - [ ] Functions <100 lines (exceptions documented)
  - [ ] No unnecessary flexibility
  
- [ ] **Surgical Changes**:
  - [ ] Only modified files related to the stated goal
  - [ ] No drive-by refactors
  - [ ] Orphan cleanup handled (imports/variables)
  
- [ ] **Goal-Driven Execution**:
  - [ ] Test written first (TDD)
  - [ ] Success criteria defined
  - [ ] Backtest gate passed (for edge changes)
```

### Phase 3: Audit Fix Implementation (Multi-Bot)

#### 3.1 Priority Order

**Phase 3a: Quick Wins (Bot-Independent)**
1. **M1** - `is_discovery` misclassification fix
   - Location: `signals.py:644-653`
   - Fix: Derive from actual TP1 formula usage
   - Test: Unit test for ranging vs trending discovery logic

**Phase 3b: Multi-Bot Conf Calibration**
2. **C4** - Confluence threshold calibration per bot
   - 5m bot: Backtest conf=50 vs 55 vs 60
   - 15m bot: Backtest conf=65 vs 70 vs 75
   - 1h bot: Backtest conf=75 vs 80 vs 85
   - Gate: NET-cost Edge Measurement Core (PR #227)

**Phase 3c: Structural Fixes**
3. **H1** - Post-cap confluence bonuses (disable per bot config)
4. **H5** - HTF chop bias (per-bot analysis)
5. **H6** - OTE mismatched legs validation
6. **H7** - Forced-RR clamp → reject approach
7. **M2** - Confluence over-counting analysis

#### 3.2 Implementation Pattern (Per Finding)

**Pattern:** Verify → Test → Fix → Backtest → Review
1. **Verify**: Adversarial re-verification of finding
2. **Test**: Write failing test reproducing the issue
3. **Fix**: Minimal surgical change
4. **Backtest**: NET-cost Edge Measurement Core run
5. **Review**: risk-ops + quant + operatőr sign-off

### Phase 4: Deployment Strategy

#### 4.1 Staged Rollout

**Stage 1 - Config Migration:**
1. Create `config.shared.yaml` + 3 bot configs
2. Validate backward compatibility
3. Test each bot independently in dry-run mode

**Stage 2 - Audit Fixes Rollout:**
1. M1 fix (quick win, low risk)
2. C4 multi-bot backtest (Edge Core)
3. H1-H7 + M2 structural fixes (per-bot validation)

**Stage 3 - Production Deployment:**
1. Deploy to shadow mode (v2_shadow) first
2. Monitor for 24-48 hours per bot
3. Sequential rollout: 5m → 15m → 1h (least to most capital)

#### 4.2 Fail-Safe Mechanisms

**Per-Bot Circuit Breakers:**
- Individual bot daily loss limits
- Cross-bot drawdown coordination
- Automated rollback on anomaly detection

## Success Criteria

### Phase 1 Success
- [ ] 3 bot-specific configs created and validated
- [ ] Shared config properly extracted
- [ ] Dry-run testing per bot successful

### Phase 2 Success  
- [ ] Pre-commit hook enforcing Karpathy principles
- [ ] PR template integrated into workflow
- [ ] Code review agents updated with Karpathy checks

### Phase 3 Success
- [ ] M1 fix deployed with passing tests
- [ ] C4 multi-bot backtest completed with optimal conf per bot
- [ ] H1-H7 + M2 fixes backtest-validated per bot
- [ ] All fixes pass risk-ops + quant review

### Phase 4 Success
- [ ] Staged deployment completed without regressions
- [ ] Production monitoring shows 3 bots operating correctly
- [ ] NET-cost edge metrics improved vs baseline

## Risks & Mitigations

### Risk 1: Config Migration Complexity
**Mitigation:** Extensive dry-run testing + backward compatibility layer

### Risk 2: Backtest Computational Load
**Mitigation:** Use Edge Measurement Core (already optimized), run per bot sequentially

### Risk 3: Multi-Bot Coordination Issues  
**Mitigation:** Fail-safe circuit breakers, staged rollout, shadow mode validation

## Open Questions

1. **Capital Allocation:** How to split capital across 3 bots? (Operatőr decision required)
2. **Correlation Risk:** What if all 3 bots get signals simultaneously? (Cross-bot coordination needed)
3. **Monitoring:** Dashboard requirements for 3-bot monitoring?