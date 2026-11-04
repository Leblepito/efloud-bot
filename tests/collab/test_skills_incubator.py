"""Quarantine guard for draft skills (collab/skills-incubator/).

skills/ is auto-loaded into every Claude Code session and preloaded by desk agents,
so an unreviewed skill there becomes behaviour. Drafts live in the incubator until a
review marks them promoted. A repeat of 645a5dc (drafts pushed straight into
skills/) must turn this suite red.
"""
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
INCUBATOR_DIR = ROOT / "collab" / "skills-incubator"
SKILLS_DIR = ROOT / "skills"
MODELS = {"claude-code", "hermes", "abacus"}
SKILL_STATUSES = {"draft", "in-review", "accepted", "rejected", "promoted"}
BANNER = "INCUBATOR TASLAĞI — AKTİF DEĞİL"
# Drafts quarantined from 645a5dc; they may only reappear in skills/ via promotion.
QUARANTINED = {
    "efloud-smc-concepts",
    "efloud-smc-setup-rules",
    "efloud-risk-management",
    "efloud-tradingview-integration",
    "eflood-tradingview-integration",
    "efloud-master-orchestrator",
}


def _split(path: Path) -> tuple[dict, str]:
    text = path.read_text(encoding="utf-8")
    assert text.startswith("---\n"), f"{path} must start with YAML frontmatter"
    _, fm, body = text.split("---\n", 2)
    data = yaml.safe_load(fm)
    assert isinstance(data, dict), f"{path} frontmatter must be a mapping"
    return data, body


INCUBATOR = sorted(p for p in INCUBATOR_DIR.glob("*") if p.is_dir())


def _status(skill_dir: Path) -> str:
    return _split(skill_dir / "REVIEW.md")[0].get("status")


def test_incubator_exists_with_readme():
    assert (INCUBATOR_DIR / "README.md").is_file()
    assert INCUBATOR, "incubator should hold the quarantined drafts"


@pytest.mark.parametrize("skill_dir", INCUBATOR, ids=lambda p: p.name)
def test_review_header(skill_dir):
    review = skill_dir / "REVIEW.md"
    assert review.is_file(), f"{skill_dir.name}: REVIEW.md missing"
    fm, _ = _split(review)
    assert fm.get("skill") == skill_dir.name
    assert fm.get("status") in SKILL_STATUSES
    assert fm.get("author") in MODELS


@pytest.mark.parametrize("skill_dir", INCUBATOR, ids=lambda p: p.name)
def test_skill_name_matches_folder_and_has_banner(skill_dir):
    skill = skill_dir / "SKILL.md"
    assert skill.is_file(), f"{skill_dir.name}: SKILL.md missing"
    fm, body = _split(skill)
    assert fm.get("name") == skill_dir.name, f"{skill_dir.name}: name: {fm.get('name')!r}"
    if _status(skill_dir) != "promoted":
        assert BANNER in body, f"{skill_dir.name}: INCUBATOR banner missing"


@pytest.mark.parametrize("skill_dir", INCUBATOR, ids=lambda p: p.name)
def test_unpromoted_draft_is_not_active(skill_dir):
    if _status(skill_dir) == "promoted":
        return
    assert not (SKILLS_DIR / skill_dir.name).exists(), (
        f"skills/{skill_dir.name} is active but its incubator review is "
        f"{_status(skill_dir)!r}, not 'promoted'"
    )


def test_quarantined_names_absent_from_skills_unless_promoted():
    promoted = {p.name for p in INCUBATOR if _status(p) == "promoted"}
    leaked = sorted(n for n in QUARANTINED - promoted if (SKILLS_DIR / n).exists())
    assert not leaked, f"quarantined drafts back in skills/: {leaked}"
