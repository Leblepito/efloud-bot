"""Single-target v2 entry placement end-to-end (PR #S6.5).

PR #S3c-2 added an explicit `if tp2 is None: return None` rejection in
_place_v2_entry_order with a comment "deferred to PR #S5". All downstream
support shipped in PR #S5 / #S5.5 / #S5.6. PR #S6.5 removes the rejection
so single-target setups flow through to OrderManager.open_position.
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from engine.safe_orchestrator import SafeOrchestrator
from engine.smc_v2.setup_state import SetupCandidate, SetupStateStore
from engine.smc_v2.zones import ZoneSpec
from exchange import BinanceClient, OrderManager


def _cfg():
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
        "engine": {"smc_version": "v2", "smc_v2_symbols": ["*"],
                   "smc_v2_shadow": False},
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


def test_place_v2_entry_order_accepts_tp2_none_end_to_end(tmp_path):
    """When calc_tp_targets returns tp2=None (single-target), helper must
    forward to OrderManager.open_position with tp2=None — NO rejection."""
    cfg = _cfg()
    store = SetupStateStore(tmp_path / "s.json")
    orc = SafeOrchestrator(cfg, state_dir=str(tmp_path), persist=False,
                            setup_state_store=store, order_manager=_make_om())
    cand = _make_cand("ETH/USDT")
    with patch.object(orc.order_manager, "open_position") as spy_open, \
         patch("engine.smc_v2.tp_calc.calc_tp_targets") as tp_spy:
        tp_spy.return_value = (95.0, None,
                               {"tp1_source": "RR_PROJECTION", "tp2_source": "NONE"})
        spy_open.return_value = MagicMock()
        result = orc._place_v2_entry_order(cand, current_price=105.0, entry_price=105.0)
        assert result is not None, (
            "PR #S6.5: tp2=None must NOT be rejected at the early gate"
        )
        assert spy_open.call_count == 1
        kwargs = spy_open.call_args.kwargs
        assert kwargs["tp2"] is None
        assert kwargs["tp1"] == 95.0
        assert kwargs["entry"] == 105.0
        assert kwargs["direction"] == "SHORT"
        assert kwargs["symbol"] == "ETH/USDT"


def test_place_v2_entry_order_two_target_unchanged(tmp_path):
    """Regression: numeric tp2 path identical to PR #71 behavior."""
    cfg = _cfg()
    store = SetupStateStore(tmp_path / "s.json")
    orc = SafeOrchestrator(cfg, state_dir=str(tmp_path), persist=False,
                            setup_state_store=store, order_manager=_make_om())
    cand = _make_cand("ETH/USDT")
    with patch.object(orc.order_manager, "open_position") as spy_open, \
         patch("engine.smc_v2.tp_calc.calc_tp_targets") as tp_spy:
        tp_spy.return_value = (95.0, 90.0,
                               {"tp1_source": "LIQUIDITY", "tp2_source": "FVG_FAR"})
        spy_open.return_value = MagicMock()
        result = orc._place_v2_entry_order(cand, current_price=105.0, entry_price=105.0)
        assert result is not None
        kwargs = spy_open.call_args.kwargs
        assert kwargs["tp1"] == 95.0
        assert kwargs["tp2"] == 90.0
        assert kwargs["tp2_target_type"] == "FVG_FAR"


def test_place_v2_entry_order_single_target_telemetry_correct(tmp_path):
    """tp2_target_type='NONE' marker (spec §6) propagates to OrderManager."""
    cfg = _cfg()
    store = SetupStateStore(tmp_path / "s.json")
    orc = SafeOrchestrator(cfg, state_dir=str(tmp_path), persist=False,
                            setup_state_store=store, order_manager=_make_om())
    cand = _make_cand("ETH/USDT")
    with patch.object(orc.order_manager, "open_position") as spy_open, \
         patch("engine.smc_v2.tp_calc.calc_tp_targets") as tp_spy:
        tp_spy.return_value = (95.0, None,
                               {"tp1_source": "LIQUIDITY", "tp2_source": "NONE"})
        spy_open.return_value = MagicMock()
        orc._place_v2_entry_order(cand, current_price=105.0, entry_price=105.0)
        kwargs = spy_open.call_args.kwargs
        assert kwargs["tp2"] is None
        assert kwargs["tp1_target_type"] == "LIQUIDITY"
        assert kwargs["tp2_target_type"] == "NONE"
        assert kwargs["entry_setup_source"] == "FVG_PULLBACK"
        assert kwargs["bars_to_pullback"] == 2


def test_place_v2_entry_order_single_target_shadow_logs_tp2_null(tmp_path, monkeypatch):
    """When shadow=true: single-target signal logs tp2 as JSON null."""
    monkeypatch.chdir(tmp_path)
    cfg = _cfg()
    cfg["engine"]["smc_v2_shadow"] = True
    store = SetupStateStore(tmp_path / "s.json")
    orc = SafeOrchestrator(cfg, state_dir=str(tmp_path), persist=False,
                            setup_state_store=store, order_manager=_make_om())
    cand = _make_cand("ETH/USDT")
    with patch.object(orc.order_manager, "open_position") as spy_open, \
         patch("engine.smc_v2.tp_calc.calc_tp_targets") as tp_spy:
        tp_spy.return_value = (95.0, None,
                               {"tp1_source": "RR_PROJECTION", "tp2_source": "NONE"})
        orc._place_v2_entry_order(cand, current_price=105.0, entry_price=105.0)
        assert spy_open.call_count == 0  # shadow → no order
    import json
    from pathlib import Path
    log_file = Path("logs") / "smc_v2_shadow.log"
    entry = json.loads(log_file.read_text(encoding="utf-8").strip())
    assert entry["tp2"] is None
    assert entry["tp2_target_type"] == "NONE"
    assert entry["reason"] == "SHADOW_MODE"
