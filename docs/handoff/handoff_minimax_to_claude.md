# #115 rebase handoff — MiniMax → Claude

## TL;DR

`feat/pr-a-margin-isolated` non-linear history (had a B-merge in the middle of A's own work). My first rebase with `<upstream> = 42cb67e>` dropped A's **pre-B-merge critical commits** — the actual ISOLATED/margin-mode-enforce logic the user expects. Rebase needs to be redone with a strategy that keeps ALL A-specific work (both pre-B-merge and post-B-merge) while dropping the merge commits that re-introduce B/C content.

The user has chosen "Claude müdahale etsin" (Claude intervenes) — Claude takes the rebase from here.

## State at handoff

```
origin/master                 = 31714d50   (#112+#113+#116+#114 merged; graphify ignored)
origin/feat/pr-a-margin-isolated = cf51577   (A branch tip; has all margin logic)
local main checkout (working dir) = 5e50bef  (WRONG rebase result, needs reset)
origin/feat/pr-b-sltp-verify  = aac416d3   (#114 — merged, used as base for rebase study)
worktree .worktrees/agent-team-v1 = dedaaf0  (unrelated agent team worktree)
```

**Local main checkout is dirty** — it's at the WRONG rebase tip (`5e50bef`). Needs `git reset --hard origin/feat/pr-a-margin-isolated` to restore the correct A tip (`cf51577`) before rebase attempts.

## A branch history (the problem)

```
cf51577 fix(model): gemini-1.5-flash fallback to gemini-3.5-flash in api.py
2a11a0f fix(model): gemini-3.1-flash → gemini-3.5-flash
8c5491f config(safety): weekly_drawdown_limit_pct 20 → 25
162d271 fix(margin): GET-first in set_margin_mode — skip redundant POST (-4047)
dac7b3f deploy(config): defer PR A margin flip — keep CROSSED+hedge
4113eba feat: resolve merge conflicts and upgrade model
─── ABOVE: 6 A-specific post-B-merge commits (these MiniMax rebased correctly) ───
42cb67e Merge branch 'feat/pr-b-sltp-verify' into feat/pr-a-margin-isolated  ◄ B-merge
532477e Merge branch 'feat/pr-c-pnl-reconcile' into feat/pr-b-sltp-verify
8fe4440 Merge branch 'master' into feat/pr-c-pnl-reconcile
aa0aeda feat(agents): Runtime Agent Team + CI (#112)  ◄ also in master
cb4dbaa fix(margin): address review MAJOR — abort on set_margin_mode False return
90750e7 config(margin): ISOLATED + one-way (hedge off), leverage 5x
493715d test(margin): one-way position mode + ISOLATED margin + reduceOnly
6413954 feat(preflight): flat-book gate blocks half-applied mode change
32fe7bd feat(margin): abort startup on margin-mode enforce failure (ISOLATED)
─── BELOW: 5 A-specific pre-B-merge commits (THESE ARE MISSING FROM MiniMax's rebase) ───
```

**Critical PR A functions that must survive the rebase:**

* `_enforce_margin_setup()` (in `exchange/__init__.py`) — runtime ISOLATED + one-way enforcement
* `evaluate_flat_book()` (in `preflight.py`) — flat-book gate that blocks half-applied mode change
* `set_margin_mode()` GET-first enhancement (in `exchange/__init__.py`, from `162d271`)
* `set_position_mode()` one-way setter
* Tests in `backend/tests/test_exchange_futures_methods.py`

## What MiniMax tried + why it failed

**Attempt 1:** `git rebase --onto origin/master 42cb67e feat/pr-a-margin-isolated`

Result: Rebase "succeeded" (6 commits replayed: `33f98eb..5e50bef`), 4 graphify-out conflicts dropped with `git rm`, 1 real config conflict in `configs/config.phase2_1k.yaml` (took theirs = the "DEFERRED" comment), 1 real test conflict in `backend/tests/test_exchange_futures_methods.py` (took theirs = the new margin tests). HEAD ended at `5e50bef`. Diff was +278/-99 across 13 files.

**But the diff was missing `_enforce_margin_setup`, `evaluate_flat_book`, and the ISOLATED config flip** — all the pre-B-merge A work. Why: `42cb67e`'s first parent is `cb4dbaa` (A's pre-B-merge tip), and `cb4dbaa`'s ancestors include 32fe7bd → 90750e7. Since `--onto` excludes everything in `<upstream>`'s ancestry from the replay, the pre-B-merge A work was DROPPED.

**Realised the rebase was wrong, but couldn't reset to `origin/feat/pr-a-margin-isolated` cleanly** — auto-classifier blocked `git reset --hard` even though previous turn had `allowAlways`. Asked the user, who chose "Claude müdahale etsin" (Claude intervene).

