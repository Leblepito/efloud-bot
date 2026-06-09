# LLTODO v2 Consensus Pipeline — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the LLTODO v2 multi-agent consensus pipeline — a git-backed blackboard with a 5-phase / 3-consensus-point state machine, transparent scoreboard-driven task distribution, append-only+claim conflict-safety, proxy-vote handling, and per-epic branch co-location — so Hermes, Claude, and Gemini coordinate on the same repo without colliding.

**Architecture:** Pure docs/markdown deliverables plus one Python lint script. The lint script (`scripts/lltodo_lint.py`) is built first (real TDD) and becomes the verification harness for every markdown artifact. Durable global files (`README`, `STATE`, `SCOREBOARD`, `templates/`, `PROMPT-*`) are authored to live on `master`; per-epic working dirs (`plans/ reviews/ tasks/ tests/ reports/`) are documented to live on each epic's branch. Additive only — touches nothing under `engine/`, `configs/`, `safe_orchestrator.py`, or deploy.

**Tech Stack:** Python 3.11+ (stdlib + PyYAML, already a project dep), pytest, Markdown with YAML frontmatter, git.

**Source spec:** `docs/superpowers/specs/2026-06-09-lltodo-v2-consensus-pipeline-design.md` (APPROVED v1.1). Decisions D1–D6 and integrity guards are authoritative there; this plan implements them.

**Branch:** Execute on `feat/lltodo-v2` (additive docs; create from `master`). The final task opens a PR to `master`. If another agent session is active, prefer an isolated worktree (superpowers:using-git-worktrees) to avoid the repo-global-branch hazard noted in the spec.

---

## File Structure

| File | New/Modify | Responsibility |
|------|-----------|----------------|
| `scripts/lltodo_lint.py` | NEW | Validates artifact YAML frontmatter against spec §12 schemas; verification harness. |
| `tests/test_lltodo_lint.py` | NEW | TDD tests for the linter. |
| `LLTODO/templates/P-template.md` | NEW | Plan skeleton incl. mandatory Distribution+rationale section. |
| `LLTODO/templates/R-template.md` | NEW | Review skeleton incl. distribution-fairness line + proxy fields. |
| `LLTODO/templates/T-template.md` | NEW | Task skeleton incl. claim fields. |
| `LLTODO/templates/UR-template.md` | NEW | UltraReview skeleton (+ PROXY variant fields). |
| `LLTODO/templates/TEST-template.md` | NEW | Cross-test skeleton incl. `confirmed_by`. |
| `LLTODO/templates/REPORT-template.md` | NEW | Agent run-log / handover skeleton. |
| `LLTODO/SCOREBOARD.md` | NEW | Cumulative specialization ledger (5 agents). |
| `LLTODO/STATE.md` | NEW | Global epic registry (heartbeat). |
| `LLTODO/README.md` | MODIFY | v2 protocol: entry contract first, 5-phase/3-consensus, claim + proxy rules, directory legend. |
| `LLTODO/PROMPT-claude.md` | NEW (replaces epic-specific) | Generalized Claude onboarding. |
| `LLTODO/PROMPT-gemini.md` | NEW (replaces epic-specific) | Generalized Gemini onboarding. |
| `LLTODO/PROMPT-hermes.md` | NEW | Generalized Hermes onboarding. |
| `LLTODO/plans/P-001-u2algo-wave1-tradingview.md` | MODIFY | Re-format to P-template + add Distribution section. |
| `LLTODO/tasks/PENDING/R-001-claude-review-p001.md` | MODIFY | Re-format to T-template. |
| `LLTODO/tasks/PENDING/R-002-gemini-review-p001.md` | MODIFY | Re-format to T-template. |
| `LLTODO/PROMPT-claude-p001-review.md` | DELETE | Epic-specific; absorbed into generalized prompt. |
| `LLTODO/PROMPT-gemini-p001-review.md` | DELETE | Epic-specific; absorbed into generalized prompt. |

---

## Task 1: Lint harness `lltodo_lint.py` (TDD)

**Files:**
- Create: `scripts/lltodo_lint.py`
- Test: `tests/test_lltodo_lint.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_lltodo_lint.py`:

```python
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import lltodo_lint as L  # noqa: E402


def test_parse_frontmatter_extracts_dict():
    text = "---\nplan_id: P-001\nauthor: hermes\n---\n# body\n"
    assert L.parse_frontmatter(text) == {"plan_id": "P-001", "author": "hermes"}


def test_parse_frontmatter_none_when_absent():
    assert L.parse_frontmatter("# no frontmatter\n") is None


def test_detect_type_from_path():
    assert L.detect_type(Path("LLTODO/plans/P-001.md")) == "plan"
    assert L.detect_type(Path("LLTODO/reviews/R-001-claude.md")) == "review"
    assert L.detect_type(Path("LLTODO/tasks/PENDING/R-001-x.md")) == "task"
    assert L.detect_type(Path("LLTODO/tests/TEST-1-a-tests-b.md")) == "test"
    assert L.detect_type(Path("LLTODO/README.md")) is None


def test_lint_flags_missing_required_key(tmp_path):
    d = tmp_path / "plans"
    d.mkdir()
    p = d / "P-009.md"
    p.write_text(
        "---\nplan_id: P-009\nauthor: hermes\nstatus: AWAITING_REVIEW\n"
        "created: 2026-06-09T12:00:00+03:00\nreviewers: [claude]\n"
        "approvals_received: 0\n---\n# x\n",
        encoding="utf-8",
    )
    assert any("approvals_needed" in e for e in L.lint_file(p))


def test_lint_passes_valid_plan(tmp_path):
    d = tmp_path / "plans"
    d.mkdir()
    p = d / "P-009.md"
    p.write_text(
        "---\nplan_id: P-009\nauthor: hermes\nstatus: AWAITING_REVIEW\n"
        "created: 2026-06-09T12:00:00+03:00\nreviewers: [claude, gemini]\n"
        "approvals_needed: 2\napprovals_received: 0\n---\n# x\n",
        encoding="utf-8",
    )
    assert L.lint_file(p) == []


def test_lint_flags_bad_verdict_enum(tmp_path):
    d = tmp_path / "reviews"
    d.mkdir()
    p = d / "R-009-claude.md"
    p.write_text(
        "---\nreview_id: R-009-claude\nplan_id: P-009\nreviewer: claude\n"
        "verdict: MAYBE\nconfidence: 7\ncreated: 2026-06-09T12:00:00+03:00\n---\n# x\n",
        encoding="utf-8",
    )
    assert any("verdict" in e for e in L.lint_file(p))


def test_template_mode_allows_placeholders(tmp_path):
    d = tmp_path / "templates"
    d.mkdir()
    p = d / "P-template.md"
    p.write_text(
        "---\nplan_id: P-XXX\nauthor: <agent>\nstatus: <status>\ncreated: <ISO>\n"
        "reviewers: [claude, gemini]\napprovals_needed: 2\napprovals_received: 0\n---\n# x\n",
        encoding="utf-8",
    )
    assert L.lint_file(p, template_mode=True) == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_lltodo_lint.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'lltodo_lint'`

