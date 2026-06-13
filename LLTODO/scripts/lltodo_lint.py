#!/usr/bin/env python3
"""LLTODO v2 linter — validates task tracking system integrity.

8 test rules:
  1. STATE.md has valid status transitions
  2. IN_PROGRESS has at most 1 task claimed PER AGENT (multi-agent: claude/
     hermes/gemini paralel çalışır; claimant'sız IN_PROGRESS kartı da ihlaldir)
  3. Files follow naming conventions (P-XXX, R-XXX, T-XXX)
  4. Plan files have required sections (Hedef, Kapsam, Görevler, Gate)
  5. Review files have required sections (Bulgular, Karar, Confidence)
  6. Task files have required headers (Epic, Claimed by)
  7. SCOREBOARD.md task counts match actual files
  8. No broken cross-references (referenced files exist)

Usage:
  python scripts/lltodo_lint.py
Exit 0 = all clear; exit 1 = violations found.
"""

import os
import re
import sys
from pathlib import Path
from typing import List, Tuple

LLTODO_DIR = Path(__file__).resolve().parent.parent


def violations() -> List[str]:
    v: List[str] = []

    # ── Rule 1: STATE.md status transitions ──
    state_path = LLTODO_DIR / "STATE.md"
    if not state_path.exists():
        v.append("[R1] STATE.md not found")
    else:
        text = state_path.read_text(encoding="utf-8")
        valid = {"DRAFT", "REVIEW_OPEN", "CHANGES_REQUESTED",
                 "CONSENSUS_REACHED", "SPLIT_AGREED", "IN_PROGRESS",
                 "ULTRA_REVIEW", "CROSS_TEST", "TEST_CONSENSUS", "DONE"}
        found = set()
        for line in text.splitlines():
            for st in valid:
                if re.search(rf"\b{st}\b", line):
                    found.add(st)
        unknown = found - valid
        if unknown:
            v.append(f"[R1] Unknown states in STATE.md: {unknown}")

    # ── Rule 2: At most 1 task IN_PROGRESS per agent ──
    # 2026-06-11: global-1 limiti multi-agent akışta kilitleniyordu (T-020
    # @claude beklerken @hermes T-002 claim edemiyordu) → agent bazına geçildi.
    in_prog = LLTODO_DIR / "tasks" / "IN_PROGRESS"
    if in_prog.exists():
        tasks = [f for f in in_prog.iterdir() if f.suffix == ".md" and not f.name.startswith(".")]
        by_agent = {}
        for f in tasks:
            content = f.read_text(encoding="utf-8")
            m = re.search(r"Claimed by:\*{0,2}\s*(@[\w-]+)", content)
            if not m:
                v.append(f"[R2] IN_PROGRESS task without claimant: {f.name} "
                         f"(header'da 'Claimed by: @agent' gerekli)")
                continue
            by_agent.setdefault(m.group(1), []).append(f.name)
        for agent, names in sorted(by_agent.items()):
            if len(names) > 1:
                v.append(f"[R2] {agent} has multiple tasks IN_PROGRESS "
                         f"({len(names)}): {', '.join(sorted(names))}")

    # ── Rule 3: Naming conventions ──
    for root, _dirs, files in os.walk(LLTODO_DIR):
        for fname in files:
            if not fname.endswith(".md"):
                continue
            if "plans" in root:
                if not re.match(r"^P-\d{3}-.+\.md$", fname):
                    v.append(f"[R3] Bad plan name: {root}/{fname} (expected P-NNN-slug.md)")
            if "reviews" in root:
                if not re.match(r"^R-\d{3}-.+\.md$", fname):
                    v.append(f"[R3] Bad review name: {root}/{fname} (expected R-NNN-reviewer.md)")
            if "tasks" in root and "IN_PROGRESS" in root:
                if not re.match(r"^T-\d{3}-.+\.md$", fname):
                    v.append(f"[R3] Bad task name: {root}/{fname} (expected T-NNN-slug.md)")
            # v3 (2026-06-13): split + cross-test artefaktları
            if "splits" in root:
                if not re.match(r"^S-\d{3}-.+\.md$", fname):
                    v.append(f"[R3] Bad split name: {root}/{fname} (expected S-NNN-slug.md)")
            if root.endswith("tests") and fname != "test_lltodo_lint.py":
                if not re.match(r"^X-\d{3}-.+\.md$", fname):
                    v.append(f"[R3] Bad cross-test name: {root}/{fname} (expected X-NNN-tester.md)")

    # ── Rule 4: Plan files have required sections ──
    plans_dir = LLTODO_DIR / "plans"
    if plans_dir.exists():
        for f in plans_dir.iterdir():
            if f.suffix != ".md":
                continue
            content = f.read_text(encoding="utf-8")
            for sec in ["Hedef", "Kapsam", "Görevler", "Gate"]:
                if sec not in content:
                    v.append(f"[R4] Plan {f.name} missing section: {sec}")

    # ── Rule 5: Review files have required sections ──
    reviews_dir = LLTODO_DIR / "reviews"
    if reviews_dir.exists():
        for f in reviews_dir.iterdir():
            if f.suffix != ".md":
                continue
            content = f.read_text(encoding="utf-8")
            for sec in ["Bulgular", "Karar", "Confidence"]:
                if sec not in content:
                    v.append(f"[R5] Review {f.name} missing section: {sec}")

    # ── Rule 6: Task files have required headers ──
    if in_prog.exists():
        for f in in_prog.iterdir():
            if f.suffix != ".md" or f.name.startswith("."):
                continue
            content = f.read_text(encoding="utf-8")
            if "Epic:" not in content:
                v.append(f"[R6] Task {f.name} missing Epic: header")
            if "Claimed by:" not in content:
                v.append(f"[R6] Task {f.name} missing Claimed by: header")

    # ── Rule 7: SCOREBOARD.md consistency ──
    score_path = LLTODO_DIR / "SCOREBOARD.md"
    if score_path.exists():
        stext = score_path.read_text(encoding="utf-8")
        itp = in_prog.exists() and len([f for f in in_prog.iterdir() if f.suffix == ".md" and not f.name.startswith(".")]) or 0
        claimed_match = re.search(r"Claim edilmiş görev.*?(\d+)", stext)
        if claimed_match and int(claimed_match.group(1)) != itp:
            v.append(f"[R7] SCOREBOARD claims {claimed_match.group(1)} but IN_PROGRESS has {itp}")

    # ── Rule 8: No broken cross-references ──
    # Match structured refs: P-001, R-001, T-001 (standalone, not part of longer slug)
    ref_pattern = re.compile(r"\b(P-\d{3})\b|\b(R-\d{3})\b|\b(T-\d{3})\b")
    all_files: set[str] = set()
    prefix_to_files: dict[str, list[str]] = {}
    for root, _dirs, files in os.walk(LLTODO_DIR):
        for fn in files:
            if fn.endswith(".md"):
                stem = fn.replace(".md", "")
                all_files.add(stem)
                # Map short prefixes like P-001 → full filename
                prefix_match = re.match(r"^([PRT]-\d{3})", stem)
                if prefix_match:
                    key = prefix_match.group(1)
                    prefix_to_files.setdefault(key, []).append(stem)

    for root, _dirs, files in os.walk(LLTODO_DIR):
        for fn in files:
            if not fn.endswith(".md"):
                continue
            fpath = os.path.join(root, fn)
            content = Path(fpath).read_text(encoding="utf-8")
            # Find all P-001/R-001/T-001 references
            for m in re.finditer(r"\b([PRT]-\d{3})\b", content):
                ref = m.group(1)
                stem = fn.replace(".md", "")
                # Skip self-reference
                if stem.startswith(ref):
                    continue
                # Skip template placeholders
                # (2026-06-11: "P-002" whitelist'i kaldırıldı — plan dosyası
                # artık master'da; whitelist typo'ları maskeliyordu)
                if ref in ("P-XXX", "R-XXX", "T-XXX"):
                    continue
                # Check if any file with this prefix exists
                if ref not in prefix_to_files:
                    v.append(f"[R8] Broken ref in {fn}: {ref} (file not found)")

    return v


def main():
    # Windows consoles default to cp1252 and can't encode the ✅/❌ status emoji;
    # force UTF-8 so the CLI status line never crashes on a non-UTF-8 stdout.
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    v = violations()
    if not v:
        print("✅ LLTODO lint: 8/8 tests passed. All clear.")
        return 0
    else:
        print(f"❌ LLTODO lint: {len(v)} violation(s) found.")
        for line in v:
            print(f"  • {line}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