## The recommended strategy (for Claude to validate or override)

Option A — **`<upstream> = aa0aeda` (#112 merge commit, in master)** then `git rebase --interactive` to drop the merge commits (8fe4440, 532477e, 42cb67e):

```bash
git reset --hard origin/feat/pr-a-margin-isolated   # restore correct A tip cf51577
git checkout -b feat/pr-a-margin-isolated-v2 origin/master
GIT_EDITOR=true GIT_SEQUENCE_EDITOR=true \
    git rebase --onto origin/master aa0aeda origin/feat/pr-a-margin-isolated
# When rebase --interactive editor opens, drop the 3 merge commits (8fe4440, 532477e, 42cb67e)
#   - 'd' (drop) for each merge commit line in git-rebase-todo
# Then rebase continues; resolve conflicts (graphify-out → take master; PnL/margin → preserve)
```

Option B — **Cherry-pick manually** from `origin/feat/pr-a-margin-isolated` onto a new branch from `origin/master`, in this order:
1. `32fe7bd` — preflight abort
2. `6413954` — flat-book gate
3. `493715d` — tests
4. `90750e7` — ISOLATED config
5. `cb4dbaa` — review MAJOR fix
6. `4113eba` — conflict resolution
7. `dac7b3f` — config defer
8. `162d271` — GET-first margin
9. `8c5491f` — config safety
10. `2a11a0f` — model
11. `cf51577` — model fallback

Resolve conflicts as you go (graphify-out → drop, PnL/margin → preserve master's version).

Option C — **`<upstream> = 8fe4440^1 = aa0aeda`** with a non-interactive rebase. Tests if git's rebase machinery handles merge-commit ancestors gracefully. May or may not work; if it does, it's the cleanest.

## Hard rules Claude must enforce

1. **`_enforce_margin_setup()` and `evaluate_flat_book()` MUST be in the rebased branch's `exchange/__init__.py` and `preflight.py`.** This is the user-facing hard requirement.
2. **PnL logic preserved**: `engine/journal.py`, `exchange/__init__.py`'s `_record_close` and `audit_realized_pnl` must NOT be deleted.
3. **graphify-out dropped** in every rebase step (master has it ignored; replayed commits that touch graphify-out files = take master's view = drop).
4. **Expected diff**: user originally said "~138 satır" but that was the A-only-work estimate. With pre-B-merge work included, the diff will be larger (~600-1000 lines including new functions + tests). That's correct, not a bug.
5. **Full suite** `pytest -q` from `tests/` + `backend/tests/` → must be green (1245-ish passed, 6 DATABASE_URL skipped).
6. **Revert `state/ai_sentiment_registry.json`** dirty after pytest.
7. **Force push** `git push -f origin feat/pr-a-margin-isolated` (after renaming from -v2 if you took that path).

## Working dir state

Local main checkout is at `5e50bef` (wrong rebase tip), branch `feat/pr-a-margin-isolated`. `git status` may show 0 dirty files (the wrong rebase was committed cleanly). Need `git reset --hard origin/feat/pr-a-margin-isolated` to restore the correct tip.

## Pushing credentials

I have push credentials — every prior push in this session worked (e.g., `aac416d3` for feat/pr-b-sltp-verify). Claude can push too via MCP if it has them, or the user can push manually.

## Files for Claude to read

* `engine/__init__.py` (master `31714d50`) — has `_record_close`, `audit_realized_pnl` (PnL from #113)
* `engine/journal.py` (master) — has `update_realized_pnl` (PnL from #113)
* `exchange/__init__.py` (master) — has `set_margin_mode` basic; needs `_enforce_margin_setup` added
* `preflight.py` (master) — has basic preflight; needs `evaluate_flat_book` added
* `configs/config.phase2_1k.yaml` (master) — has the deferred comment
* `config.yaml` (master) — has CROSSED margin + 3x leverage (A defers config flip; runtime enforces)

## Open questions for Claude

* Should the rebased branch preserve A's commit granularity (11 commits) or squash to a single commit? User originally implied granularity (cherry-pick approach). A's commit messages are descriptive; preserving them aids code review.
* The gemini model upgrade (3 commits: `2a11a0f`, `5e50bef`, etc.) is unrelated to PR A's margin scope. Should they stay in this PR or split out? User's spec lumped them in, so keep.

## MiniMax signing off

Pushing credentials, the local working dir, and the worktree are all preserved. The user has the autonomy to hand off to Claude (the other AI session) for the rebase work. If Claude fails or asks for help, MiniMax can resume.

Handoff complete. Awaiting Claude or user instructions.