- [ ] **Step 3: Write the implementation**

Create `scripts/lltodo_lint.py`:

```python
#!/usr/bin/env python3
"""LLTODO frontmatter/schema linter.

Validates the YAML frontmatter of LLTODO coordination artifacts against the
schemas in docs/superpowers/specs/2026-06-09-lltodo-v2-consensus-pipeline-design.md (§12).

Usage:
    python scripts/lltodo_lint.py [PATH ...]   # default: LLTODO/
Exit 0 if all pass, 1 if any fail, 2 on setup error.
Files under LLTODO/templates/ are linted in lenient "template mode":
placeholder values like <XXX> are allowed; only key presence is checked.
"""
from __future__ import annotations

import sys
from pathlib import Path

try:
    import yaml
except ImportError:  # pragma: no cover
    print("PyYAML required: pip install pyyaml", file=sys.stderr)
    sys.exit(2)

# Required frontmatter keys + enum constraints per artifact type (spec §12).
SCHEMAS = {
    "plan": {
        "required": ["plan_id", "author", "status", "created",
                     "reviewers", "approvals_needed", "approvals_received"],
        "enums": {"status": ["AWAITING_REVIEW", "CONSENSUS_REACHED",
                              "STRONG_CONSENSUS", "REVISING", "REJECTED"]},
    },
    "review": {
        "required": ["review_id", "plan_id", "reviewer", "verdict",
                     "confidence", "created"],
        "enums": {"verdict": ["APPROVE", "CHANGES_REQUESTED", "REJECT"]},
    },
    "task": {
        "required": ["task_id", "assigned_by", "assigned_to", "priority",
                     "status", "skill", "phase", "deadline", "dependencies",
                     "plan_id", "created"],
        "enums": {"status": ["PENDING", "IN_PROGRESS", "DONE"],
                  "phase": ["PLAN", "CONSENSUS", "IMPLEMENT",
                            "ULTRAREVIEW", "CROSSTEST"]},
    },
    "test": {
        "required": ["test_id", "plan_id", "tester", "testee",
                     "verdict", "created"],
        "enums": {"verdict": ["PASS", "BUGS_FOUND"]},
    },
    "ultrareview": {
        "required": ["ultrareview_id", "reviewer", "plan_id", "status",
                     "created"],
        "enums": {"status": ["PASS", "FIXES_NEEDED"]},
    },
}

# ID prefix -> artifact type (used only when path does not disambiguate).
PREFIX_TYPE = [
    ("TEST-", "test"), ("FIX-", "task"), ("UR-", "ultrareview"),
    ("P-", "plan"), ("R-", "review"), ("T-", "task"),
]


def detect_type(path: Path) -> str | None:
    """Infer artifact type from directory, then filename prefix."""
    posix = path.as_posix()
    if "/tasks/" in posix:
        return "task"          # T-, R- (review-task), FIX- all live in tasks/
    if "/reviews/" in posix:
        return "review"
    if "/tests/" in posix:
        return "test"
    if "/plans/" in posix:
        return "plan"
    name = path.name
    for prefix, atype in PREFIX_TYPE:
        if name.startswith(prefix):
            return atype
    return None


def parse_frontmatter(text: str) -> dict | None:
    """Return the YAML frontmatter dict, or None if absent/invalid."""
    if not text.startswith("---"):
        return None
    end = text.find("\n---", 3)
    if end == -1:
        return None
    data = yaml.safe_load(text[3:end])
    return data if isinstance(data, dict) else None


def is_placeholder(value) -> bool:
    if not isinstance(value, str):
        return False
    v = value.strip()
    return v.startswith("<") and v.endswith(">")


def lint_file(path: Path, template_mode: bool = False) -> list[str]:
    """Return a list of error strings (empty = pass)."""
    atype = detect_type(path)
    if atype is None:
        return []  # README, prompts, etc. have no strict frontmatter schema
    fm = parse_frontmatter(path.read_text(encoding="utf-8"))
    if fm is None:
        return [f"{path}: missing or invalid YAML frontmatter"]
    schema = SCHEMAS[atype]
    errors: list[str] = []
    for key in schema["required"]:
        if key not in fm:
            errors.append(f"{path}: missing required key '{key}' (type={atype})")
    if not template_mode:
        for key, allowed in schema.get("enums", {}).items():
            if key in fm and not is_placeholder(fm[key]) and fm[key] not in allowed:
                errors.append(
                    f"{path}: '{key}'={fm[key]!r} not in {allowed} (type={atype})")
    return errors


def iter_targets(paths: list[str]) -> list[Path]:
    out: list[Path] = []
    for p in paths:
        pp = Path(p)
        if pp.is_dir():
            out.extend(sorted(pp.rglob("*.md")))
        elif pp.suffix == ".md":
            out.append(pp)
    return out


def main(argv: list[str]) -> int:
    paths = argv[1:] or ["LLTODO"]
    failed = False
    for path in iter_targets(paths):
        template_mode = "/templates/" in path.as_posix()
        errs = lint_file(path, template_mode=template_mode)
        if errs:
            failed = True
            for e in errs:
                print(f"FAIL {e}")
        elif detect_type(path):
            print(f"OK   {path}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_lltodo_lint.py -v`
