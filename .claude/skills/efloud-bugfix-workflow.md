---
name: efloud-bugfix-workflow
description: Standard procedure for fixing a bug in efloud-bot — repro → localize → fix → test → review → PR. Use whenever user reports a bug, log error, or production incident.
---

# efloud-bugfix-workflow

Follow these steps in order. Do not skip.

## 1. Repro
- Get the error message, log line, or behavior description from user / GitHub issue / `efloud_bot.log`.
- Construct the **minimum** repro: which command, which config, which symbol, which timeframe.
- Write the repro down (will become the test in step 4).

## 2. Localize
- `Grep` for the error string or the misbehaving symbol.
- `Read` the file. Walk the **call graph** outward: who calls this function, what state does it depend on?
- Identify the **root cause**, not just the symptom. (Don't catch+ignore; don't add try/except as a "fix".)

## 3. Fix
- Minimum diff. No surrounding refactor, no "while I'm here" cleanup.
- No new abstraction unless the bug literally requires it.
- No defensive code for cases that can't happen.
- If touching `engine/safety/`, `engine/lifecycle.py`, `exchange/`, `config.yaml` →
  this is a risk-bearing change. Plan to invoke `efloud-risk-ops-reviewer`.

## 4. Test (regression guard)
- Hand off to `efloud-test-engineer` agent OR write the test inline:
  - First write the test → confirm it **fails** without the fix.
  - Apply the fix → confirm test now **passes**.
- Run smoke: `pytest test_smoke.py test_safety.py -v`.

## 5. Self-review
- Invoke `efloud-code-reviewer` on the diff.
- If the diff touches risk/safety paths → also invoke `efloud-risk-ops-reviewer`.
- Address all BLOCKER and MAJOR findings before continuing.

## 6. PR
- Branch: feature branch (per session instructions, e.g. `claude/bot-analysis-memory-*`).
- Commit message: `fix: <one-line summary>` — atomic, no mixed concerns.
- Check if `RISK_MAP.md` needs updating (new failure mode discovered).
- Push: `git push -u origin <branch>`.
- Open **draft** PR (per harness rules) with:
  - **Summary**: what broke, root cause, fix.
  - **Test plan**: which tests, how to verify manually.
  - **Risk**: any production-side action needed (migration, compose recreate)?

## Hard rules
- No `--no-verify` on commits.
- No force-push to main.
- No skipping step 4 (regression test).
- No production deploy from this workflow — that's a separate human approval.
