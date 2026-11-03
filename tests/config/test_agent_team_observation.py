"""Operator decision 2026-11-03: the advisory AgentTeam runs in OBSERVATION mode on the
live config — every opened trade gets a team verdict journaled (trade_journal
agent_review) so its edge can be measured later — but it never gates a trade.

Guards: the live config has the team enabled with gating False, and no config in
the repo enables gating (flipping it needs a recorded shadow period + operator
sign-off, see skills/desk-operating-model).
"""
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
LIVE = ROOT / "configs" / "config.phase2_1k.yaml"
ALL_CONFIGS = sorted([ROOT / "config.yaml", *(ROOT / "configs").glob("config.*.yaml")])


def _load(path: Path) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def test_live_config_runs_agent_team_in_observation_mode():
    team = _load(LIVE).get("agent_team") or {}
    assert team.get("enabled") is True
    assert team.get("gating") is False
    assert team.get("provider") == "claude"
    assert team.get("model") == "claude-sonnet-5-5"


@pytest.mark.parametrize("path", ALL_CONFIGS, ids=lambda p: p.name)
def test_no_config_lets_the_agent_team_gate_trades(path: Path):
    team = _load(path).get("agent_team") or {}
    assert team.get("gating", False) is False, f"{path.name}: agent_team.gating must stay false"
