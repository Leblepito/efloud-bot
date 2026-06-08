import time
from unittest.mock import MagicMock, patch
import pytest
from engine import SafeOrchestrator
from engine.journal import TradeJournal, TradeSnapshot

def test_async_agent_review_flow(tmp_path):
    # Setup mock AgentTeam
    mock_agent_team = MagicMock()
    mock_agent_team.cfg = {"enabled": True, "gating": False}
    mock_agent_team.review_trade.return_value = {
        "team_verdict": "APPROVE",
        "score": 0.85,
        "reasons": ["Good structure"]
    }

    # Setup real TradeJournal
    journal_path = tmp_path / "trade_journal.jsonl"
    journal = TradeJournal(str(journal_path))

    # Setup SafeOrchestrator
    config = {
        "timeframes": {"htf": "4h", "mtf": "1h", "entry": "15m"},
        "structure": {"swing_lookback": 4, "ob_sequential": 5, "body_mode": True, "eq_threshold_pct": 0.1, "range_lookback": 50},
        "fibonacci": {"ote_lower": 0.618, "ote_upper": 0.786, "ext_tp2": 1.618},
        "safety": {"adx_trend_threshold": 25, "adx_range_threshold": 20, "volatile_atr_mult": 2.5, "daily_loss_limit_pct": 3.0, "weekly_drawdown_limit_pct": 8.0, "consecutive_loss_limit": 3, "starting_balance": 10000},
        "risk": {"min_confluence": 55, "min_rr": 1.5, "max_open_positions": 20, "recency_bars": 40},
        "operation": {"watch_only": True},
        "exchange": {"leverage": 1},
    }
    
    orch = SafeOrchestrator(
        config=config,
        state_dir=str(tmp_path),
        freshness_check=False,
        trade_journal=journal,
    )
    orch.agent_team = mock_agent_team

    # Create position using lifecycle
    pos = orch.lifecycle.open_position(
        symbol="BTC/USDT",
        direction="LONG",
        entry_price=100.0,
        size=1.0,
        sl=95.0,
        tp1=110.0,
        tp2=120.0,
    )
    
    # We must record the entry first so update_agent_review can find it
    orch._journal_record_entry(pos)

    # Measure time to confirm non-blocking execution
    start_time = time.time()
    
    # Trigger the async review
    orch._run_agent_review_async(
        pos=pos,
        confluence=60,
        htf_bias="BULL",
        df_htf=None,
        adx=22.0,
        rr=2.0,
        size_notional_pct=1.5
    )
    
    duration = time.time() - start_time
    assert duration < 0.05, f"Async review call blocked for {duration:.4f}s"

    # Wait for the background thread to run and update the journal
    for _ in range(20):
        time.sleep(0.05)
        snap = journal.get(pos.id)
        if snap and snap.agent_review is not None:
            break
            
    snap = journal.get(pos.id)
    assert snap is not None
    assert snap.agent_review == {
        "team_verdict": "APPROVE",
        "score": 0.85,
        "reasons": ["Good structure"]
    }
    
    # Verify mock was called correctly
    mock_agent_team.review_trade.assert_called_once()
    args = mock_agent_team.review_trade.call_args[0][0]
    assert args["symbol"] == "BTC/USDT"
    assert args["direction"] == "LONG"
    assert args["entry"] == 100.0
    assert args["sl"] == 95.0
    assert args["tp1"] == 110.0
    assert args["confluence"] == 60
    assert args["htf_bias"] == "BULL"
    assert args["adx"] == 22.0
    assert args["rr"] == 2.0
    assert args["size_notional_pct"] == 1.5


