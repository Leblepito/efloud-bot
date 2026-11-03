"""Structural checks for the efloud-desk Claude Code plugin.

`claude plugin validate` does not parse agent/skill frontmatter as strict YAML;
an unquoted ": " in a description silently breaks loading. These checks catch it.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
DOCS = sorted(list((ROOT / "agents").glob("*.md")) + list((ROOT / "skills").glob("*/SKILL.md")))


def frontmatter(path: Path) -> dict:
    text = path.read_text(encoding="utf-8")
    assert text.startswith("---\n"), f"{path} must start with YAML frontmatter"
    return yaml.safe_load(text.split("---", 2)[1])


@pytest.mark.parametrize("path", DOCS, ids=lambda p: str(p.relative_to(ROOT)))
def test_frontmatter_is_strict_yaml_with_name_and_description(path):
    fm = frontmatter(path)
    assert isinstance(fm, dict)
    assert isinstance(fm.get("name"), str) and fm["name"]
    assert isinstance(fm.get("description"), str) and len(fm["description"]) >= 40


def test_agent_names_match_file_names_and_are_unique():
    names = [frontmatter(p)["name"] for p in (ROOT / "agents").glob("*.md")]
    assert sorted(names) == sorted(p.stem for p in (ROOT / "agents").glob("*.md"))
    assert len(names) == len(set(names))


def test_every_agent_preloads_existing_skills():
    skill_names = {frontmatter(p)["name"] for p in (ROOT / "skills").glob("*/SKILL.md")}
    for path in (ROOT / "agents").glob("*.md"):
        preload = frontmatter(path).get("skills")
        assert isinstance(preload, list) and preload, f"{path.name} must preload skills (YAML list)"
        missing = set(preload) - skill_names
        assert not missing, f"{path.name} preloads unknown skills: {missing}"


def test_plugin_manifest_points_at_existing_hook():
    plugin = json.loads((ROOT / ".claude-plugin" / "plugin.json").read_text())
    hook_cfg = json.loads((ROOT / plugin["hooks"]).read_text())
    command = hook_cfg["hooks"]["PreToolUse"][0]["hooks"][0]["command"]
    assert "hooks/live_write_gate.py" in command
    assert (ROOT / "hooks" / "live_write_gate.py").is_file()


def test_marketplace_lists_the_plugin():
    market = json.loads((ROOT / ".claude-plugin" / "marketplace.json").read_text())
    plugin = json.loads((ROOT / ".claude-plugin" / "plugin.json").read_text())
    assert [p["name"] for p in market["plugins"]] == [plugin["name"]]