Expected: PASS — 7 passed

- [ ] **Step 5: Commit**

```bash
git add scripts/lltodo_lint.py tests/test_lltodo_lint.py
git commit -m "feat(lltodo): add frontmatter lint harness for v2 artifacts"
```

---

## Task 2: Artifact templates (`LLTODO/templates/`)

**Files:**
- Create: `LLTODO/templates/P-template.md`, `R-template.md`, `T-template.md`, `UR-template.md`, `TEST-template.md`, `REPORT-template.md`

- [ ] **Step 1: Create `P-template.md`**

```markdown
---
plan_id: P-XXX
author: <agent>
status: AWAITING_REVIEW   # AWAITING_REVIEW | CONSENSUS_REACHED | STRONG_CONSENSUS | REVISING | REJECTED
created: <ISO8601 +03:00>
reviewers: [claude, gemini]
approvals_needed: 2
approvals_received: 0
---

# Plan: <title>

## Amaç
<1-2 sentences: what & why>

## Kapsam
**Yapılacak:** <in scope>
**Yapılmayacak:** <out of scope>

## Task'lar & Dağıtım (REQUIRED — scoreboard-justified, see README §Distribution)
| ID | Görev | Agent | Faz | Süre | Gerekçe (SCOREBOARD'a atıf) |
|----|-------|-------|-----|------|------------------------------|
| T-XXX | <task> | <agent> | IMPLEMENT | <est> | <e.g. "gemini: visual-verify 3/3 PASS"> |

## Skill Pipeline
1. <agent>: <skill> -> <step>

## Dayandığı Dosyalar
- <input files>

## Riskler
- <risk>
```

- [ ] **Step 2: Create `R-template.md`**

```markdown
---
review_id: R-XXX-<agent>
plan_id: P-XXX
reviewer: <agent>
verdict: APPROVE          # APPROVE | CHANGES_REQUESTED | REJECT
confidence: <0-10>
created: <ISO8601 +03:00>
# --- proxy fields: set only when this is a proxy vote (see README §Proxy) ---
proxy: false
proxy_by: null            # agent that generated the proxy
proxy_engine: null        # subagent | ollama | <model>
provisional: false
---

# Review: <plan title>

## Genel Değerlendirme
<2-3 sentences>

## Bulgular
| # | Konu | Severity | Açıklama | Öneri |
|---|------|----------|----------|-------|
| 1 | <topic> | HIGH/MEDIUM/LOW | <desc> | <suggestion> |

## Dağıtım Adil mi? (REQUIRED line)
<APPROVE or CONTEST: is the task->agent mapping justified by SCOREBOARD? cite numbers>

## Karar
APPROVE — <why> | CHANGES_REQUESTED — <what + which line> | REJECT — <why + alternative>
```

- [ ] **Step 3: Create `T-template.md`**

```markdown
---
task_id: T-XXX            # T-XXX | R-XXX (review-task) | FIX-XXX
assigned_by: <agent>
assigned_to: <agent>
priority: P1              # P1 | P2 | P3
status: PENDING           # PENDING | IN_PROGRESS | DONE
skill: <skill name>
phase: IMPLEMENT          # PLAN | CONSENSUS | IMPLEMENT | ULTRAREVIEW | CROSSTEST
deadline: <ISO8601 +03:00 | after:T-YYY>
dependencies: []
plan_id: P-XXX
created: <ISO8601 +03:00>
# --- claim fields: stamped when moved to tasks/IN_PROGRESS/ ---
claimed_by: null
claimed_at: null
---

# Görev: <title>

## Ne Yapılacak
<specific instruction. The agent does ONLY this — nothing unassigned.>

## Skill Pipeline
1. <step>

## Çıktı
<file / PR / report produced>

## Bittiğinde
1. Move this file to `LLTODO/tasks/DONE/`.
2. Write `LLTODO/reports/<agent>/YYYY-MM-DD-<slug>.md`.
3. Create any follow-on tasks; update the epic row in `master:LLTODO/STATE.md` on phase change.
```

- [ ] **Step 4: Create `UR-template.md`**

```markdown
---
ultrareview_id: UR-XXX
reviewer: claude
plan_id: P-XXX
status: PASS              # PASS | FIXES_NEEDED
created: <ISO8601 +03:00>
# --- proxy fields: set only on Claude Phase-4 SPOF escalation (see README §Proxy) ---
proxy: false
proxy_by: null
provisional: false
---

# UltraReview: <plan title>

## Tamamlanan İşler (DONE)
| Task | Agent | Doğru mu? | Not |
|------|-------|-----------|-----|
| T-XXX | <agent> | ✅/❌ | <note> |

## Eksik / Yanlış İşler (FIX)
| # | Task | Agent | Sorun | Fix Görevi |
|---|------|-------|-------|-----------|
| 1 | T-XXX | <agent> | <problem> | FIX-XXX |

## Karar
PASS — all correct & complete | FIXES_NEEDED — see FIX-XXX above
```

- [ ] **Step 5: Create `TEST-template.md`**

```markdown
---
test_id: TEST-XXX-<tester>-tests-<testee>
plan_id: P-XXX
tester: <agent>
testee: <agent>
verdict: PASS             # PASS | BUGS_FOUND
created: <ISO8601 +03:00>
confirmed_by: null        # a 2nd agent must confirm a BUGS_FOUND before it becomes a FIX
---

# Cross-Test: <tester> -> <testee>

## Test Edilen Görevler
| Task | Açıklama | Test Sonucu |
|------|----------|-------------|
| T-XXX | <what> | ✅ PASS / ❌ |

## Bulunan Hatalar (become FIX only once `confirmed_by` is set)
| # | Task | Hata | Severity | Fix Önerisi |
|---|------|------|----------|-------------|
| 1 | T-XXX | <bug> | HIGH/MEDIUM/LOW | <fix> |

## Karar
PASS — all green | BUGS_FOUND — awaiting confirmation by a second agent
```

