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


def test_is_placeholder():
    assert L.is_placeholder("<agent>") is True
    assert L.is_placeholder("APPROVE | CHANGES_REQUESTED | REJECT") is True
    assert L.is_placeholder("APPROVE") is False


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
