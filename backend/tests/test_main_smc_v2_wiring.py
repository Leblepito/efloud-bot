"""main._build_setup_state_store wiring (PR #S6).

Inert default (smc_version=v1): returns None → SafeOrchestrator inert (PR #67).
Active (smc_version=v2): instantiates SetupStateStore with max_pending_per_symbol
from config.
"""
from __future__ import annotations


def _v2_cfg():
    return {
        "engine": {"smc_version": "v2", "smc_v2_symbols": [], "smc_v2_shadow": False},
        "smc_v2": {"pullback_timeout_bars": 8, "max_pending_per_symbol": 3,
                   "fvg_priority": True, "ote_band": [0.618, 0.786],
                   "require_confirmation": True},
        "operation": {"state_dir": "./state_test"},
    }


def test_build_setup_state_store_returns_store_when_v2(tmp_path):
    from main import _build_setup_state_store
    store = _build_setup_state_store(_v2_cfg(), str(tmp_path))
    assert store is not None
    assert store.max_pending_per_symbol == 3


def test_build_setup_state_store_returns_none_when_v1(tmp_path):
    cfg = _v2_cfg()
    cfg["engine"]["smc_version"] = "v1"
    from main import _build_setup_state_store
    assert _build_setup_state_store(cfg, str(tmp_path)) is None


def test_build_setup_state_store_returns_none_when_engine_block_missing(tmp_path):
    """Legacy/test config without engine block: must default to None (inert)."""
    cfg = {"operation": {}}  # no engine, no smc_v2
    from main import _build_setup_state_store
    assert _build_setup_state_store(cfg, str(tmp_path)) is None


def test_build_setup_state_store_honors_max_pending(tmp_path):
    cfg = _v2_cfg()
    cfg["smc_v2"]["max_pending_per_symbol"] = 5
    from main import _build_setup_state_store
    store = _build_setup_state_store(cfg, str(tmp_path))
    assert store.max_pending_per_symbol == 5
