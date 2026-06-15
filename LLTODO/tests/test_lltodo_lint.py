#!/usr/bin/env python3
"""Tests for lltodo_lint.py — validates all 8 lint rules."""

import os
import sys
import tempfile
import shutil
from pathlib import Path

# Add parent dir to path for import
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import lltodo_lint


def make_lltodo_structure(base: Path, files: dict):
    """Create a minimal LLTODO structure from {relpath: content} dict."""
    for relpath, content in files.items():
        full = base / relpath
        full.parent.mkdir(parents=True, exist_ok=True)
        full.write_text(content, encoding="utf-8")


def test_r1_valid_states():
    """R1: STATE.md with valid status transitions should pass."""
    with tempfile.TemporaryDirectory() as td:
        base = Path(td)
        make_lltodo_structure(base, {
            "STATE.md": "P-001: CONSENSUS_REACHED\nP-001: IN_PROGRESS\n",
            "SCOREBOARD.md": "Toplam görev | 0",
        })
        old = lltodo_lint.LLTODO_DIR
        lltodo_lint.LLTODO_DIR = base
        try:
            v = lltodo_lint.violations()
            r1 = [x for x in v if x.startswith("[R1]")]
            assert not r1, f"Unexpected R1 violations: {r1}"
        finally:
            lltodo_lint.LLTODO_DIR = old


def test_r2_at_most_one_in_progress():
    """R2: Should flag >1 task IN_PROGRESS for the SAME agent."""
    with tempfile.TemporaryDirectory() as td:
        base = Path(td)
        make_lltodo_structure(base, {
            "STATE.md": "P-001: IN_PROGRESS",
            "SCOREBOARD.md": "Claim edilmiş görev | 2",
            "tasks/IN_PROGRESS/T-001-test.md": "Epic: P-001\nClaimed by: @hermes",
            "tasks/IN_PROGRESS/T-002-test.md": "Epic: P-001\nClaimed by: @hermes",
        })
        old = lltodo_lint.LLTODO_DIR
        lltodo_lint.LLTODO_DIR = base
        try:
            v = lltodo_lint.violations()
            r2 = [x for x in v if x.startswith("[R2]")]
            assert len(r2) == 1, f"Expected 1 R2 violation, got: {r2}"
        finally:
            lltodo_lint.LLTODO_DIR = old


def test_r2_different_agents_may_claim_in_parallel():
    """R2: 2026-06-11 multi-agent kuralı — farklı agent'lar paralel claim edebilir."""
    with tempfile.TemporaryDirectory() as td:
        base = Path(td)
        make_lltodo_structure(base, {
            "STATE.md": "P-001: IN_PROGRESS",
            "SCOREBOARD.md": "Claim edilmiş görev | 2",
            # Markdown-bold header biçimi de (gerçek kart formatı) parse edilmeli:
            "tasks/IN_PROGRESS/T-020-test.md": "**Epic:** P-003\n**Claimed by:** @claude (2026-06-11)",
            "tasks/IN_PROGRESS/T-002-test.md": "Epic: P-001\nClaimed by: @hermes",
        })
        old = lltodo_lint.LLTODO_DIR
        lltodo_lint.LLTODO_DIR = base
        try:
            v = lltodo_lint.violations()
            r2 = [x for x in v if x.startswith("[R2]")]
            assert not r2, f"Different agents must be allowed in parallel, got: {r2}"
        finally:
            lltodo_lint.LLTODO_DIR = old


def test_r2_unclaimed_in_progress_flagged():
    """R2: IN_PROGRESS'te claimant'sız kart = ihlal."""
    with tempfile.TemporaryDirectory() as td:
        base = Path(td)
        make_lltodo_structure(base, {
            "STATE.md": "P-001: IN_PROGRESS",
            "SCOREBOARD.md": "Claim edilmiş görev | 1",
            "tasks/IN_PROGRESS/T-005-test.md": "Epic: P-001\nClaimed by: — (henüz claim edilmedi)",
        })
        old = lltodo_lint.LLTODO_DIR
        lltodo_lint.LLTODO_DIR = base
        try:
            v = lltodo_lint.violations()
            r2 = [x for x in v if x.startswith("[R2]")]
            assert len(r2) == 1 and "without claimant" in r2[0], f"Expected unclaimed violation, got: {r2}"
        finally:
            lltodo_lint.LLTODO_DIR = old


