---
description: Run efloud-code-reviewer on the current branch's pending changes. Auto-escalates to efloud-risk-ops-reviewer if risk/safety paths are touched.
---

# /review

Invoke the efloud-code-reviewer agent on the current diff (`git diff` staged + unstaged).

Steps:
1. Run `git status --short` and `git diff --stat` to see scope.
2. If any of the following paths appear in the diff, ALSO invoke `efloud-risk-ops-reviewer`:
   - `engine/safety/`
   - `engine/lifecycle.py`
   - `exchange/`
   - `config.yaml` (only if `risk:` or `safety:` blocks changed)
   - `docker-compose.prod.yml`
   - `backend/migrate.py`
   - any new `.sql` file
3. Report findings using each agent's standard output format.
4. End with a single line: `READY TO COMMIT: yes | no — <reason>`.
