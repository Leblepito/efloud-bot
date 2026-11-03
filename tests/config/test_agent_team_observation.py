"""Operator decision 2026-11-03 (revised): the advisory AgentTeam runs in OBSERVATION
mode on the live config — every opened trade gets a team verdict journaled
(trade_journal agent_review) so its edge can be measured later — but it never gates a
trade.

Backend decision: the advisory layer (agent team + sentiment + structure validation)
runs on **OpenRouter** with `deepseek/deepseek-v4.1-flash`. Rationale: a single key
(`OPENROUTER_API_KEY`) reaches every model, and the VPS has no Anthropic/MiniMax key —
so a `provider: claude` / `provider: minimax` pin leaves every call returning the
canonical `{}` fail-safe (the layer would look enabled but be inert).

Guards:
  * the live config has the team enabled with gating False, and no config in the repo
    enables gating (flipping it needs a recorded shadow period + operator sign-off,
    see skills/desk-operating-model);
  * every pinned provider is in the LLM factory's key-env registry — a provider with
    no key mapping is silently skipped by the startup/sentiment gate;
  * the live `llm:` and `agent_team:` blocks agree on provider+model, so the operator
    cannot switch one and leave the other calling a dead backend.
"""
from pathlib import Path

import pytest
import yaml

from engine.agents.llm import PROVIDER_KEY_ENV

ROOT = Path(__file__).resolve().parents[2]
LIVE = ROOT / "configs" / "config.phase2_1k.yaml"
ALL_CONFIGS = sorted([ROOT / "config.yaml", *(ROOT / "configs").glob("config.*.yaml")])

# The pinned advisory backend (operator decision 2026-11-03).
LIVE_PROVIDER = "openrouter"
LIVE_MODEL = "deepseek/deepseek-v4.1-flash"


def _load(path: Path) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def test_live_config_runs_agent_team_in_observation_mode():
    team = _load(LIVE).get("agent_team") or {}
    assert team.get("enabled") is True
    assert team.get("gating") is False
    assert team.get("provider") == LIVE_PROVIDER
    assert team.get("model") == LIVE_MODEL


def test_live_llm_and_agent_team_pin_the_same_backend():
    """The two advisory blocks must not drift apart. `llm:` wins for the
    sentiment/structure call sites and `agent_team:` for the per-trade review;
    a mismatch means one of them silently calls a backend with no key."""
    cfg = _load(LIVE)
    llm = cfg.get("llm") or {}
    team = cfg.get("agent_team") or {}
    assert llm.get("provider") == team.get("provider")
    assert llm.get("model") == team.get("model")


def test_pinned_model_looks_like_a_provider_scoped_slug():
    """No dead alias pins: an OpenRouter model id is `vendor/model`. A bare
    alias is how the previous `gemini-3.5-flash`-class 404 regression got in."""
    assert "/" in LIVE_MODEL, f"{LIVE_MODEL!r} is not a provider-scoped OpenRouter slug"


def test_pinned_provider_has_a_key_env_registry_entry():
    assert LIVE_PROVIDER in PROVIDER_KEY_ENV, (
        f"provider {LIVE_PROVIDER!r} is missing from PROVIDER_KEY_ENV — "
        "provider_key_present() would report the layer as unconfigured"
    )


@pytest.mark.parametrize("path", ALL_CONFIGS, ids=lambda p: p.name)
def test_no_config_lets_the_agent_team_gate_trades(path: Path):
    team = _load(path).get("agent_team") or {}
    assert team.get("gating", False) is False, f"{path.name}: agent_team.gating must stay false"


@pytest.mark.parametrize("path", ALL_CONFIGS, ids=lambda p: p.name)
def test_every_pinned_llm_provider_is_key_registry_aware(path: Path):
    """If a config pins a provider, the factory must know which env var carries
    its key — otherwise the bot logs "no key" and skips the advisory call."""
    cfg = _load(path)
    for block in ("llm", "agent_team"):
        provider = (cfg.get(block) or {}).get("provider")
        if provider:
            assert provider in PROVIDER_KEY_ENV, (
                f"{path.name}: {block}.provider={provider!r} is not in PROVIDER_KEY_ENV"
            )