def test_r3_naming_conventions():
    """R3: Bad plan/review/task names should be flagged."""
    with tempfile.TemporaryDirectory() as td:
        base = Path(td)
        make_lltodo_structure(base, {
            "STATE.md": "P-001: DRAFT",
            "SCOREBOARD.md": "Claim edilmiş görev | 0",
            "plans/bad-name.md": "# Plan",
            "reviews/not-valid.md": "# Review",
        })
        old = lltodo_lint.LLTODO_DIR
        lltodo_lint.LLTODO_DIR = base
        try:
            v = lltodo_lint.violations()
            r3 = [x for x in v if x.startswith("[R3]")]
            assert len(r3) >= 1, f"Expected R3 violations, got: {r3}"
        finally:
            lltodo_lint.LLTODO_DIR = old


def test_r4_plan_required_sections():
    """R4: Plans missing required sections should be flagged."""
    with tempfile.TemporaryDirectory() as td:
        base = Path(td)
        make_lltodo_structure(base, {
            "STATE.md": "P-001: DRAFT",
            "SCOREBOARD.md": "Claim edilmiş görev | 0",
            "plans/P-001-test.md": "# Plan\nJust some text.\nNo real sections.",
        })
        old = lltodo_lint.LLTODO_DIR
        lltodo_lint.LLTODO_DIR = base
        try:
            v = lltodo_lint.violations()
            r4 = [x for x in v if x.startswith("[R4]")]
            assert len(r4) >= 1, f"Expected R4 violations, got: {r4}"
        finally:
            lltodo_lint.LLTODO_DIR = old


def test_r5_review_required_sections():
    """R5: Reviews missing required sections should be flagged."""
    with tempfile.TemporaryDirectory() as td:
        base = Path(td)
        make_lltodo_structure(base, {
            "STATE.md": "P-001: REVIEW_OPEN",
            "SCOREBOARD.md": "Claim edilmiş görev | 0",
            "reviews/R-001-test.md": "# Review\nNo sections here.",
        })
        old = lltodo_lint.LLTODO_DIR
        lltodo_lint.LLTODO_DIR = base
        try:
            v = lltodo_lint.violations()
            r5 = [x for x in v if x.startswith("[R5]")]
            assert len(r5) >= 1, f"Expected R5 violations, got: {r5}"
        finally:
            lltodo_lint.LLTODO_DIR = old


def test_r6_task_required_headers():
    """R6: Tasks missing Epic:/Claimed by: should be flagged."""
    with tempfile.TemporaryDirectory() as td:
        base = Path(td)
        make_lltodo_structure(base, {
            "STATE.md": "P-001: IN_PROGRESS",
            "SCOREBOARD.md": "Claim edilmiş görev | 1",
            "tasks/IN_PROGRESS/T-001-test.md": "# Task\nNo headers.",
        })
        old = lltodo_lint.LLTODO_DIR
        lltodo_lint.LLTODO_DIR = base
        try:
            v = lltodo_lint.violations()
            r6 = [x for x in v if x.startswith("[R6]")]
            assert len(r6) >= 2, f"Expected 2 R6 violations, got: {r6}"
        finally:
            lltodo_lint.LLTODO_DIR = old


def test_r7_scoreboard_counts():
    """R7: SCOREBOARD claims should match actual IN_PROGRESS count."""
    with tempfile.TemporaryDirectory() as td:
        base = Path(td)
        make_lltodo_structure(base, {
            "STATE.md": "P-001: IN_PROGRESS",
            "SCOREBOARD.md": "Claim edilmiş görev | 5",
            "tasks/IN_PROGRESS/T-001-test.md": "Epic: P-001\nClaimed by: @hermes",
        })
        old = lltodo_lint.LLTODO_DIR
        lltodo_lint.LLTODO_DIR = base
        try:
            v = lltodo_lint.violations()
            r7 = [x for x in v if x.startswith("[R7]")]
            assert len(r7) == 1, f"Expected 1 R7 violation, got: {r7}"
        finally:
            lltodo_lint.LLTODO_DIR = old


