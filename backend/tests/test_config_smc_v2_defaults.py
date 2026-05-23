"""Defaults for SMC v2 flag block in config.yaml (PR #S6).

Inert invariant: smc_version=v1, smc_v2_symbols=[], smc_v2_shadow=false
→ zero behavioral change in production after deploy.
"""
from __future__ import annotations

from pathlib import Path

import yaml


def _load_config():
    return yaml.safe_load(Path("config.yaml").read_text(encoding="utf-8"))


def test_config_yaml_has_engine_block():
    cfg = _load_config()
    assert "engine" in cfg, "config.yaml must define an `engine` block"


def test_engine_smc_version_default_v1():
    cfg = _load_config()
    assert cfg["engine"]["smc_version"] == "v1"


def test_engine_smc_v2_symbols_default_empty():
    cfg = _load_config()
    assert cfg["engine"]["smc_v2_symbols"] == []


def test_engine_smc_v2_shadow_default_false():
    cfg = _load_config()
    assert cfg["engine"]["smc_v2_shadow"] is False


def test_config_has_smc_v2_tunable_block():
    cfg = _load_config()
    assert "smc_v2" in cfg


def test_smc_v2_tunables_match_spec():
    cfg = _load_config()
    smc_v2 = cfg["smc_v2"]
    assert smc_v2["pullback_timeout_bars"] == 8
    assert smc_v2["fvg_priority"] is True
    assert smc_v2["ote_band"] == [0.618, 0.786]
    assert smc_v2["require_confirmation"] is True
    assert smc_v2["max_pending_per_symbol"] == 3
