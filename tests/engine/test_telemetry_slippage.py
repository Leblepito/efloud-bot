from datetime import datetime, timezone
import pytest
from unittest.mock import MagicMock
from engine.journal import TradeJournal, TradeSnapshot
from engine.lifecycle import Position, Entry
from engine import SafeOrchestrator

def test_telemetry_slippage_calculation(tmp_path):
    journal_path = tmp_path / "trade_journal.jsonl"
    journal = TradeJournal(str(journal_path))

    # Setup orchestrator with mocked config
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

    # Test case 1: LONG with adverse slippage (fill > signal)
    pos_long_adverse = Position(
        id="t1_long_adverse",
        symbol="BTC/USDT",
        direction="LONG",
        entries=[Entry(id="e1", price=102.0, size=1.0, timestamp="2026-06-08T09:00:02Z")],
        opened_at="2026-06-08T09:00:02Z",
        initial_sl=95.0,
        tp1=110.0,
        tp2=120.0,
    )
    orch._journal_record_entry(
        pos=pos_long_adverse,
        signal_entry_price=100.0,
        actual_fill_price=102.0,
        zone_mid=100.0,
        ts_signal="2026-06-08T09:00:00Z",
        ts_fill="2026-06-08T09:00:02Z"
    )
    snap = journal.get("t1_long_adverse")
    assert snap is not None
    assert snap.signal_entry_price == 100.0
    assert snap.actual_fill_price == 102.0
    assert snap.slippage_pct == pytest.approx(2.0)  # (102 - 100) / 100 * 100
    assert snap.latency_ms == pytest.approx(2000.0)  # 2 seconds = 2000ms

    # Test case 2: LONG with favorable slippage (fill < signal)
    pos_long_favorable = Position(
        id="t2_long_favorable",
        symbol="BTC/USDT",
        direction="LONG",
        entries=[Entry(id="e2", price=98.0, size=1.0, timestamp="2026-06-08T09:00:02Z")],
        opened_at="2026-06-08T09:00:02Z",
        initial_sl=95.0,
        tp1=110.0,
        tp2=120.0,
    )
    orch._journal_record_entry(
        pos=pos_long_favorable,
        signal_entry_price=100.0,
        actual_fill_price=98.0,
        zone_mid=100.0,
        ts_signal="2026-06-08T09:00:00Z",
        ts_fill="2026-06-08T09:00:02Z"
    )
    snap = journal.get("t2_long_favorable")
    assert snap is not None
    assert snap.slippage_pct == pytest.approx(-2.0)  # (98 - 100) / 100 * 100

    # Test case 3: SHORT with adverse slippage (fill < signal)
    pos_short_adverse = Position(
        id="t3_short_adverse",
        symbol="BTC/USDT",
        direction="SHORT",
        entries=[Entry(id="e3", price=98.0, size=1.0, timestamp="2026-06-08T09:00:02Z")],
        opened_at="2026-06-08T09:00:02Z",
        initial_sl=105.0,
        tp1=90.0,
        tp2=80.0,
    )
    orch._journal_record_entry(
        pos=pos_short_adverse,
        signal_entry_price=100.0,
        actual_fill_price=98.0,
        zone_mid=100.0,
        ts_signal="2026-06-08T09:00:00Z",
        ts_fill="2026-06-08T09:00:02Z"
    )
    snap = journal.get("t3_short_adverse")
    assert snap is not None
    assert snap.slippage_pct == pytest.approx(2.0)  # (100 - 98) / 100 * 100

    # Test case 4: SHORT with favorable slippage (fill > signal)
    pos_short_favorable = Position(
        id="t4_short_favorable",
        symbol="BTC/USDT",
        direction="SHORT",
        entries=[Entry(id="e4", price=102.0, size=1.0, timestamp="2026-06-08T09:00:02Z")],
        opened_at="2026-06-08T09:00:02Z",
        initial_sl=105.0,
        tp1=90.0,
        tp2=80.0,
    )
    orch._journal_record_entry(
        pos=pos_short_favorable,
        signal_entry_price=100.0,
        actual_fill_price=102.0,
        zone_mid=100.0,
        ts_signal="2026-06-08T09:00:00Z",
        ts_fill="2026-06-08T09:00:02Z"
    )
    snap = journal.get("t4_short_favorable")
    assert snap is not None
    assert snap.slippage_pct == pytest.approx(-2.0)  # (100 - 102) / 100 * 100