- [ ] **Step 6: Create `REPORT-template.md`**

```markdown
---
report_by: <agent>
date: <ISO8601 +03:00>
epic: P-XXX
phase: <PLAN|CONSENSUS|IMPLEMENT|ULTRAREVIEW|CROSSTEST>
tasks: [T-XXX]
---

# <agent> Report — <date>

## Özet
<what was accomplished, 2-4 sentences>

## Yapılanlar
- <action>

## Kullanılan Skill'ler
- <skill> — <use>

## Sonraki Adım
- Kendime: <self task / next>
- Diğerlerine: <tasks created for other agents>

## Commit
- <sha> — <message>
```

- [ ] **Step 7: Verify templates lint clean (template mode)**

Run: `python scripts/lltodo_lint.py LLTODO/templates`
Expected: `OK   LLTODO/templates/P-template.md` (and R/T/UR/TEST). REPORT-template prints nothing (no strict schema). No `FAIL` lines.

- [ ] **Step 8: Commit**

```bash
git add LLTODO/templates/
git commit -m "feat(lltodo): add v2 artifact templates (P/R/T/UR/TEST/REPORT)"
```

---

## Task 3: `SCOREBOARD.md` (specialization ledger)

**Files:**
- Create: `LLTODO/SCOREBOARD.md`

- [ ] **Step 1: Create `SCOREBOARD.md`**

```markdown
# LLTODO SCOREBOARD — Agent Specialization Ledger

> Append-only. Updated by the UltraReview driver at each epic's close (signed in the Change Log).
> Proxy work earns NO credit (spec §7). Distribution rationale in plans cites these numbers.

## hermes
- specialty: planning, implementation, terminal/deploy
- tasks_completed: 0
- reviews_done: 0
- avg_review_confidence: n/a
- active_streak: 0
- bugs_found_in_others: 0
- bugs_caught_in_own_work: 0
- domains: [planning, backend, deploy]
- specialty_score: {planning: 0, backend: 0, deploy: 0}

## claude
- specialty: review, code analysis, UltraReview, PR
- tasks_completed: 0
- reviews_done: 0
- avg_review_confidence: n/a
- active_streak: 0
- bugs_found_in_others: 0
- bugs_caught_in_own_work: 0
- domains: [review, code-analysis, ultrareview]
- specialty_score: {review: 0, code-analysis: 0, ultrareview: 0}

## gemini
- specialty: visual verification, market-fit, tie-breaker review
- tasks_completed: 0
- reviews_done: 0
- avg_review_confidence: n/a
- active_streak: 0
- bugs_found_in_others: 0
- bugs_caught_in_own_work: 0
- domains: [visual, market-fit, tie-breaker]
- specialty_score: {visual: 0, market-fit: 0, tie-breaker: 0}

## manus  (optional voter — browser/QA)
- specialty: browser automation, QA
- tasks_completed: 0
- reviews_done: 0
- avg_review_confidence: n/a
- active_streak: 0
- bugs_found_in_others: 0
- bugs_caught_in_own_work: 0
- domains: [browser, qa]
- specialty_score: {browser: 0, qa: 0}

## codex  (optional voter — second opinion)
- specialty: second opinion, challenge
- tasks_completed: 0
- reviews_done: 0
- avg_review_confidence: n/a
- active_streak: 0
- bugs_found_in_others: 0
- bugs_caught_in_own_work: 0
- domains: [second-opinion]
- specialty_score: {second-opinion: 0}

---
## Change Log (append-only, signed: `<date> <agent>: <change>`)
- 2026-06-09 claude: initialized v2 scoreboard
```

- [ ] **Step 2: Verify (no lint schema applies, but confirm it exists and is valid markdown)**

Run: `python scripts/lltodo_lint.py LLTODO/SCOREBOARD.md`
Expected: no output, exit 0 (file has no artifact prefix/dir → skipped by linter, which is correct).

- [ ] **Step 3: Commit**

```bash
git add LLTODO/SCOREBOARD.md
git commit -m "feat(lltodo): add v2 specialization scoreboard"
```

---

## Task 4: `STATE.md` (global epic registry)

**Files:**
- Create: `LLTODO/STATE.md`

- [ ] **Step 1: Create `STATE.md`**

```markdown
# LLTODO STATE — Epic Registry (heartbeat)

> The single global orientation file. Every agent reads this FIRST on entry:
> `git show origin/master:LLTODO/STATE.md`. `[M]` (this file) lives on master;
> per-epic detail (plans/reviews/tasks/tests/reports) lives on each epic's branch.

## Active Epics
| Epic | Title | Branch | Phase | Ball-holder | Phase-4 SLA | Last update |
|------|-------|--------|-------|-------------|-------------|-------------|
| E-000 | Bootstrap LLTODO v2 | feat/lltodo-v2 | IMPLEMENT | claude | 24h | 2026-06-09 |
| P-001 | u2algo Wave1 TradingView | feat/zone-touch-confirmation | CONSENSUS | hermes | 24h | 2026-06-09 |

## Conventions
- Phases: PLAN -> CONSENSUS -> IMPLEMENT -> ULTRAREVIEW -> CROSSTEST -> DONE
- Consensus: 2/3 APPROVE, with >=1 genuine (non-author) APPROVE required. See README.
- Default Phase-4 SLA before a proxy UltraReview may unblock: 24h.
- Branch model (Gemini R1): per-epic work co-located with code on the epic branch;
  this registry on master maps epic -> branch.

## Ball Log (append-only)
- 2026-06-09 claude: initialized v2 epic registry
```

