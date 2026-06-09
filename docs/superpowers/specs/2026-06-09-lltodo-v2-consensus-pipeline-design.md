# LLTODO v2 — Multi-Agent Consensus Pipeline (Design Spec)

- **Date:** 2026-06-09
- **Status:** APPROVED — v1.1 incorporates Gemini's 9.5/10 review (R1: branch co-location; R2: UltraReview proxy). → ready for writing-plans
- **Authors:** claude (synthesis) + gemini (independent implementation plan, merged)
- **Supersedes:** LLTODO v1 (`LLTODO/README.md` @ commit `0ba4780`)
- **Topic:** A git-backed blackboard + consensus state machine that lets Hermes, Claude,
  and Gemini (and optionally Codex/Manus/ollama) plan, review, implement, and test the
  same repo without colliding, with transparent task distribution and specialization
  that compounds over time.

---

## 1. Context & Problem

Hermes built **LLTODO v1**: a file-based coordination directory with a 5-phase pipeline
(PLAN → CONSENSUS → IMPLEMENT → ULTRAREVIEW → CROSSTEST), task/plan/review/report folders,
a 2/3-APPROVE consensus rule, and copy-paste prompts for Claude and Gemini.

The user (Utku) identified five gaps:

1. **Task distribution is opaque** — who does what, and *why*, is decided unilaterally by
   the plan author. ("hangi mantıkla dağıttın bilmiyorum.")
2. **Consensus only gates the PLAN phase** — the user wants mutual confirmation on plan,
   distribution, *and* test.
3. **No self-scheduling** — an agent should write a plan, then (via its own scheduler)
   come back and execute the tasks assigned to it, without doing unassigned work.
4. **No specialization tracking** — the role table is static; agents should provably get
   better in specific domains over time.
5. **No conflict-safety contract** — three agents writing to one repo must not collide.
   ("kimse kimseyle çakışmasın.")

This spec defines **LLTODO v2**, which closes all five gaps. It is the synthesis of an
independent Claude design and an independent Gemini implementation plan
(`~/.gemini/.../implementation_plan.md`); the two converged on ~80% of the structure,
which is treated as a strong validation signal.

## 2. Goals / Non-Goals

**Goals**

- A single, deterministic **entry contract** every agent runs on entering the repo.
- **Transparent, consensus-ratified task distribution** (rationale referencing a scoreboard).
- **Three consensus points** — plan approval, distribution approval, cross-test verdict
  confirmation — without inflating the familiar 5-phase model.
- **Conflict-safety by construction** — append-only per-agent namespaces + a claim lock.
- **Proxy-vote** handling so an active agent keeps momentum when a teammate is offline,
  while never impersonating the absent agent.
- **Specialization ledger** (`SCOREBOARD.md`) that compounds with each epic.
- **Honest self-scheduling** — automatic for Claude Code; prompt-driven relay for others.
- Reusable, generalized onboarding prompts for hermes/claude/gemini.

**Non-Goals**

- Automated cross-model invocation of frontier models. (As of 2026-06-09 the `superagent`
  MCP has only `ollama` configured; Gemini/GPT/Claude API keys are **not** set, so the
  consensus loop cannot fully auto-drive across frontier models. The design assumes a
  **hybrid**: each active runtime advances as far as it can, then hands off via files +
  a ready-made prompt.)
- Changing any live trading logic. LLTODO is docs-only and additive; it never touches
  `engine/`, `safe_orchestrator.py`, configs, or deploy.
- A real-time message bus. Coordination is asynchronous via committed files.

## 3. Key Decisions (locked in brainstorm)

