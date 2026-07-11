"""F1 (leblep gate) + F2 (v2 lifecycle mirror) — 2026-07-11 bugfix batch.

Spec: docs/superpowers/specs/2026-07-11-tp-entry-anchored-targeting-and-bugfix-batch-design.md
Bölüm 3.

F1: _check_leblep_limits hiçbir config'de var olmayan root-level UPPERCASE
    key'leri okuyordu → her deployda allowed=False → v1 emir yolu ölü.
F2: Canlı v2 open lifecycle'a mirror edilmiyordu → guard'lar + breaker kör.
"""

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from engine.lifecycle import PositionLifecycle
from engine.safe_orchestrator import SafeOrchestrator


def _bare_orchestrator(config: dict) -> SafeOrchestrator:
    """__init__ çalıştırmadan iskelet instance — gate/method-level unit test."""
    orch = SafeOrchestrator.__new__(SafeOrchestrator)
    orch.config = config
    orch.breaker = SimpleNamespace(peak_balance=1000.0, current_balance=1000.0)
    return orch


class TestLeblepGateFix:
    """F1 — gate yalnız leblep/bot_v2 özelliği açıkken uygulanmalı."""

    def test_default_config_allows_v1_path(self):
        # Kök config'te bot_v2.enabled=false, leblep_enabled=false →
        # gate INERT olmalı (v1 yolu aylardır bu gate yüzünden ölüydü).
        orch = _bare_orchestrator({
            "bot_v2": {"enabled": False},
            "leblep_enabled": False,
            "leblep": {"risk_ops_approved": False},
        })
        check = orch._check_leblep_limits(
            balance=1000.0, symbol="ETH/USDT", direction="LONG",
            entry=100.0, size=1.0, existing_positions=[],
        )
        assert check.allowed, f"Gate must be inert when feature off: {check.reason}"

    def test_feature_on_unapproved_rejects(self):
        orch = _bare_orchestrator({
            "bot_v2": {"enabled": True},
            "leblep": {"risk_ops_approved": False},
        })
        check = orch._check_leblep_limits(
            balance=1000.0, symbol="ETH/USDT", direction="LONG",
            entry=100.0, size=1.0, existing_positions=[],
        )
        assert not check.allowed
        assert "RISK_OPS_APPROVED" in check.reason

    def test_feature_on_approved_nested_config_allows(self):
        # Nested lowercase config (gerçek config.yaml şeması) OKUNMALI.
        orch = _bare_orchestrator({
            "bot_v2": {"enabled": True},
            "leblep": {
                "risk_ops_approved": True,
                "max_combined_leverage": 5.0,
                "max_drawdown_pct": 12.0,
                "multi_instance_limit": 3,
            },
        })
        check = orch._check_leblep_limits(
            balance=1000.0, symbol="ETH/USDT", direction="LONG",
            entry=100.0, size=1.0, existing_positions=[],
        )
        assert check.allowed, check.reason

    def test_feature_on_approved_leverage_breach_rejects(self):
        orch = _bare_orchestrator({
            "bot_v2": {"enabled": True},
            "leblep": {
                "risk_ops_approved": True,
                "max_combined_leverage": 2.0,
            },
        })
        # new_notional = 100 × 30 = 3000 → 3x > 2x limit
        check = orch._check_leblep_limits(
            balance=1000.0, symbol="ETH/USDT", direction="LONG",
            entry=100.0, size=30.0, existing_positions=[],
        )
        assert not check.allowed
        assert "leverage" in check.reason.lower()

    def test_env_override_wins(self, monkeypatch):
        monkeypatch.setenv("RISK_OPS_APPROVED", "true")
        orch = _bare_orchestrator({
            "bot_v2": {"enabled": True},
            "leblep": {"risk_ops_approved": False},  # env bunu ezmeli
        })
        check = orch._check_leblep_limits(
            balance=1000.0, symbol="ETH/USDT", direction="LONG",
            entry=100.0, size=1.0, existing_positions=[],
        )
        assert check.allowed, check.reason

    def test_legacy_uppercase_root_keys_still_honored(self):
        # Geriye dönük uyum: eski uppercase root key'ler fallback olarak okunur.
        orch = _bare_orchestrator({
            "bot_v2": {"enabled": True},
            "RISK_OPS_APPROVED": True,
        })
        check = orch._check_leblep_limits(
            balance=1000.0, symbol="ETH/USDT", direction="LONG",
            entry=100.0, size=1.0, existing_positions=[],
        )
        assert check.allowed, check.reason


