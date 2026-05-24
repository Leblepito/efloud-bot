"""Symbol whitelist gate in _place_v2_entry_order (PR #S6).

First gate, before all safety checks. Rejects when symbol not in
engine.smc_v2_symbols (with ["*"] meaning all).
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from engine.safe_orchestrator import SafeOrchestrator
from engine.smc_v2.setup_state import SetupCandidate, SetupStateStore
from engine.smc_v2.zones import ZoneSpec
from exchange import BinanceClient, OrderManager


def _cfg(whitelist: list, shadow: bool = False):
    return {
        "structure": {"swing_lookback": 5, "ob_sequential": 5, "body_mode": True,
                      "eq_threshold_pct": 0.1, "range_lookback": 50},
        "fibonacci": {"ote_lower": 0.618, "ote_upper": 0.786, "ext_tp2": 1.618},
        "risk": {"max_open_positions": 7, "min_rr": 1.8, "min_confluence": 55,
                 "risk_per_trade_pct": 0.75, "recency_bars": 40,
                 "position_size_calculation": "legacy",
                 "max_loss_per_trade_usdt": 10, "target_stop_distance_pct": 5},
        "safety": {"daily_loss_limit_pct": 3.0, "weekly_drawdown_limit_pct": 8.0,
                   "consecutive_loss_limit": 3, "consecutive_pause_min": 120,
                   "starting_balance": 10000, "max_position_notional_pct": 20,
                   "max_total_exposure": 5.0, "max_holding_hours": 48,
                   "max_pyramid_adds": 2, "min_sl_atr": 0.5, "max_sl_atr": 5.0,
                   "adx_trend_threshold": 25, "adx_range_threshold": 20,
                   "volatile_atr_mult": 2.5, "reverse_min_profit_pct": 0.2,
                   "sl_atr_buffer": 0.5},
        "timeframes": {"htf": "4h", "mtf": "1h", "entry": "15m"},
        "operation": {"check_interval_sec": 30, "log_level": "INFO"},
        "exchange": {"leverage": 1},
        "engine": {"smc_version": "v2", "smc_v2_symbols": whitelist,
                   "smc_v2_shadow": shadow},
    }


def _make_cand(symbol="ETH/USDT"):
    return SetupCandidate(
        symbol=symbol, direction="SHORT",
        trigger_bar_ts=2_500, trigger_price=100.0, htf_bias="BEAR",
        target_zone=ZoneSpec(low=100.0, high=110.0, source="HTF_FVG"),
        htf_swing_anchor=115.0, bars_waited=2, state="IN_ZONE",
        confluence_score=75, reasons=[],
    )


def _make_om():
    mock_client = MagicMock(spec=BinanceClient)
    mock_client.exchange = MagicMock()
    mock_client.market_type = "futures"
    mock_client.testnet = True
    mock_client.to_ccxt_symbol.side_effect = lambda s: f"{s}:USDT"
    mock_client.get_balance = MagicMock(return_value=10000.0)
    mock_client.get_available_margin = MagicMock(return_value=10000.0)
    return OrderManager(mock_client, dry_run=True)


def test_whitelist_empty_rejects_all(tmp_path):
    """smc_v2_symbols=[] → v2 never fires. Default safety state."""
    cfg = _cfg([])
    store = SetupStateStore(tmp_path / "s.json")
    orc = SafeOrchestrator(cfg, state_dir=str(tmp_path), persist=False,
                            setup_state_store=store, order_manager=_make_om())
    with patch.object(orc.order_manager, "open_position") as spy:
        result = orc._place_v2_entry_order(_make_cand("ETH/USDT"),
                                            current_price=105.0, entry_price=105.0)
        assert result is None
        assert spy.call_count == 0


def test_whitelist_specific_symbol_accepts(tmp_path):
    cfg = _cfg(["ETH/USDT"])
    store = SetupStateStore(tmp_path / "s.json")
    orc = SafeOrchestrator(cfg, state_dir=str(tmp_path), persist=False,
                            setup_state_store=store, order_manager=_make_om())
    with patch.object(orc.order_manager, "open_position") as spy, \
         patch("engine.smc_v2.tp_calc.calc_tp_targets") as tp_spy:
        tp_spy.return_value = (95.0, 90.0,
                               {"tp1_source": "LIQUIDITY", "tp2_source": "FVG_FAR"})
        spy.return_value = MagicMock()
        result = orc._place_v2_entry_order(_make_cand("ETH/USDT"),
                                            current_price=105.0, entry_price=105.0)
        assert spy.call_count == 1
        assert result is not None


def test_whitelist_wildcard_accepts_all(tmp_path):
    """smc_v2_symbols=["*"] → all symbols pass the whitelist gate."""
    cfg = _cfg(["*"])
    store = SetupStateStore(tmp_path / "s.json")
    orc = SafeOrchestrator(cfg, state_dir=str(tmp_path), persist=False,
                            setup_state_store=store, order_manager=_make_om())
    with patch.object(orc.order_manager, "open_position") as spy, \
         patch("engine.smc_v2.tp_calc.calc_tp_targets") as tp_spy:
        tp_spy.return_value = (95.0, 90.0,
                               {"tp1_source": "LIQUIDITY", "tp2_source": "FVG_FAR"})
        spy.return_value = MagicMock()
        result = orc._place_v2_entry_order(_make_cand("DOGE/USDT"),
                                            current_price=105.0, entry_price=105.0)
        assert spy.call_count == 1
        assert result is not None


def test_whitelist_other_symbol_rejected(tmp_path):
    """Symbol not in specific whitelist → rejected, no order."""
    cfg = _cfg(["BTC/USDT"])
    store = SetupStateStore(tmp_path / "s.json")
    orc = SafeOrchestrator(cfg, state_dir=str(tmp_path), persist=False,
                            setup_state_store=store, order_manager=_make_om())
    with patch.object(orc.order_manager, "open_position") as spy:
        result = orc._place_v2_entry_order(_make_cand("ETH/USDT"),
                                            current_price=105.0, entry_price=105.0)
        assert spy.call_count == 0
        assert result is None


def test_whitelist_non_list_rejected_defensively(tmp_path):
    """YAML operator typo: smc_v2_symbols: "ETH/USDT" (string) instead of
    smc_v2_symbols: ["ETH/USDT"] (list). Defensive guard from risk-ops review
    rejects non-list values — substring `in` semantics would otherwise produce
    surprise matches (e.g., `"ET" in "ETH/USDT"` is True)."""
    cfg = _cfg(["ETH/USDT"])
    cfg["engine"]["smc_v2_symbols"] = "ETH/USDT"  # operator typo: string
    store = SetupStateStore(tmp_path / "s.json")
    orc = SafeOrchestrator(cfg, state_dir=str(tmp_path), persist=False,
                            setup_state_store=store, order_manager=_make_om())
    with patch.object(orc.order_manager, "open_position") as spy:
        result = orc._place_v2_entry_order(_make_cand("ETH/USDT"),
                                            current_price=105.0, entry_price=105.0)
        assert result is None
        assert spy.call_count == 0


def test_whitelist_runs_before_safety_gates(tmp_path):
    """Whitelist gate is FIRST — rejection happens without touching breaker,
    pos_guard, or tp_calc."""
    cfg = _cfg([])
    store = SetupStateStore(tmp_path / "s.json")
    orc = SafeOrchestrator(cfg, state_dir=str(tmp_path), persist=False,
                            setup_state_store=store, order_manager=_make_om())
    with patch.object(orc.breaker, "check") as breaker_spy, \
         patch.object(orc.order_manager, "open_position") as open_spy, \
         patch("engine.smc_v2.tp_calc.calc_tp_targets") as tp_spy:
        result = orc._place_v2_entry_order(_make_cand("ETH/USDT"),
                                            current_price=105.0, entry_price=105.0)
        assert result is None
        # Whitelist short-circuits BEFORE breaker check / tp_calc / open_position
        assert breaker_spy.call_count == 0
        assert tp_spy.call_count == 0
        assert open_spy.call_count == 0