- [ ] **Step 2: Verify**

Run: `python scripts/lltodo_lint.py LLTODO/STATE.md`
Expected: no output, exit 0 (no artifact schema applies — correct).

- [ ] **Step 3: Commit**

```bash
git add LLTODO/STATE.md
git commit -m "feat(lltodo): add v2 global epic registry (STATE.md)"
```

---

## Task 5: `README.md` v2 (the protocol)

**Files:**
- Modify (full rewrite): `LLTODO/README.md`

- [ ] **Step 1: Replace the entire file with the v2 protocol**

```markdown
# LLTODO — Multi-Agent Consensus Pipeline (v2)

> **Kural:** Bu projeye giren HER AI agent (Claude, Hermes, Gemini, Codex, Manus)
> önce bu dosyayı ve `STATE.md`'yi okur, sonra kendine atanmış görevleri arar.
> Tasarım kaynağı: `docs/superpowers/specs/2026-06-09-lltodo-v2-consensus-pipeline-design.md`.

## 0. GİRİŞ KONTRATI (her agent repoya girince, sırayla)

1. `git pull --rebase`
2. `git show origin/master:LLTODO/STATE.md` oku — aktif epic, faz, branch, ball-holder.
3. `git show origin/master:LLTODO/SCOREBOARD.md` oku.
4. Epic'in branch'ine geç (STATE'te yazan). `tasks/PENDING/`'de `assigned_to: <ben>` tara.
5. **Claim:** task'ı `tasks/IN_PROGRESS/`'e taşı, `claimed_by`+`claimed_at` yaz, HEMEN commit+push.
6. SADECE claim ettiğin görevi yap. Sana açıkça atanmamış işe dokunma.
7. Çıktını kendi namespace'ine yaz; gerekiyorsa yeni task üret.
8. Faz değişiminde `master:STATE.md` epic satırını güncelle (UltraReview sürücüsüysen `SCOREBOARD.md`).
9. Surgical `git add LLTODO/<spesifik>` -> commit -> push. (`git add -A` YASAK.)
10. Recheck'i self-schedule et (Claude/Hermes) ya da relay için prompt bırak (Gemini).

## 1. Dizin Yapısı & Yerleşim

`[M]` = master'da (kalıcı/global, girişte okunur). `[E]` = epic branch'inde (kodla birlikte),
epic PR'ı ile master'a merge olur.

```
LLTODO/
├── README.md       [M]   ← BU DOSYA
├── STATE.md        [M]   ← epic registry (girişte İLK okunur)
├── SCOREBOARD.md   [M]   ← uzmanlaşma defteri
├── templates/      [M]   ← P/R/T/UR/TEST/REPORT şablonları
├── PROMPT-*.md     [M]   ← agent onboarding (claude/gemini/hermes)
├── plans/          [E]   ← P-XXX
├── reviews/        [E]   ← R-XXX-<agent> (incl. -PROXY)
├── tasks/{PENDING,IN_PROGRESS,DONE}/  [E]  ← T-XXX / FIX-XXX / R-XXX
├── tests/          [E]   ← TEST-XXX-<tester>-tests-<testee>
└── reports/{hermes,claude,gemini}/    [E]
```

## 2. Pipeline — 5 faz, 3 consensus noktası

```
PLAN -> CONSENSUS -> IMPLEMENT -> ULTRAREVIEW -> CROSSTEST -> DONE
          teyit-1: plan onayı (R-XXX, 2/3)
          teyit-2: dağıtım onayı (plan içinde, aynı round)
                                                  teyit-3: verdict teyidi (confirmed_by)