| # | Decision | Choice |
|---|----------|--------|
| D1 | Orchestration model | **Hybrid** — committed `LLTODO/` is the source of truth; active agent auto-advances; file+prompt handoff for runtimes it cannot invoke. |
| D2 | Absent-agent handling | **Proxy vote + explicit label** — provisional, overridable, never impersonating; earns no specialization credit. |
| D3 | Conflict-safety | **Append-only + claim** — per-agent namespaces, claim-to-lock, surgical `git add`, no destructive ops. |
| D4 | Distribution & specialization | **Scoreboard-driven** — distribution proposed with scoreboard-referenced rationale, ratified by plan consensus. |
| D5 | Branch (revised, Gemini R1) | **Co-located per-epic + master registry.** An epic's LLTODO *working* files live on that epic's branch, beside the code, so the working agent never switches branches mid-task. Durable global files (`README`, `STATE` registry, `SCOREBOARD`, `templates`, `PROMPT-*`) live on `master`. Epic completion = one PR merging code + LLTODO to master. |
| D6 | Phase model | **5 phases, 3 consensus points** — keep v1/Gemini phase names; embed distribution-ratification inside CONSENSUS and verdict-confirmation inside CROSSTEST. |

## 4. Architecture

A **git-backed blackboard**. `LLTODO/` in the repo is the shared state. Each agent runtime
is a separate process (Claude Code, Gemini CLI, Hermes framework, optional Codex/Manus/
ollama). They never run in one address space; they coordinate purely through committed
files. Two small files give every agent O(1) orientation:

- **`STATE.md`** — the heartbeat: active epic, current phase, branch, who holds the ball,
  consensus tallies, what is blocking.
- **`SCOREBOARD.md`** — the specialization ledger: per-agent, per-domain track record.

**State lives in two tiers (revised per Gemini R1, to remove branch-switching overhead):**
- **Durable / global — on `master`:** `README.md`, `STATE.md` (the *epic registry*),
  `SCOREBOARD.md`, `templates/`, `PROMPT-*.md`. Agents read these on entry without switching
  branches (e.g. `git show origin/master:LLTODO/STATE.md`).
- **Volatile / per-epic — on the epic's working branch, beside the code:** `plans/`,
  `reviews/`, `tasks/`, `tests/`, `reports/` for that epic. The working agent claims, codes,
  tests, and reports all on one branch — **zero per-task branch-switching**. The epic's PR
  merges this coordination record to master on completion.

## 5. The Pipeline — 5 phases, 3 consensus points

```
PLAN ─▶ CONSENSUS ─▶ IMPLEMENT ─▶ ULTRAREVIEW ─▶ CROSSTEST
          │  ▲ teyit-1: plan approval (R-XXX, 2/3 APPROVE)
          │  ▲ teyit-2: distribution approval (in-plan section, same round)
          └──────────────────────────────────────────▲ teyit-3:
                                  cross-test verdict confirmation (confirmed_by)
```

