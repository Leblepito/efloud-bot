"""SafeOrchestrator → OrderManager wiring tests.

Bug: orchestrator'ın `lifecycle.open_position` çağrısı sadece local state'e
yazıyordu, borsaya emir göndermiyordu → bot loglarında "Opened LONG" diyordu
ama Binance'te pozisyon yoktu (paper-trade davranışı).

Fix: OrderManager dependency injection — order_manager varsa
order_manager.open_position çağrılır (real exchange order), sonra lifecycle'a
eklenir. Order failure'da lifecycle'a eklenmez (state mismatch önleme).
"""
from __future__ import annotations

from unittest.mock import MagicMock

from engine import SafeOrchestrator


def _minimal_config() -> dict:
    """SafeOrchestrator init'i için minimum config — runtime davranışı önemsiz."""
    return {
        "exchange": {"leverage": 3, "market_type": "futures"},
        "structure": {
            "swing_lookback": 5, "ob_sequential": 5, "body_mode": True,
            "eq_threshold_pct": 0.1, "range_lookback": 50,
        },
        "fibonacci": {"ote_lower": 0.618, "ote_upper": 0.786, "ext_tp2": 1.618},
        "risk": {
            "risk_per_trade_pct": 1.0, "max_open_positions": 10,
            "min_rr": 1.8, "min_confluence": 50, "recency_bars": 40,
            "sl_atr_buffer": 0.5,
        },
        "safety": {
            "daily_loss_limit_pct": 10.0, "weekly_drawdown_limit_pct": 15.0,
            "consecutive_loss_limit": 3, "consecutive_pause_min": 120,
            "starting_balance": 1000, "max_position_notional_pct": 3.33,
            "max_total_exposure": 1.0, "max_holding_hours": 24,
            "max_pyramid_adds": 0, "min_sl_atr": 0.5, "max_sl_atr": 5.0,
            "emergency_balance_threshold": 900, "reserve_balance": 0,
        },
    }


def test_orchestrator_accepts_order_manager_kwarg(tmp_path):
    """SafeOrchestrator constructor `order_manager` parametresini kabul etmeli."""
    cfg = _minimal_config()
    mock_om = MagicMock(name="OrderManager")
    orch = SafeOrchestrator(cfg, state_dir=str(tmp_path), order_manager=mock_om)
    assert orch.order_manager is mock_om


def test_orchestrator_order_manager_defaults_to_none(tmp_path):
    """Backward-compat: order_manager verilmezse None olmalı (paper-trade mode)."""
    cfg = _minimal_config()
    orch = SafeOrchestrator(cfg, state_dir=str(tmp_path))
    assert orch.order_manager is None


def _start_source():
    """start() + _start_impl() kaynağı birlikte.

    B-6 fix (2026-07-17): start() gövdesi TOCTOU guard'ıyla _start_impl()'e
    taşındı; wiring artık orada. Smoke test her iki metodu birlikte tarar.
    """
    import inspect
    from backend import bot_runner as runner_mod
    src = inspect.getsource(runner_mod.BotRunner.start)
    if hasattr(runner_mod.BotRunner, "_start_impl"):
        src += inspect.getsource(runner_mod.BotRunner._start_impl)
    return src


def test_bot_runner_wires_order_manager_into_orchestrator():
    """Production wiring: bot_runner.py orchestrator init'inde order_mgr göndermeli.

    Bu test source kodu inceler (smoke test) — runtime testi mock heavy
    olur, kod-bazlı assertion daha güvenilir bu satırlar için.
    """
    src = _start_source()
    assert "order_manager=self.order_mgr" in src, (
        "bot_runner.start() SafeOrchestrator'a order_mgr göndermeli "
        "— yoksa borsaya emir gitmez (paper-trade bug)"
    )


def test_bot_runner_wires_orphan_protector_into_order_manager():
    """Production wiring: OrderManager orphan_protector almalı."""
    src = _start_source()
    assert "orphan_protector=orphan_protector" in src