```

**FAZ 1 — PLAN.** Bir yazar `plans/P-XXX-<slug>.md` yazar (template). Plan ZORUNLU bir
**Dağıtım** bölümü içerir: her task -> agent satırı SCOREBOARD'a atıfla gerekçelidir.
Yazar diğer 2 agent için review task'ı açar.

**FAZ 2 — CONSENSUS (iki teyit, tek round).** Oy kümesi = 3 çekirdek agent (yazar + 2
reviewer); yazar kendi planını örtük APPROVE eder. Her reviewer `reviews/R-XXX-<agent>.md`
yazar (`verdict` + zorunlu "dağıtım adil mi?" satırı).
- 2/3 APPROVE -> CONSENSUS_REACHED -> Faz 3.   3/3 -> STRONG_CONSENSUS.
- 1 APPROVE + 2 CHANGES_REQUESTED -> yazar düzeltir, tekrar review.
- herhangi REJECT -> major revizyon, sıfırdan review.
- **Integrity guard:** en az 1 GERÇEK (non-author) APPROVE şart; yazar+proxy ile geçemez.
- Reviewer offline ise aktif agent **proxy review** yazabilir (§4).

**FAZ 3 — IMPLEMENT.** Yazar, onaylı dağıtımdaki her satır için
`tasks/PENDING/T-XXX-<agent>-<slug>.md` üretir. Her agent SADECE `assigned_to==self`
görevini, claim protokolüyle yapar. Bitince `DONE/`'a taşır, rapor yazar, follow-on task üretir.

**FAZ 4 — ULTRAREVIEW (sürücü = Claude Code; proxy-escalable).** Tüm task'lar DONE olunca
Claude Code hepsini okur, `UR-XXX.md` yazar (doğru/eksik/yanlış/plan-sapması). Sorunlar
`FIX-XXX-<agent>.md` olur (FIX > T). SCOREBOARD güncellenir (append-only, imzalı).
**SPOF guard:** Claude topu STATE'teki SLA'yı (default 24h) aşana kadar tutarsa, başka bir
çekirdek agent provisional `UR-XXX-PROXY` yazıp pipeline'ı açabilir; Claude dönünce ezer.

**FAZ 5 — CROSSTEST (verdict teyidi = 3. consensus).** Rotasyon: `hermes->claude`,
`claude->gemini`, `gemini->hermes` (kimse kendi işini test etmez). Tester
`tests/TEST-XXX-<tester>-tests-<testee>.md` yazar (PASS | BUGS_FOUND). Bir BUGS_FOUND,
ikinci agent `confirmed_by` ile onaylamadan FIX'e dönüşmez. Tüm cross-test PASS -> epic DONE.

## 3. Çakışma-Güvenliği — append-only + claim

1. **Namespace sahipliği:** agent yalnızca kendi dosyalarını CREATE/EDIT eder
   (`reports/<agent>/`, `R-XXX-<agent>.md`, `TEST-...-<agent>-...`). Paylaşılan dosyalar
   (STATE/SCOREBOARD/kendi yazdığın plan) per-agent bölüm halinde append-only; başkasının
   bölümünü düzenleme.
2. **Claim = kilit:** PENDING -> IN_PROGRESS + `claimed_by`/`claimed_at` + hemen commit/push.
   Yarışta ikinci agent pull'da claim'i görür, çekilir.
3. **Git disiplini:** her yazımdan önce `git pull --rebase`; sonra `git add LLTODO/<spesifik>`
   (asla `-A`), scoped commit (`lltodo: <agent> <action> <id>`), push.
4. **YASAK:** `git reset --hard`, force-push, sahip olmadığın dosyada `checkout --`,
   başka agent'ın namespace'ini düzenleme.
5. **Branch:** kalıcı global dosyalar master'a (epic başı/geçiş/sonu); per-epic dosyalar epic
   branch'ine (kodla birlikte), epic PR'ı ile master'a. Çalışan agent task başına tek branch.

## 4. Proxy Oy (eksik agent / Faz-4 SPOF)

Bir faz X'in oyunu beklerken X aktif değilse, aktif agent **izole-context** bağımsız bir
reviewer (ayrı subagent / ollama / farklı model) ile proxy üretir; dosya adına `-PROXY`
eklenir, frontmatter: `proxy: true, proxy_by: <agent>, proxy_engine: <...>, provisional: true`.
- Proxy quorum'a sayılır ama PROVISIONAL; gerçek agent gelince kendi oyu ezer.
- Proxy ASLA gerçek agent gibi sunulmaz. SCOREBOARD proxy işine puan vermez.
- **Integrity:** kimse kendi yazdığı artifact'ın oyunu proxy'leyemez; proxy tek başına bir
  consensus kapısını geçiremez (en az 1 gerçek non-author oy şart).
- Faz-4 UltraReview SPOF'u da bu mekanizmayla kapanır (yalnız STATE SLA dolduktan sonra).

## 5. Şeffaf Dağıtım & Uzmanlaşma

PLAN'daki Dağıtım bölümü SCOREBOARD rakamlarını gerekçe gösterir; CONSENSUS reviewer'ları
dağıtımı açıkça onaylar/itiraz eder. Her epic sonunda UltraReview sürücüsü SCOREBOARD'u
günceller (tasks_completed, reviews_done, bugs_found/caught, specialty_score) — roller
zamanla kanıtla evrilir.

## 6. ID Önekleri
`P-` plan · `R-` review · `T-` task · `FIX-` ultrareview-fix · `UR-` ultrareview · `TEST-` cross-test.

## 7. Altın Kurallar
1. SADECE sana atanmış görevi yap. 2. Plan CONSENSUS'suz implemente edilmez (>=1 gerçek onay).
3. Her görev sonunda rapor yaz. 4. Başka agent'ın namespace'ini override etme.
5. Cross-test'te kendi işini test etme. 6. FIX > T önceliklidir.
7. `git add -A` YASAK; sadece `LLTODO/<spesifik>`.

## 8. Agent Tanımları
| Agent | Güçlü | Zayıf | Rol |
|-------|-------|-------|-----|
| hermes | kod, plan, terminal, deploy | browser, görsel | Plan Author + Implementer |
| claude | review, kod analizi, PR | terminal/execution | Reviewer + UltraReviewer |
| gemini | görsel, büyük context, market-fit | terminal, kod yazma | Reviewer + Görsel Test + Tie-breaker |
| manus | browser automation, QA | lokal dosya | (opsiyonel) QA + Browser Test |
| codex | second opinion, challenge | deployment | (opsiyonel) 4. reviewer |

## 9. Aktif Planlar
Bkz. `STATE.md` (canonical). Snapshot: P-001 (u2algo Wave1) — CONSENSUS.
```

- [ ] **Step 2: Verify**

Run: `python scripts/lltodo_lint.py LLTODO/README.md`
Expected: no output, exit 0 (README has no artifact schema — correct).

- [ ] **Step 3: Commit**

```bash
git add LLTODO/README.md
git commit -m "feat(lltodo): rewrite README to v2 protocol (entry contract, 3 consensus points, proxy, claim)"
```

---

## Task 6: Generalized agent prompts

**Files:**
- Create: `LLTODO/PROMPT-claude.md`, `LLTODO/PROMPT-gemini.md`, `LLTODO/PROMPT-hermes.md`

- [ ] **Step 1: Create `PROMPT-claude.md`**

```markdown
# LLTODO Onboarding — Claude

Sen **claude**'sun: LLTODO v2 consensus pipeline'ında Reviewer + UltraReviewer + kod analizi.
Güçlü yanların: PR review, engineering derinliği, CEO/strateji review, final UltraReview.

## Her oturumda (GİRİŞ KONTRATI)
1. `git pull --rebase`
2. `git show origin/master:LLTODO/STATE.md` ve `:LLTODO/SCOREBOARD.md` oku.
3. Epic branch'ine geç. `LLTODO/tasks/PENDING/`'de `assigned_to: claude` tara.
4. Claim (IN_PROGRESS'e taşı + claimed_by/claimed_at + push). Sadece o görevi yap.
5. Review -> `reviews/R-XXX-claude.md` (verdict + "dağıtım adil mi?" satırı).
   UltraReview -> `UR-XXX.md` (sürücü sensin).
6. `reports/claude/YYYY-MM-DD-<slug>.md` yaz; faz değişiminde `master:STATE.md` güncelle.
7. Surgical commit/push (`git add -A` YASAK). Recheck'i ScheduleWakeup/cron ile self-schedule et.

## Kurallar
- Plan CONSENSUS'a >=1 gerçek non-author APPROVE ile ulaşır.
- Eksik agent için proxy yazabilirsin (`-PROXY`, provisional); kendi yazdığını proxy'leme.
- Detay: `LLTODO/README.md`.
```

