#!/usr/bin/env python3
"""LLTODO frontmatter/schema linter.

Validates the YAML frontmatter of LLTODO coordination artifacts against the
schemas in docs/superpowers/specs/2026-06-09-lltodo-v2-consensus-pipeline-design.md (§12).

Usage:
    python scripts/lltodo_lint.py [PATH ...]   # default: LLTODO/
Exit 0 if all pass, 1 if any fail, 2 on setup error.
Files under LLTODO/templates/ are linted in lenient "template mode":
placeholder values like <XXX> or "A | B | C" option lists are allowed; only key
presence is checked.
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
                              "STRONG_CONSENSUS", "REVISING", "REJECTED",
                              "IMPLEMENTING", "DONE"]},
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
# Order matters: longer/more-specific prefixes first.
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
    if "/ultrareviews/" in posix:
        return "ultrareview"
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
    try:
        data = yaml.safe_load(text[3:end])
    except yaml.YAMLError:
        return None
    return data if isinstance(data, dict) else None


def is_placeholder(value) -> bool:
    """True for template placeholders: <XXX> or option lists like 'A | B'."""
    if not isinstance(value, str):
        return False
    v = value.strip()
    if v.startswith("<") and v.endswith(">"):
        return True
    if "|" in v:  # template option list, e.g. "APPROVE | CHANGES_REQUESTED"
        return True
    return False


def lint_file(path: Path, template_mode: bool = False) -> list[str]:
    """Return a list of error strings (empty = pass)."""
    atype = detect_type(path)
    if atype is None:
        return []  # README, prompts, SCOREBOARD, STATE: no strict schema
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