def test_r8_broken_references():
    """R8: References to non-existent files should be flagged."""
    with tempfile.TemporaryDirectory() as td:
        base = Path(td)
        make_lltodo_structure(base, {
            "STATE.md": "Ref: P-999-does-not-exist.md\nP-001: DRAFT",
            "SCOREBOARD.md": "Claim edilmiş görev | 0",
        })
        old = lltodo_lint.LLTODO_DIR
        lltodo_lint.LLTODO_DIR = base
        try:
            v = lltodo_lint.violations()
            r8 = [x for x in v if x.startswith("[R8]")]
            assert len(r8) >= 1, f"Expected R8 violations, got: {r8}"
        finally:
            lltodo_lint.LLTODO_DIR = old


def test_r1_v3_states_valid():
    """R1 (v3): SPLIT_AGREED / CROSS_TEST / TEST_CONSENSUS geçerli sayılmalı."""
    with tempfile.TemporaryDirectory() as td:
        base = Path(td)
        make_lltodo_structure(base, {
            "STATE.md": "P-001: SPLIT_AGREED\nP-001: CROSS_TEST\nP-001: TEST_CONSENSUS\n",
            "SCOREBOARD.md": "Claim edilmiş görev | 0",
        })
        old = lltodo_lint.LLTODO_DIR
        lltodo_lint.LLTODO_DIR = base
        try:
            r1 = [x for x in lltodo_lint.violations() if x.startswith("[R1]")]
            assert not r1, f"v3 states must be valid, got: {r1}"
        finally:
            lltodo_lint.LLTODO_DIR = old


def test_r3_v3_split_and_crosstest_naming():
    """R3 (v3): splits/ S-NNN ve tests/ X-NNN dışı .md adları flag'lenmeli."""
    with tempfile.TemporaryDirectory() as td:
        base = Path(td)
        make_lltodo_structure(base, {
            "STATE.md": "P-001: SPLIT_AGREED",
            "SCOREBOARD.md": "Claim edilmiş görev | 0",
            "splits/bad-split.md": "# nope",
            "tests/bad-crosstest.md": "# nope",
            # Doğru adlar ihlal ÜRETMEMELİ:
            "splits/S-001-ok.md": "# ok",
            "tests/X-001-claude.md": "# ok",
        })
        old = lltodo_lint.LLTODO_DIR
        lltodo_lint.LLTODO_DIR = base
        try:
            r3 = [x for x in lltodo_lint.violations() if x.startswith("[R3]")]
            assert any("bad-split.md" in x for x in r3), f"split naming not flagged: {r3}"
            assert any("bad-crosstest.md" in x for x in r3), f"cross-test naming not flagged: {r3}"
            assert not any("S-001-ok.md" in x or "X-001-claude.md" in x for x in r3), \
                f"valid v3 names wrongly flagged: {r3}"
        finally:
            lltodo_lint.LLTODO_DIR = old


if __name__ == "__main__":
    # Windows konsolu cp1252 — emoji status satırları crash etmesin
    # (lltodo_lint.py main()'indeki fix'in aynısı; PR #172/#177 pattern'i).
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    tests = [
        test_r1_valid_states,
        test_r2_at_most_one_in_progress,
        test_r2_different_agents_may_claim_in_parallel,
        test_r2_unclaimed_in_progress_flagged,
        test_r3_naming_conventions,
        test_r4_plan_required_sections,
        test_r5_review_required_sections,
        test_r6_task_required_headers,
        test_r7_scoreboard_counts,
        test_r8_broken_references,
        test_r1_v3_states_valid,
        test_r3_v3_split_and_crosstest_naming,
    ]
    passed = 0
    failed = 0
    for t in tests:
        try:
            t()
            print(f"  ✅ {t.__name__}")
            passed += 1
        except AssertionError as e:
            print(f"  ❌ {t.__name__}: {e}")
            failed += 1
        except Exception as e:
            print(f"  💥 {t.__name__}: {e}")
            failed += 1

    print(f"\n{'✅' if failed == 0 else '❌'} {passed}/{len(tests)} tests passed.")
    sys.exit(0 if failed == 0 else 1)
