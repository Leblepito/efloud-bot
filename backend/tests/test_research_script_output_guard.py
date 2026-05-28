"""Output-guard for scripts/research_social_strategy.py.

Locks Gate 1 of docs/runbooks/social-research-promotion.md: the
research runner must refuse to write to any production-control file
even if a future caller (or a bug in `h_id` construction) coerces the
candidate path into one of those names.
"""
from __future__ import annotations

import pytest

from scripts.research_social_strategy import (
    PROTECTED_OUTPUT_NAMES,
    _refuse_protected_output,
)


def test_protected_set_includes_production_control_files():
    expected = {
        "config.yaml",
        "config.phase2_1k.yaml",
        "docker-compose.prod.yml",
        ".env",
    }
    assert expected <= set(PROTECTED_OUTPUT_NAMES), (
        "PROTECTED_OUTPUT_NAMES must include every production-control file "
        "the promotion runbook lists as untouchable by the research script."
    )


@pytest.mark.parametrize(
    "path",
    [
        "config.yaml",
        "configs/config.phase2_1k.yaml",
        "docker-compose.prod.yml",
        ".env",
        "./config.yaml",
        "/abs/path/to/config.phase2_1k.yaml",
    ],
)
def test_guard_refuses_protected_basenames(path):
    with pytest.raises(ValueError, match="Refusing to write"):
        _refuse_protected_output(path)


@pytest.mark.parametrize(
    "path",
    [
        "configs/candidates/candidate_social_ote_fvg_htf_bias_v1.yaml",
        "reports/social_research/2026-05-28_x/compare.json",
        "candidate.yaml",
        "configs/candidates/candidate_.yaml",
    ],
)
def test_guard_allows_research_paths(path):
    _refuse_protected_output(path)


def test_guard_uses_basename_not_substring():
    """A path that *contains* a protected basename as a parent directory
    must NOT be refused. Only the final filename matters."""
    _refuse_protected_output("backup/.env/notes.txt")
    _refuse_protected_output("configs/config.yaml.bak")


@pytest.mark.parametrize(
    "h_id",
    [
        # Attacker-controlled hypothesis id values that, when fed into
        # `CANDIDATES_DIR / f"candidate_{h_id}.yaml"`, resolve to a path
        # whose final segment is a protected basename. The guard must
        # still refuse them because `Path.name` returns the last
        # segment regardless of leading "../" traversal noise.
        "../../../config",
        "../../config.phase2_1k",
        "../../docker-compose.prod.yml/config",
    ],
)
def test_guard_catches_path_traversal_in_h_id(h_id):
    from pathlib import Path

    constructed = Path("configs/candidates") / f"candidate_{h_id}.yaml"
    if constructed.name in PROTECTED_OUTPUT_NAMES:
        with pytest.raises(ValueError, match="Refusing to write"):
            _refuse_protected_output(constructed)
    # The non-protected case (e.g. ".yaml" suffix breaking the match) is
    # already covered by the allow-list test above; the explicit
    # protected-name attack is the one that matters here.
    explicit_attack = Path("configs/candidates") / Path(h_id).name
    if explicit_attack.name in PROTECTED_OUTPUT_NAMES:
        with pytest.raises(ValueError, match="Refusing to write"):
            _refuse_protected_output(explicit_attack)