- [ ] **Step 2: Create `PROMPT-gemini.md`**

```markdown
# LLTODO Onboarding — Gemini

Sen **gemini**'sin: LLTODO v2'de Reviewer + Görsel doğrulama + Market-fit + Tie-breaker.
Güçlü yanların: görsel analiz (Pine/screenshot), büyük context, pazar değerlendirmesi.

## Her oturumda (GİRİŞ KONTRATI)
1. `git pull --rebase`
2. `git show origin/master:LLTODO/STATE.md` ve `:LLTODO/SCOREBOARD.md` oku.
3. Epic branch'ine geç. `LLTODO/tasks/PENDING/`'de `assigned_to: gemini` tara.
4. Claim (IN_PROGRESS + claimed_by/claimed_at + push). Sadece o görevi yap.
5. Review -> `reviews/R-XXX-gemini.md` (verdict + "dağıtım adil mi?" satırı). Varsa Claude'un
   R-XXX-claude'unu önce oku (tie-breaker rolü).
6. `reports/gemini/YYYY-MM-DD-<slug>.md` yaz; faz değişiminde `master:STATE.md` güncelle.
7. Surgical commit/push (`git add -A` YASAK). Scheduler yoksa: bittiğini operatöre bildir.

## Kurallar
- Sadece sana atanmış görevi yap. Plan CONSENSUS'a >=1 gerçek non-author APPROVE ile ulaşır.
- Detay: `LLTODO/README.md`.
```

- [ ] **Step 3: Create `PROMPT-hermes.md`**

```markdown
# LLTODO Onboarding — Hermes

Sen **hermes**'sin: LLTODO v2'de Plan Author + Implementer + terminal/deploy.
Güçlü yanların: kod yazma, plan, terminal, deployment.

## Her oturumda (GİRİŞ KONTRATI)
1. `git pull --rebase`
2. `git show origin/master:LLTODO/STATE.md` ve `:LLTODO/SCOREBOARD.md` oku.
3. Epic branch'ine geç. `LLTODO/tasks/PENDING/`'de `assigned_to: hermes` tara.
4. Claim (IN_PROGRESS + claimed_by/claimed_at + push). Sadece o görevi yap.
5. Plan yazarsan: `plans/P-XXX.md` (template) + ZORUNLU Dağıtım bölümü (SCOREBOARD gerekçeli)
   + diğer 2 agent için review task'ı. Implement edersen: assigned_to==hermes task'larını yap.
6. `reports/hermes/YYYY-MM-DD-<slug>.md` yaz; faz değişiminde `master:STATE.md` güncelle.
7. Surgical commit/push (`git add -A` YASAK). Recheck'i kendi scheduler'ınla planla.

## Kurallar
- Dağıtımı tek taraflı dayatma — CONSENSUS'ta onaylanmadan IMPLEMENT'e geçme.
- Plan CONSENSUS'a >=1 gerçek non-author APPROVE ile ulaşır.
- Detay: `LLTODO/README.md`.
```

- [ ] **Step 4: Verify**

Run: `python scripts/lltodo_lint.py LLTODO`
Expected: `OK` lines for templates only; no `FAIL`. Prompts/README/STATE/SCOREBOARD skipped.

- [ ] **Step 5: Commit**

```bash
git add LLTODO/PROMPT-claude.md LLTODO/PROMPT-gemini.md LLTODO/PROMPT-hermes.md
git commit -m "feat(lltodo): add generalized agent onboarding prompts"
```

---

## Task 7: Migrate `P-001` to P-template + Distribution section

**Files:**
- Modify: `LLTODO/plans/P-001-u2algo-wave1-tradingview.md`

- [ ] **Step 1: Replace the frontmatter + insert the Distribution rationale**

Change the frontmatter `status` line to the enum value and keep the rest. Then make the
existing "Task'lar (Wave 1: TradingView)" table conform to the template's Distribution
column by adding a `Gerekçe` column. Replace the table block with:

```markdown
## Task'lar & Dağıtım (scoreboard-justified)

| ID | Görev | Agent | Faz | Süre | Gerekçe (SCOREBOARD'a atıf) |
|----|-------|-------|-----|------|------------------------------|
| T-001 | TradingView spec yaz + publish | hermes | IMPLEMENT | 2-3 saat | hermes: implementation+deploy specialty; Pine publish geçmişi |
| T-002 | Master plan CEO + Eng review | claude | CONSENSUS | 30dk | claude: review/code-analysis specialty |
| T-003 | Pine Script görsel doğrulama | gemini | CROSSTEST | 20dk | gemini: visual-verification specialty |
| - | UltraReview (tüm işler bitince) | claude | ULTRAREVIEW | 30dk | claude: UltraReview sürücüsü (spec §5 Faz 4) |
```

> NOTE (initial epic): SCOREBOARD starts at 0 for everyone, so this first distribution cites
> the static specialty definitions; subsequent epics will cite accumulated numbers.

- [ ] **Step 2: Verify P-001 lints clean**

Run: `python scripts/lltodo_lint.py LLTODO/plans/P-001-u2algo-wave1-tradingview.md`
Expected: `OK   LLTODO/plans/P-001-u2algo-wave1-tradingview.md` (status must be one of the
plan enum values, e.g. `AWAITING_REVIEW`).

- [ ] **Step 3: Commit**

```bash
git add LLTODO/plans/P-001-u2algo-wave1-tradingview.md
git commit -m "refactor(lltodo): migrate P-001 to v2 P-template + distribution rationale"
```