**Phase 1 — PLAN.** One author writes `plans/P-XXX-<slug>.md`. The plan **must** include a
**Distribution** section: a `task → agent` table where every row carries a one-line
rationale referencing `SCOREBOARD.md` (e.g. "T-004 → gemini: highest visual-verification
record, 3/3 PASS"). The author opens review tasks for the other two agents.

**Phase 2 — CONSENSUS (two confirmation points in one round).** Voting set = the 3 core
agents (author + 2 reviewers); the author implicitly APPROVEs their own artifact. Each
reviewer writes `reviews/R-XXX-<agent>.md` with a `verdict` (APPROVE / CHANGES_REQUESTED /
REJECT) and an explicit line judging **distribution fairness**. Rules:
- 2/3 APPROVE → CONSENSUS_REACHED → Phase 3.
- 3/3 APPROVE → STRONG_CONSENSUS → Phase 3.
- 1 APPROVE + 2 CHANGES_REQUESTED → author revises, re-review.
- any REJECT → major revision, re-review from scratch.
- If a reviewer is offline, an active agent may file a **proxy review** (§7).
- **Integrity guards:** (a) CONSENSUS_REACHED requires at least **one genuine non-author
  APPROVE** — a plan can never pass on the author's self-approve + proxy votes alone;
  (b) the author may not proxy a reviewer of their own artifact (§7).

**Phase 3 — IMPLEMENT.** The author materializes one `tasks/PENDING/T-XXX-<agent>-<slug>.md`
per row of the (now-ratified) distribution. Each agent executes **only** tasks where
`assigned_to == self`, following the claim protocol (§6). On completion: move task to
`DONE/`, write a report under `reports/<agent>/`, and create any follow-on tasks.

**Phase 4 — ULTRAREVIEW (driver = Claude Code; proxy-escalable, Gemini R2).** When all
implementation tasks are DONE, Claude Code reads every DONE task + report and writes
`UR-XXX.md`: what's correct, what's missing/wrong, plan-drift, cross-task inconsistency.
Issues become `tasks/PENDING/FIX-XXX-<agent>.md` (FIX > T in priority). Claude Code also
updates `SCOREBOARD.md` for the epic (append-only, signed). **SPOF guard:** if Claude holds
the Phase-4 ball past the SLA recorded in `STATE.md` (default 24h, user-tunable), another
core agent MAY file a provisional **proxy UltraReview** (`UR-XXX-PROXY`) to unblock the
pipeline; Claude's genuine report supersedes it on return. Proxy UltraReview obeys the §7
integrity guards (no reviewing one's own implementation; earns no specialization credit).

**Phase 5 — CROSSTEST (verdict confirmation = third consensus point).** Rotation: each
agent tests **another** agent's work (`hermes→claude`, `claude→gemini`, `gemini→hermes`).
The tester writes `tests/TEST-XXX-<tester>-tests-<testee>.md` with verdict PASS / BUGS_FOUND.
A `BUGS_FOUND` verdict does **not** become a FIX task until a second agent confirms it
(`confirmed_by:` in frontmatter) — this prevents false-positive bugs from derailing.
Confirmed bugs → FIX tasks → re-test → re-confirm. When all cross-tests PASS, the epic
is DONE and `STATE.md` advances.

## 6. Conflict-Safety Protocol (append-only + claim)

**Namespace ownership** — an agent only CREATEs/EDITs files it owns:
- `reports/<agent>/...`
- `reviews/R-XXX-<agent>.md`, `tests/TEST-XXX-<agent>-tests-*.md`
- Shared files (`STATE.md`, `SCOREBOARD.md`, a plan it authored) are edited **only** by
  their owner, or appended to via a clearly delimited **per-agent section**. No agent ever
  edits another agent's section.

**Claim = lock** — to work a PENDING task: move it to `IN_PROGRESS/`, stamp `claimed_by`
+ `claimed_at` in frontmatter, then **commit+push immediately**. On the next `pull`, a
racing agent sees the claim and backs off.

**Git discipline (every write):**
1. `git pull --rebase` before any change.
2. `git add LLTODO/<specific paths>` — **never** `git add -A` / `git add .`.
3. Commit with a scoped message (`lltodo: <agent> <action> <id>`), then `git push`.
4. **Forbidden:** `git reset --hard`, force-push, `git checkout --` on files you don't own,
   editing another agent's namespace.
5. **Durable global files** (`README`, `STATE` registry, `SCOREBOARD`, `templates`,
   `PROMPT-*`) are committed to **`master`** (rare — at epic start/transition/end).
   **Per-epic working files** are committed to the **epic's branch** alongside the code and
   reach master via the epic's merge PR (D5, Gemini R1). The working agent thus stays on one
   branch per task — no mid-task switching.

## 7. Absent-Agent Proxy-Vote Protocol (D2)

When a phase needs agent X's vote and X is not active, the active agent MAY produce a
**proxy** using an **independent context** (a fresh/adversarial Claude subagent, `ollama`,
or any configured model), written to the normal artifact path with a `-PROXY` suffix and
frontmatter:

```yaml
proxy: true
proxy_by: claude          # who generated it
proxy_engine: subagent    # subagent | ollama | <model>
provisional: true
```

Rules:
- A proxy vote **counts toward quorum** but is flagged PROVISIONAL.
- When the real agent later runs, its genuine vote **supersedes** the proxy (the proxy file
  is moved aside / marked `superseded_by`).
- A proxy is **never** presented as the real agent.
- `SCOREBOARD.md` awards **no specialization credit** for proxied work.
- **Integrity guards:** an agent may not proxy a vote on its **own** authored artifact;
  and proxy votes alone can never satisfy a consensus gate — at least one genuine,
  non-author vote is always required (mirrors §5 Phase 2).
- **Phase-4 coverage (Gemini R2):** the same proxy mechanism covers the UltraReview SPOF.
  A `UR-XXX-PROXY` is provisional and superseded by Claude's genuine report on return; it
  unblocks the pipeline only after the `STATE.md` SLA on Claude's Phase-4 ball has elapsed.

## 8. Scoreboard & Transparent Distribution (D4)

`LLTODO/SCOREBOARD.md` — one block per agent (`hermes, claude, gemini, manus, codex`),
append-only, updated by the UltraReview driver each epic:

Per-agent fields (union of Claude + Gemini designs):
- `tasks_completed`, `reviews_done`, `avg_review_confidence`, `active_streak`
- `bugs_found_in_others` (+), `bugs_caught_in_own_work` (−)
- `domains[]` touched, and a per-domain `specialty_score`
- a short `specialty:` definition line

**Transparency loop:** the PLAN-phase Distribution section cites these numbers as the
rationale for each assignment; CONSENSUS reviewers explicitly ratify or contest the
distribution. This is the concrete fix for "hangi mantıkla dağıttın bilmiyorum."

## 9. Self-Scheduling (D1, honest hybrid)

- **Claude Code (me):** native `ScheduleWakeup` / cron — after advancing the pipeline I
  schedule an LLTODO recheck. **Automatic.**
- **Hermes:** its own runtime; prompt instructs "re-enter, scan LLTODO." Usually
  user-driven or Hermes's own scheduler.
- **Gemini CLI:** no scheduler — the PENDING task + ready prompt file is the trigger; the
  user relays it. (No false promise of cron.)

## 10. Directory Structure & ID Scheme

**Placement legend (Gemini R1):** `[M]` = lives on `master` (durable/global, read on entry);
`[E]` = lives on the epic's working branch (volatile, beside the code) until the epic PR
merges it to master.

```
LLTODO/
├── README.md       [M]  # v2 protocol; entry contract at the very top
├── STATE.md        [M]  # epic registry: active epics → branch, phase, ball-holder, SLA
├── SCOREBOARD.md   [M]  # specialization ledger (cumulative across epics)
├── templates/      [M]
│   ├── P-template.md          # Plan (incl. mandatory Distribution+rationale section)
│   ├── R-template.md          # Review (verdict, findings, distribution-fairness line,
│   │                          #          proxy fields)
│   ├── T-template.md          # Task (instructions, deps, deliverables, claim fields)
│   ├── UR-template.md         # UltraReview report (+ PROXY variant)
│   ├── TEST-template.md       # Cross-test (verdict, confirmed_by)
│   └── REPORT-template.md     # Agent run log / handover note
├── PROMPT-claude.md  [M]  # generalized onboarding (NOT epic-specific)
├── PROMPT-gemini.md  [M]
├── PROMPT-hermes.md  [M]
├── plans/          [E]  # P-XXX
├── reviews/        [E]  # R-XXX-<agent>  (incl. -PROXY)
├── tasks/{PENDING,IN_PROGRESS,DONE}/  [E]  # T-XXX / FIX-XXX / R-XXX review-tasks
├── tests/          [E]  # TEST-XXX-<tester>-tests-<testee>
└── reports/{hermes,claude,gemini}/  [E]
```

**ID prefixes:** `P-` plan · `R-` review · `T-` task · `FIX-` ultrareview fix ·
`UR-` ultrareview report · `TEST-` cross-test.

## 11. Entry Contract (deterministic boot — top of README)

Every agent, on entering the repo:
1. `git pull --rebase`
2. Read `LLTODO/STATE.md` (orient: epic, phase, branch, ball-holder).
3. Read `LLTODO/SCOREBOARD.md`.
4. Scan `tasks/PENDING/` for `assigned_to: <me>` (or proxy-eligible work per §7).
5. **Claim** the task (move to `IN_PROGRESS/`, stamp, commit+push).
6. Do **only** the claimed task. Do not touch unassigned work.
7. Write output in your namespace; create any follow-on tasks.
8. On a **phase transition**, update the `master:STATE.md` registry entry for your epic
   (phase, ball-holder, SLA); per-task progress is reflected by moving task files on the
   epic branch (no master touch per task). If you are the UltraReview driver, also update
   `master:SCOREBOARD.md` (append-only, signed).
9. Surgical `git add LLTODO/...` → commit → push.
10. Self-schedule a recheck (Claude/Hermes) or leave a ready prompt for relay (Gemini).

## 12. Artifact Frontmatter (authoritative schemas)

Carried over from v1 where unchanged; additions noted. Templates encode these.

- **Plan `P-XXX`:** `plan_id, author, status, created, reviewers[], approvals_needed,
  approvals_received` + body sections incl. **Distribution (with rationale)**.
- **Review `R-XXX-<agent>`:** `review_id, plan_id, reviewer, verdict, confidence, created`
  + optional proxy fields (§7) + a **distribution-fairness** verdict line.
- **Task `T-XXX`:** `task_id, assigned_by, assigned_to, priority, status, skill, phase,
  deadline, dependencies[], plan_id, created` + `claimed_by, claimed_at` on claim.
- **Cross-test `TEST-XXX`:** `test_id, plan_id, tester, testee, verdict, created` +
  `confirmed_by` before a BUGS_FOUND becomes a FIX.
- **UltraReview `UR-XXX`:** `ultrareview_id, reviewer, plan_id, status, created`.

## 13. Migration & Cleanup (first live epic = the system testing itself)

- `[MODIFY]` `LLTODO/README.md` → v2 (entry contract on top, 5-phase/3-consensus, proxy
  rules, claim protocol, directory layout).
- `[NEW]` `STATE.md`, `SCOREBOARD.md`, `templates/*`, `PROMPT-{claude,gemini,hermes}.md`.
- `[MODIFY]` `plans/P-001-...md` → P-template format incl. Distribution section.
- `[MODIFY]` `tasks/PENDING/R-001-...md`, `R-002-...md` → T-template format.
- `[DELETE]` `PROMPT-claude-p001-review.md`, `PROMPT-gemini-p001-review.md`
  (epic-specific logic absorbed into generalized prompts).

## 14. Verification Plan

- **File existence:** every NEW file present; every DELETE removed.
- **Schema lint:** each artifact's frontmatter contains required keys (a tiny check script
  or manual pass).
- **graphify:** `graphify query "Show dependencies for LLTODO"` after `graphify update .`
  to confirm the docs graph is coherent.
- **Dry-run of the entry contract:** walk one agent (Claude) through boot → claim →
  report → STATE update → scoreboard update in shadow mode, confirming no namespace is
  violated and the claim lock works.
- **Bootstrap test:** run the migrated **P-001** epic through CONSENSUS using the new
  templates (Claude real review + a labeled Gemini proxy) to prove the loop end-to-end.

## 15. Deliverables (handed to writing-plans)

1. `LLTODO/README.md` v2
2. `LLTODO/STATE.md`
3. `LLTODO/SCOREBOARD.md`
4. `LLTODO/templates/{P,R,T,UR,TEST,REPORT}-template.md`
5. `LLTODO/PROMPT-{claude,gemini,hermes}.md`
6. Migration of P-001 + R-001/R-002; deletion of the two epic-specific prompts
7. (Optional) a `scripts/lltodo_lint.py` frontmatter checker for the verification step

## 16. Open Questions / Future

- Adding frontier API keys to `superagent` would let Claude auto-drive the full consensus
  loop (upgrade path from hybrid → automated). Out of scope now.
- Whether `manus`/`codex` become standing voters (changing quorum math from 2/3) or remain
  optional tie-breakers. Default: 3 core voters; extras are optional.
- A periodic "retro" that rewrites each agent's `specialty:` line from accumulated scores.