class TestV2LifecycleMirror:
    """F2 — canlı v2 open, lifecycle'a v1 pattern'iyle (satır ~1595) yazılmalı."""

    def _orch_for_v2(self, monkeypatch):
        orch = SafeOrchestrator.__new__(SafeOrchestrator)
        orch.config = {
            "engine": {"smc_v2_symbols": ["ETH/USDT"], "smc_v2_shadow": False},
            "safety": {"sl_atr_buffer": 0.5, "min_sl_atr": 0.5, "max_sl_atr": 5.0,
                       "max_position_notional_pct": 8.0},
            "risk": {"min_rr": 1.5, "risk_per_trade_pct": 1.0},
            "exchange": {"leverage": 1},
            "fibonacci": {"ext_tp2": 1.618},
        }
        orch.lifecycle = PositionLifecycle()
        orch.breaker = SimpleNamespace(
            check=lambda now=None: SimpleNamespace(
                can_trade=True, state=SimpleNamespace(value="OK")),
            current_balance=1000.0, peak_balance=1000.0,
        )
        orch.pos_guard = SimpleNamespace(
            can_open_position=lambda **kw: SimpleNamespace(allowed=True, reason=""),
            is_new_entry_allowed=lambda sig: SimpleNamespace(allowed=True),
        )
        exchange_pos = SimpleNamespace(
            avg_entry_price=100.0, entry=100.0, id="test-pos-1",
            symbol="ETH/USDT", direction="LONG", size=1.0,
            sl=99.0, tp1=103.0, tp2=106.0,
            opened_at="2026-07-11T00:00:00",
        )
        orch.order_manager = SimpleNamespace(
            client=SimpleNamespace(get_balance=lambda: 1000.0),
            open_position=MagicMock(return_value=exchange_pos),
        )
        orch._journal_record_entry = lambda *a, **kw: None
        orch._log_shadow_signal = lambda *a, **kw: None
        orch._run_agent_review_async = lambda *a, **kw: None

        # SL/TP hesaplarını sabitle (birim test — hedef mirror davranışı)
        import engine.smc_v2.sl_calc as sl_calc_mod
        import engine.smc_v2.tp_calc as tp_calc_mod
        monkeypatch.setattr(sl_calc_mod, "calc_sl", lambda **kw: 99.0)
        monkeypatch.setattr(
            tp_calc_mod, "calc_tp_targets",
            lambda **kw: (103.0, 106.0, {"tp1_source": "LIQUIDITY",
                                         "tp2_source": "FVG_FAR"}),
        )
        return orch

    def _cand(self):
        return SimpleNamespace(
            symbol="ETH/USDT", direction="LONG",
            target_zone=SimpleNamespace(source="OTE", low=99.0, high=100.0),
            htf_swing_anchor=None, bars_waited=2, trigger_bar_ts=None,
            confluence_score=70, htf_bias="BULL",
        )

    def test_live_v2_open_registers_in_lifecycle(self, monkeypatch):
        orch = self._orch_for_v2(monkeypatch)
        pos = orch._place_v2_entry_order(self._cand(), 100.0, 100.0)

        assert pos is not None, "order path should succeed in this fixture"
        assert orch.order_manager.open_position.called
        open_now = orch.lifecycle.open_positions("ETH/USDT")
        assert len(open_now) == 1, (
            "Live v2 open MUST mirror into lifecycle (guards/breaker read it); "
            f"found {len(open_now)}"
        )
        mirrored = open_now[0]
        assert mirrored.direction == "LONG"
        assert mirrored.tp1 == 103.0
        assert mirrored.tp2 == 106.0
        assert mirrored.entry_setup_source == "OTE_RETRACE"

    def test_paper_v2_open_not_double_registered(self, monkeypatch):
        # order_manager=None (paper) dalı lifecycle'a ZATEN açıyor —
        # mirror çift kayıt yaratmamalı.
        orch = self._orch_for_v2(monkeypatch)
        orch.order_manager = None
        pos = orch._place_v2_entry_order(self._cand(), 100.0, 100.0)

        assert pos is not None
        assert len(orch.lifecycle.open_positions("ETH/USDT")) == 1
