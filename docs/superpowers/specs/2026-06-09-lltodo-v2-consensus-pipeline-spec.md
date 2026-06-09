# LLTODO v2 Multi-Agent Consensus Pipeline — Design Spec

**Date:** 2026-06-09
**Status:** Approved (Tasarım onaylandı)
**Author:** Gemini (Senior Orchestrator)
**Scope:** Multi-agent collaboration framework, task distribution system, and state management.

---

## 1. Context & Objectives

The `LLTODO` folder serves as a git-based shared database (blackboard pattern) that enables autonomous multi-agent systems (Claude, Hermes, Gemini, Manus, Codex) to coordinate task assignment, reach consensus on architecture and scope, execute implementation safely, and perform cross-testing.

This specification details **LLTODO v2**, which refines the flow, institutes a strict entry contract for all agents, establishes structured templates, defines a centralized dashboard system (`STATE.md` and `SCOREBOARD.md`), and provides custom system prompts to align agent behavior.

### Open Decision (C.4): Repository Branch Strategy for LLTODO
After evaluation, it is resolved that **LLTODO files live directly on the active codebase branches** (current feature-branches and merged directly into `main`).
- **Rationale:** Tasks, plans, and reviews are deeply tied to the AST and code state. Storing them in the same branch ensures atomic code changes along with their corresponding task status and design reviews.

---

## 2. Dizin Yapısı (Folder Layout)

The new structure of `LLTODO/` is:

```
LLTODO/
├── README.md               # [v2] Entry contract & global rules
├── STATE.md                # [NEW] Active plans, tasks state, and next actions
├── SCOREBOARD.md           # [NEW] Multi-agent performance tracking & roles
├── PROMPT-hermes.md        # [NEW] Copy-paste system prompts for Hermes agent
├── PROMPT-claude.md        # [NEW] Copy-paste system prompts for Claude agent
├── PROMPT-gemini.md        # [NEW] Copy-paste system prompts for Gemini agent
├── plans/                  # Plan files: P-XXX-<slug>.md
├── reviews/                # Consensus reviews: R-XXX-{agent}.md
├── tests/                  # Cross-testing reports: TEST-XXX-{tester}-tests-{testee}.md
├── reports/                # Agent logs grouped by agent directories
│   ├── hermes/
│   ├── claude/
│   └── gemini/
├── tasks/                  # Task lifecycle tracking
│   ├── PENDING/
│   ├── IN_PROGRESS/
│   └── DONE/
└── templates/              # [NEW] Templates for plans, tasks, reviews, etc.
    ├── P-template.md
    ├── R-template.md
    ├── T-template.md
    ├── UR-template.md
    ├── TEST-template.md
    └── REPORT-template.md
```

---

## 3. Giriş Kontratı (Deterministic Entry Contract)

Every AI agent entering the repository must run the following deterministic sequence:

