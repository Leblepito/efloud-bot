from unittest.mock import MagicMock, patch
import pytest
from engine.safe_orchestrator import SafeOrchestrator
from engine.smc_v2.setup_state import SetupCandidate, SetupStateStore
from engine.smc_v2.zones import ZoneSpec

@pytest.fixture
def make_orc(tmp_path):
    def _make(require_confirmation=True):
        config = {
            "structure": {
                "swing_lookback": 5, "ob_sequential": 5, "body_mode": True,
                "eq_threshold_pct": 0.1, "range_lookback": 50,
            },
            "fibonacci": {"ote_lower": 0.618, "ote_upper": 0.786, "ext_tp2": 1.618},
            "risk": {"max_open_positions": 7, "min_rr": 1.8, "min_confluence": 55,
                     "risk_per_trade_pct": 0.75, "recency_bars": 40},
            "safety": {
                "daily_loss_limit_pct": 3.0, "weekly_drawdown_limit_pct": 8.0,
                "consecutive_loss_limit": 3, "consecutive_pause_min": 120,
                "starting_balance": 10000, "max_position_notional_pct": 20,
                "max_total_exposure": 5.0, "max_holding_hours": 48,
                "max_pyramid_adds": 2, "min_sl_atr": 0.5, "max_sl_atr": 5.0,
                "adx_trend_threshold": 25, "adx_range_threshold": 20,
                "volatile_atr_mult": 2.5, "reverse_min_profit_pct": 0.2,
            },
            "timeframes": {"htf": "4h", "mtf": "1h", "entry": "15m"},
            "operation": {"check_interval_sec": 30, "log_level": "INFO"},
            "smc_v2": {
                "pullback_timeout_bars": 8,
                "fvg_priority": True,
                "ote_band": [0.618, 0.786],
                "require_confirmation": require_confirmation,
                "max_pending_per_symbol": 3,
            }
        }
        
        store = SetupStateStore(tmp_path / "state.json")
        orc = SafeOrchestrator(
            config=config,
            state_dir=str(tmp_path),
            persist=False,
            setup_state_store=store,
        )
        return orc, store
    return _make

def test_immediate_entry_on_zone_touch_when_require_confirmation_false(make_orc):
    orc, store = make_orc(require_confirmation=False)
    
    cand = SetupCandidate(
        symbol="BTC/USDT", direction="LONG",
        trigger_bar_ts=1700000000000, trigger_price=95000.0,
        htf_bias="BULL",
        target_zone=ZoneSpec(low=96000.0, high=97000.0, source="HTF_FVG"),
        htf_swing_anchor=95000.0, bars_waited=0,
        state="AWAITING_PULLBACK", confluence_score=75, reasons=[],
    )
    store.add(cand)

    # Patch order placement method
    with patch.object(orc, "_place_v2_entry_order") as mock_place:
        orc._advance_setup_state_tick(
            symbol="BTC/USDT",
            current_price=96500.0,  # inside target_zone [96000, 97000]
            current_bar_ts=1700000060000,
        )
        
        assert cand.state == "CONFIRMED"
        mock_place.assert_called_once_with(
            cand,
            current_price=96500.0,
            entry_price=96500.0
        )

def test_no_immediate_entry_when_require_confirmation_true(make_orc):
    orc, store = make_orc(require_confirmation=True)
    
    cand = SetupCandidate(
        symbol="BTC/USDT", direction="LONG",
        trigger_bar_ts=1700000000000, trigger_price=95000.0,
        htf_bias="BULL",
        target_zone=ZoneSpec(low=96000.0, high=97000.0, source="HTF_FVG"),
        htf_swing_anchor=95000.0, bars_waited=0,
        state="AWAITING_PULLBACK", confluence_score=75, reasons=[],
    )
    store.add(cand)

    # Patch order placement method
    with patch.object(orc, "_place_v2_entry_order") as mock_place:
        orc._advance_setup_state_tick(
            symbol="BTC/USDT",
            current_price=96500.0,  # inside target_zone [96000, 97000]
            current_bar_ts=1700000060000,
        )
        
        assert cand.state == "IN_ZONE"
        mock_place.assert_not_called()

def test_sticky_in_zone_advances_directly_on_require_confirmation_false(make_orc):
    orc, store = make_orc(require_confirmation=False)
    
    cand = SetupCandidate(
        symbol="BTC/USDT", direction="LONG",
        trigger_bar_ts=1700000000000, trigger_price=95000.0,
        htf_bias="BULL",
        target_zone=ZoneSpec(low=96000.0, high=97000.0, source="HTF_FVG"),
        htf_swing_anchor=95000.0, bars_waited=1,
        state="IN_ZONE", confluence_score=75, reasons=[],
    )
    store.add(cand)

    with patch.object(orc, "_place_v2_entry_order") as mock_place:
        # Case 1: Price is OUTSIDE the zone (95500 is below low=96000)
        orc._advance_setup_state_tick(
            symbol="BTC/USDT",
            current_price=95500.0,
            current_bar_ts=1700000060000,
        )
        
        # State must remain IN_ZONE, and mock_place must not be called
        assert cand.state == "IN_ZONE"
        mock_place.assert_not_called()

        # Case 2: Price is INSIDE the zone (96500 is inside [96000, 97000])
        orc._advance_setup_state_tick(
            symbol="BTC/USDT",
            current_price=96500.0,
            current_bar_ts=1700000120000,
        )

        # State must advance to CONFIRMED, and entry must fire at 96500.0
        assert cand.state == "CONFIRMED"
        mock_place.assert_called_once_with(
            cand,
            current_price=96500.0,
            entry_price=96500.0
        )