def test_async_agent_review_with_exchange_style_position(tmp_path):
    mock_agent_team = MagicMock()
    mock_agent_team.cfg = {"enabled": True, "gating": False}
    mock_agent_team.review_trade.return_value = {
        "team_verdict": "APPROVE",
        "score": 0.9,
        "reasons": ["Solid OB"]
    }

    journal_path = tmp_path / "trade_journal_exchange.jsonl"
    journal = TradeJournal(str(journal_path))

    orch = SafeOrchestrator(
        config={
            "timeframes": {"htf": "4h", "mtf": "1h", "entry": "15m"},
            "structure": {"swing_lookback": 4, "ob_sequential": 5, "body_mode": True, "eq_threshold_pct": 0.1, "range_lookback": 50},
            "fibonacci": {"ote_lower": 0.618, "ote_upper": 0.786, "ext_tp2": 1.618},
            "safety": {"starting_balance": 10000},
            "risk": {"max_open_positions": 20},
            "operation": {"watch_only": True},
        },
        state_dir=str(tmp_path),
        freshness_check=False,
        trade_journal=journal,
    )
    orch.agent_team = mock_agent_team

    from exchange import Position as ExchangePosition
    ex_pos = ExchangePosition(
        symbol="BTC/USDT",
        direction="LONG",
        entry=100.0,
        sl=95.0,
        tp1=110.0,
        tp2=120.0,
        size=1.0,
        order_id="order_9999",
        opened_at="2026-06-08T09:00:00Z"
    )

    # Record entry for exchange position (handles lack of .entries and .id)
    orch._journal_record_entry(ex_pos)

    # Trigger async review with exchange position (handles lack of avg_entry_price and id)
    orch._run_agent_review_async(
        pos=ex_pos,
        confluence=70,
        htf_bias="BULL",
        df_htf=None,
        adx=24.0,
        rr=2.0,
        size_notional_pct=1.0
    )

    # Wait for background thread
    for _ in range(20):
        time.sleep(0.05)
        snap = journal.get("order_9999")
        if snap and snap.agent_review is not None:
            break

    snap = journal.get("order_9999")
    assert snap is not None
    assert snap.agent_review == {
        "team_verdict": "APPROVE",
        "score": 0.9,
        "reasons": ["Solid OB"]
    }
    assert snap.actual_fill_price == 100.0
    assert snap.trade_id == "order_9999"


def test_v2_entry_order_with_exchange_style_position_returns_pos_and_no_exception(tmp_path):
    mock_agent_team = MagicMock()
    mock_agent_team.cfg = {"enabled": True, "gating": False}
    mock_agent_team.review_trade.return_value = {"team_verdict": "APPROVE"}

    journal_path = tmp_path / "trade_journal_v2_live.jsonl"
    journal = TradeJournal(str(journal_path))

    # Setup mocked order manager
    mock_order_manager = MagicMock()
    mock_order_manager.client.get_balance.return_value = 10000.0
    from exchange import Position as ExchangePosition
    ex_pos = ExchangePosition(
        symbol="ETH/USDT",
        direction="SHORT",
        entry=3500.0,
        sl=3550.0,
        tp1=3400.0,
        tp2=3300.0,
        size=2.0,
        order_id="live_order_1234",
        opened_at="2026-06-08T09:05:00Z"
    )
    mock_order_manager.open_position.return_value = ex_pos
    orch = SafeOrchestrator(
        config={
            "timeframes": {"htf": "4h", "mtf": "1h", "entry": "15m"},
            "structure": {"swing_lookback": 4, "ob_sequential": 5, "body_mode": True, "eq_threshold_pct": 0.1, "range_lookback": 50},
            "fibonacci": {"ote_lower": 0.618, "ote_upper": 0.786, "ext_tp2": 1.618},
            "safety": {
                "starting_balance": 10000,
                "sl_atr_buffer": 0.5,
                "min_sl_atr": 0.5,
                "max_sl_atr": 5.0,
                "max_position_notional_pct": 20.0,
                "max_total_exposure": 5.0,
                "max_holding_hours": 48,
                "max_pyramid_adds": 2,
            },
            "risk": {
                "max_open_positions": 20,
                "min_rr": 1.5,
                "min_confluence": 55,
                "risk_per_trade_pct": 0.75,
            },
            "operation": {"watch_only": False},  # shadow OFF
            "engine": {
                "smc_v2_symbols": ["*"],
                "smc_v2_shadow": False,
            },
            "exchange": {"leverage": 1},
        },
        state_dir=str(tmp_path),
        freshness_check=False,
        trade_journal=journal,
        order_manager=mock_order_manager
    )
    orch.agent_team = mock_agent_team

    from engine.smc_v2.setup_state import SetupCandidate
    from engine.smc_v2.zones import ZoneSpec
    cand = SetupCandidate(
        symbol="ETH/USDT", direction="SHORT",
        trigger_bar_ts=1700000000000, trigger_price=3500.0,
        htf_bias="BEAR",
        target_zone=ZoneSpec(low=3480.0, high=3520.0, source="HTF_FVG"),
        htf_swing_anchor=3600.0, bars_waited=2,
        state="CONFIRMED", confluence_score=80, reasons=[],
    )

    # Call the live order placement helper
    res_pos = orch._place_v2_entry_order(
        cand=cand,
        current_price=3500.0,
        entry_price=3500.0,
    )

    # Verify return value and that no exceptions escaped
    assert res_pos == ex_pos
    mock_order_manager.open_position.assert_called_once()
    
    # Wait for the async review of the live position to run
    for _ in range(20):
        time.sleep(0.05)
        snap = journal.get("live_order_1234")
        if snap and snap.agent_review is not None:
            break

    snap = journal.get("live_order_1234")
    assert snap is not None
    assert snap.actual_fill_price == 3500.0
    assert snap.zone_mid == 3500.0