1. **Synchronize:** Execute `git pull --rebase` to fetch the latest whiteboard status.
2. **Scan State:** Read [STATE.md](file:///c:/Users/utkuc/Downloads/efloud-bot/LLTODO/STATE.md) and [SCOREBOARD.md](file:///c:/Users/utkuc/Downloads/efloud-bot/LLTODO/SCOREBOARD.md) to understand current progress and agent roles.
3. **Check Assignment:** Scan `LLTODO/tasks/PENDING/` for files where `assigned_to` matches `<my-role>` (or proxy-appropriate exceptions).
4. **Claim Task:** Move the task file from `PENDING/` to `IN_PROGRESS/` and update `status: IN_PROGRESS` inside the task frontmatter. Commit and push this claim instantly.
5. **Execute:** Follow the task specification exactly. Do not do out-of-scope work or override another agent's target files.
6. **Log & Report:**
   - Create a session report file under `reports/<agent>/YYYY-MM-DD-<summary>.md` describing what was built, what succeeded/failed, and what tests ran.
   - If this task spawns subsequent tasks, create them in `tasks/PENDING/`.
7. **Complete Task:** Move the task file from `IN_PROGRESS/` to `DONE/`.
8. **Update State:** Write the new status in [STATE.md](file:///c:/Users/utkuc/Downloads/efloud-bot/LLTODO/STATE.md) (e.g. next actions, stage changes).
9. **Surgical Commit & Push:** Commit only the code changed and the updated LLTODO files. Push immediately.
10. **Re-schedule or Relay:** Use self-scheduling capabilities (timers) if available, or write a final prompt summarizing the handover for the next agent.

---

## 4. Deliverables Details

### 4.1. `STATE.md` Schema
A centralized status dashboard representing active epics, status of plans, reviews, tasks, and specifying whose turn it is.

Format:
```markdown
# LLTODO System State

Last Updated: YYYY-MM-DD HH:MM:SS (UTC+X)

## 🎯 Active Epic
- **Plan ID:** P-XXX
- **Title:** Epic Title
- **Current Phase:** PLAN | CONSENSUS | IMPLEMENT | ULTRAREVIEW | CROSSTEST
- **Next Action / Ball Holder:** @agent_name

## 📊 Phase Roadmap
- [x] FAZ 1: PLAN (P-XXX)
- [/] FAZ 2: CONSENSUS (R-XXX-claude, R-XXX-gemini)
- [ ] FAZ 3: IMPLEMENT (T-XXX, T-YYY)
- [ ] FAZ 4: ULTRAREVIEW (UR-XXX)
- [ ] FAZ 5: CROSSTEST (TEST-XXX)

## 📋 Task Matrix Summary
- **PENDING:** N tasks
- **IN_PROGRESS:** M tasks
- **DONE:** K tasks
```

### 4.2. `SCOREBOARD.md` Schema
Tracks performance and specialization metrics across the crew.

Format:
```markdown
# Agent Scoreboard

| Agent | Specialty | Tasks Completed | Avg Review Score | Reviews Done | Active Streak |
|---|---|---|---|---|---|
| **hermes** | Kod, plan, terminal, deploy | 0 | - | 0 | 0 |
| **claude** | Review, kod analizi, PR | 0 | - | 0 | 0 |
| **gemini** | Görsel analiz, büyük context | 0 | - | 0 | 0 |
| **manus** | Browser automation, QA | 0 | - | 0 | 0 |
| **codex** | Second opinion, challenge | 0 | - | 0 | 0 |
```

### 4.3. Templates (`LLTODO/templates/`)
Markdown files with explicit frontmatter constraints to ensure parsed inputs are consistent.
- `P-template.md`: Plan template. Contains plan metadata, objectives, list of task assignments, required tools, and risk assessments.
- `R-template.md`: Review template. Contains decision (`APPROVE | CHANGES_REQUESTED | REJECT`), confidence (0-10), findings table.
- `T-template.md`: Task template. Contains task specifications, dependencies, and expected deliverables.
- `UR-template.md`: UltraReview template. Contains final quality check validations and bug lists.
- `TEST-template.md`: Cross-testing validation checklist.
- `REPORT-template.md`: Standard daily run report.

### 4.4. Agent Prompts (`LLTODO/PROMPT-*.md`)
Dedicated prompt files telling each agent role (Hermes, Claude, Gemini) how to navigate the repository, fulfill their specific role (e.g., tie-breaker for Gemini, deep reviewer for Claude, planner/coder for Hermes), and enforce the v2 workflow rules.

---

## 5. Migration of P-001 Epic

To test the system immediately, the existing P-001 Epic (u2algo Master Plan) and its pending reviews (R-001 for Claude, R-002 for Gemini) will be migrated to the new v2 schema.
- **P-001**: Update frontmatter and section layout to match the v2 template.
- **R-001/R-002 Tasks**: Update files inside `tasks/PENDING/` to match `T-template.md` structure.

---

## 6. Verification Plan

1. **Ruff / Syntax Checks:** Run formatting validation on markdown and any generated script templates.
2. **State and Directory Integrity:** Verify all directories exist and templates load correctly.
3. **Consensus Validation:** Ensure the migrated R-001 and R-002 tasks successfully target the migrated P-001 plan.