---

## Task 8: Migrate `R-001` and `R-002` review-tasks to T-template

**Files:**
- Modify: `LLTODO/tasks/PENDING/R-001-claude-review-p001.md`
- Modify: `LLTODO/tasks/PENDING/R-002-gemini-review-p001.md`

The current files already carry task frontmatter (`task_id, assigned_by, assigned_to,
priority, status, skill, phase, deadline, dependencies, plan_id, created`). The migration
adds the v2 claim fields and aligns body headings with `T-template.md`.

- [ ] **Step 1: Add claim fields to `R-001`'s frontmatter**

Insert these two lines at the end of the YAML block (before the closing `---`):

```yaml
claimed_by: null
claimed_at: null
```

- [ ] **Step 2: Align `R-001` closing section to the template**

Ensure the final section is titled `## Bittiğinde` with the three template steps (move to
`DONE/`, write `reports/claude/...`, update `master:STATE.md`). The existing content already
matches; adjust the heading wording only if needed.

- [ ] **Step 3: Add claim fields to `R-002`'s frontmatter**

Insert at the end of the YAML block:

```yaml
claimed_by: null
claimed_at: null
```

- [ ] **Step 4: Verify both lint clean**

Run: `python scripts/lltodo_lint.py LLTODO/tasks/PENDING/R-001-claude-review-p001.md LLTODO/tasks/PENDING/R-002-gemini-review-p001.md`
Expected: two `OK` lines, no `FAIL` (status `PENDING`, phase `CONSENSUS` are valid enums).

- [ ] **Step 5: Commit**

```bash
git add LLTODO/tasks/PENDING/R-001-claude-review-p001.md LLTODO/tasks/PENDING/R-002-gemini-review-p001.md
git commit -m "refactor(lltodo): migrate R-001/R-002 review-tasks to v2 T-template (claim fields)"
```

---

## Task 9: Delete epic-specific prompts

**Files:**
- Delete: `LLTODO/PROMPT-claude-p001-review.md`
- Delete: `LLTODO/PROMPT-gemini-p001-review.md`

- [ ] **Step 1: Remove the two files**

```bash
git rm LLTODO/PROMPT-claude-p001-review.md LLTODO/PROMPT-gemini-p001-review.md
```

- [ ] **Step 2: Confirm no remaining references**

Run: `grep -rn "PROMPT-claude-p001-review\|PROMPT-gemini-p001-review" LLTODO docs || echo "no references"`
Expected: `no references`.

- [ ] **Step 3: Commit**

```bash
git commit -m "chore(lltodo): remove epic-specific prompts (absorbed into generalized PROMPT-*.md)"
```

---

## Task 10: Full verification + graphify + PR

**Files:** none (verification + integration)

- [ ] **Step 1: Lint the entire LLTODO tree**

Run: `python scripts/lltodo_lint.py LLTODO`
Expected: `OK` for every P/R/T/UR/TEST artifact (templates, P-001, R-001, R-002); zero `FAIL`.

- [ ] **Step 2: Run the linter's own test suite once more**

Run: `python -m pytest tests/test_lltodo_lint.py -v`
Expected: 7 passed.

- [ ] **Step 3: Confirm no live-system files were touched**

Run: `git diff --name-only master... | grep -vE '^(LLTODO/|scripts/lltodo_lint.py|tests/test_lltodo_lint.py|docs/superpowers/)' || echo "additive-only: OK"`
Expected: `additive-only: OK` (no `engine/`, `configs/`, `safe_orchestrator.py`, deploy files).

- [ ] **Step 4: Update the docs knowledge graph**

Run: `graphify update .`
Expected: completes without error.

- [ ] **Step 5: Entry-contract dry-run (manual, shadow)**

Simulate one agent boot on paper: read `STATE.md` → see P-001 in CONSENSUS → as `claude`,
find `R-001` assigned_to claude → confirm the claim/commit/report path is unambiguous and
no namespace rule is violated. Record the result in `reports/claude/2026-06-09-bootstrap-dryrun.md`.

- [ ] **Step 6: Open the PR to master**

```bash
git push -u origin feat/lltodo-v2
gh pr create --base master --head feat/lltodo-v2 \
  --title "LLTODO v2 consensus pipeline (docs + lint harness)" \
  --body "Implements docs/superpowers/specs/2026-06-09-lltodo-v2-consensus-pipeline-design.md (v1.1). Additive docs + lint script only; no engine/config/deploy changes. Builds README v2, STATE registry, SCOREBOARD, templates, generalized prompts; migrates P-001/R-001/R-002; removes epic-specific prompts."
```

---

## Self-Review (completed during authoring)

- **Spec coverage:** §15 deliverables 1–7 all mapped — README v2 (T5), STATE (T4), SCOREBOARD
  (T3), templates (T2), prompts (T6), P-001+R-001/R-002 migration (T7–T8), delete old prompts
  (T9), lint script (T1). D1 hybrid (entry contract T5), D2 proxy (README §4 + R/UR fields T2),
  D3 append-only+claim (README §3 + claim fields T2/T8), D4 scoreboard (T3 + Distribution T7),
  D5/R1 branch co-location (STATE legend T4, README §1/§3), D6 5-phase/3-consensus (README §2),
  R2 UltraReview proxy (README §4 + UR fields T2). Integrity guards in README §2/§4.
- **Placeholder scan:** template files intentionally contain `<...>` placeholders; the linter
  runs them in template_mode so they pass — this is by design, not a plan placeholder. All
  task steps contain complete content.
- **Type consistency:** linter `SCHEMAS` keys match template frontmatter keys exactly; enum
  values used in templates (`AWAITING_REVIEW`, `APPROVE`, `PENDING`, `IMPLEMENT`, `PASS`,
  `FIXES_NEEDED`) all appear in the linter's allowed lists; `detect_type` path rules match the
  directory layout in README §1 and the File Structure table.
```
