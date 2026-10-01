"""OPERATOR FIX (2026-10-01): v1 signal path must be MUTED for symbols the v2
pullback path owns. v1 fires MARKET at the CHoCH break moment ("aninda giris");
v2 waits for the OB/BB retest. _v2_entry_active() is the single source of truth
shared by both gates — same whitelist + shadow conditions as
_place_v2_entry_order, so v1 can never be muted on a symbol v2 won't execute.
"""
from engine.safe_orchestrator import SafeOrchestrator


def _bare(store, engine_cfg):
    orch = SafeOrchestrator.__new__(SafeOrchestrator)
    orch.config = {"engine": engine_cfg}
    orch.setup_state_store = store
    return orch


def test_inert_when_store_none():
    orch = _bare(None, {"smc_version": "v2", "smc_v2_symbols": ["BTC/USDT"],
                        "smc_v2_shadow": False})
    assert orch._v2_entry_active("BTC/USDT") is False


def test_active_for_whitelisted_live_symbol():
    orch = _bare(object(), {"smc_version": "v2", "smc_v2_symbols": ["BTC/USDT"],
                            "smc_v2_shadow": False})
    assert orch._v2_entry_active("BTC/USDT") is True
    assert orch._v2_entry_active("ETH/USDT") is False


def test_shadow_mode_does_not_mute_v1():
    # v2 shadow logs only, places no orders — v1 must keep trading.
    orch = _bare(object(), {"smc_version": "v2", "smc_v2_symbols": ["BTC/USDT"],
                            "smc_v2_shadow": True})
    assert orch._v2_entry_active("BTC/USDT") is False


def test_wildcard_does_not_mute_v1():
    # '*' is never allowed for LIVE v2 execution (H2 fail-closed) — v1 stays on.
    orch = _bare(object(), {"smc_version": "v2", "smc_v2_symbols": ["*"],
                            "smc_v2_shadow": False})
    assert orch._v2_entry_active("BTC/USDT") is False


def test_missing_shadow_key_fail_closed():
    # smc_v2_shadow default True → v2 not live → v1 NOT muted.
    orch = _bare(object(), {"smc_version": "v2", "smc_v2_symbols": ["BTC/USDT"]})
    assert orch._v2_entry_active("BTC/USDT") is False


def test_non_list_whitelist_no_mute():
    orch = _bare(object(), {"smc_version": "v2", "smc_v2_symbols": "BTC/USDT",
                            "smc_v2_shadow": False})
    assert orch._v2_entry_active("BTC/USDT") is False
