"""Dry-run shadow mode log writer (PR #S6).

When engine.smc_v2_shadow=true: v2 path computes the full signal (including
safety gates), then logs to logs/smc_v2_shadow.log and returns None instead
of calling OrderManager.open_position.

Use case: Hermes runs v2 paralel to v1 for 1 week, reads the log daily,
compares to v1 outcomes, then flips smc_v2_shadow=false for live trading.
"""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from engine.safe_orchestrator import SafeOrchestrator
from engine.smc_v2.setup_state import SetupCandidate, SetupStateStore
from engine.smc_v2.zones import ZoneSpec
from exchange import BinanceClient, OrderManager


def _cfg(shadow: bool, symbols=None):
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
        "engine": {"smc_version": "v2",
                   "smc_v2_symbols": symbols or ["*"],
                   "smc_v2_shadow": shadow},
    }


def _make_cand(symbol="ETH/USDT"):
    return SetupCandidate(
        symbol=symbol, direction="SHORT",
        trigger_bar_ts=2_500, trigger_price=100.0, htf_bias="BEAR",
        target_zone=ZoneSpec(low=100.0, high=110.0, source="HTF_FVG"),
        htf_swing_anchor=115.0, bars_waited=2, state="IN_ZONE",
        confluence_score=75, reasons=["test"],
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


def test_shadow_on_logs_and_skips_order(tmp_path, monkeypatch):
    """smc_v2_shadow=true: signal computed, logged to file, no open_position call."""
    monkeypatch.chdir(tmp_path)  # logs/ relative to cwd
    cfg = _cfg(shadow=True)
    store = SetupStateStore(tmp_path / "s.json")
    orc = SafeOrchestrator(cfg, state_dir=str(tmp_path), persist=False,
                            setup_state_store=store, order_manager=_make_om())
    with patch.object(orc.order_manager, "open_position") as spy, \
         patch("engine.smc_v2.tp_calc.calc_tp_targets") as tp_spy:
        tp_spy.return_value = (95.0, 90.0,
                               {"tp1_source": "LIQUIDITY", "tp2_source": "FVG_FAR"})
        result = orc._place_v2_entry_order(_make_cand("ETH/USDT"),
                                            current_price=105.0, entry_price=105.0)
        assert result is None
        assert spy.call_count == 0
    log_file = Path("logs") / "smc_v2_shadow.log"
    assert log_file.exists()
    lines = log_file.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 1
    entry = json.loads(lines[0])
    assert entry["symbol"] == "ETH/USDT"
    assert entry["direction"] == "SHORT"
    assert entry["would_execute"] is False
    assert entry["reason"] == "SHADOW_MODE"
    assert entry["entry"] == 105.0
    assert entry["tp1"] == 95.0
    assert entry["tp2"] == 90.0
    assert entry["entry_setup_source"] == "FVG_PULLBACK"
    assert entry["tp1_target_type"] == "LIQUIDITY"
    assert entry["tp2_target_type"] == "FVG_FAR"
    assert entry["bars_to_pullback"] == 2
    assert entry["confluence_score"] == 75
    assert "ts" in entry  # ISO timestamp present


def test_shadow_off_executes_normally(tmp_path, monkeypatch):
    """Regression: smc_v2_shadow=false (with an EXPLICIT whitelist per H2) →
    OrderManager.open_position called."""
    monkeypatch.chdir(tmp_path)
    cfg = _cfg(shadow=False, symbols=["ETH/USDT"])
    store = SetupStateStore(tmp_path / "s.json")
    orc = SafeOrchestrator(cfg, state_dir=str(tmp_path), persist=False,
                            setup_state_store=store, order_manager=_make_om())
    with patch.object(orc.order_manager, "open_position") as spy, \
         patch("engine.smc_v2.tp_calc.calc_tp_targets") as tp_spy:
        tp_spy.return_value = (95.0, 90.0,
                               {"tp1_source": "LIQUIDITY", "tp2_source": "FVG_FAR"})
        spy.return_value = MagicMock()
        orc._place_v2_entry_order(_make_cand("ETH/USDT"),
                                  current_price=105.0, entry_price=105.0)
        assert spy.call_count == 1
    log_file = Path("logs") / "smc_v2_shadow.log"
    assert not log_file.exists(), "shadow log must not be created when shadow=false"


def test_shadow_appends_multiple_signals(tmp_path, monkeypatch):
    """Each shadow signal is one JSON line appended."""
    monkeypatch.chdir(tmp_path)
    cfg = _cfg(shadow=True)
    store = SetupStateStore(tmp_path / "s.json")
    orc = SafeOrchestrator(cfg, state_dir=str(tmp_path), persist=False,
                            setup_state_store=store, order_manager=_make_om())
    with patch("engine.smc_v2.tp_calc.calc_tp_targets") as tp_spy:
        tp_spy.return_value = (95.0, 90.0,
                               {"tp1_source": "LIQUIDITY", "tp2_source": "FVG_FAR"})
        orc._place_v2_entry_order(_make_cand("ETH/USDT"),
                                  current_price=105.0, entry_price=105.0)
        orc._place_v2_entry_order(_make_cand("BTC/USDT"),
                                  current_price=105.0, entry_price=105.0)
    lines = (Path("logs") / "smc_v2_shadow.log").read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 2
    assert json.loads(lines[0])["symbol"] == "ETH/USDT"
    assert json.loads(lines[1])["symbol"] == "BTC/USDT"


def test_shadow_skipped_when_safety_gate_rejects(tmp_path, monkeypatch):
    """Safety gates run BEFORE shadow gate. Rejection by breaker/pos_guard/etc.
    short-circuits before the shadow log writer. Operator sees rejection via
    main log; shadow log only captures ACCEPTED-but-not-executed signals."""
    monkeypatch.chdir(tmp_path)
    cfg = _cfg(shadow=True)
    store = SetupStateStore(tmp_path / "s.json")
    orc = SafeOrchestrator(cfg, state_dir=str(tmp_path), persist=False,
                            setup_state_store=store, order_manager=_make_om())
    with patch.object(orc.breaker, "check") as breaker_spy:
        breaker_status = MagicMock()
        breaker_status.can_trade = False
        breaker_status.state.value = "HALTED"
        breaker_spy.return_value = breaker_status
        result = orc._place_v2_entry_order(_make_cand("ETH/USDT"),
                                            current_price=105.0, entry_price=105.0)
        assert result is None
    log_file = Path("logs") / "smc_v2_shadow.log"
    assert not log_file.exists()


def test_shadow_default_true_when_key_absent(tmp_path, monkeypatch):
    """H2 fail-CLOSED: if the smc_v2_shadow KEY is dropped from config, the
    runtime default must be True (shadow/log-only) — a missing key must NEVER
    escalate v2 to live. Explicit whitelist present; only the shadow key is gone."""
    monkeypatch.chdir(tmp_path)
    cfg = _cfg(shadow=False, symbols=["ETH/USDT"])
    del cfg["engine"]["smc_v2_shadow"]  # operator/template drops the key
    store = SetupStateStore(tmp_path / "s.json")
    orc = SafeOrchestrator(cfg, state_dir=str(tmp_path), persist=False,
                            setup_state_store=store, order_manager=_make_om())
    with patch.object(orc.order_manager, "open_position") as spy, \
         patch("engine.smc_v2.tp_calc.calc_tp_targets") as tp_spy:
        tp_spy.return_value = (95.0, 90.0,
                               {"tp1_source": "LIQUIDITY", "tp2_source": "FVG_FAR"})
        result = orc._place_v2_entry_order(_make_cand("ETH/USDT"),
                                            current_price=105.0, entry_price=105.0)
        assert result is None, "missing smc_v2_shadow key must default to shadow (no live order)"
        assert spy.call_count == 0
    assert (Path("logs") / "smc_v2_shadow.log").exists()  # logged as shadow
