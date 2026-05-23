"""Tests for SMC v2 entry order placement on CONFIRMED state.

PR #S3c-2 adds `_place_v2_entry_order` helper called from
_advance_setup_state_tick when state transitions to CONFIRMED.

Inert gates:
- order_manager is None → skipped (test/paper mode)
- setup_state_store is None → never reaches CONFIRMED (PR #67)

Real exchange path:
- calc_sl + calc_tp_targets compute SL/TP
- risk.calc_position_size computes size
- order_manager.open_position called with all params
- Returns Position or None (matches v1 contract)
"""
from unittest.mock import MagicMock, patch
import pandas as pd
import pytest

from engine.safe_orchestrator import SafeOrchestrator
from engine.smc_v2.setup_state import SetupCandidate, SetupStateStore
from engine.smc_v2.zones import ZoneSpec


def _minimal_config():
    return {
        "structure": {
            "swing_lookback": 5, "ob_sequential": 5, "body_mode": True,
            "eq_threshold_pct": 0.1, "range_lookback": 50,
        },
        "fibonacci": {"ote_lower": 0.618, "ote_upper": 0.786, "ext_tp2": 1.618},
        "risk": {
            "max_open_positions": 7, "min_rr": 1.8, "min_confluence": 55,
            "risk_per_trade_pct": 0.75, "recency_bars": 40,
            "position_size_calculation": "legacy",
            "max_loss_per_trade_usdt": 10, "target_stop_distance_pct": 5,
        },
        "safety": {
            "daily_loss_limit_pct": 3.0, "weekly_drawdown_limit_pct": 8.0,
            "consecutive_loss_limit": 3, "consecutive_pause_min": 120,
            "starting_balance": 10000, "max_position_notional_pct": 20,
            "max_total_exposure": 5.0, "max_holding_hours": 48,
            "max_pyramid_adds": 2, "min_sl_atr": 0.5, "max_sl_atr": 5.0,
            "adx_trend_threshold": 25, "adx_range_threshold": 20,
            "volatile_atr_mult": 2.5, "reverse_min_profit_pct": 0.2,
            "sl_atr_buffer": 0.5,
        },
        "timeframes": {"htf": "4h", "mtf": "1h", "entry": "15m"},
        "operation": {"check_interval_sec": 30, "log_level": "INFO"},
    }


def _make_in_zone_candidate():
    """A SetupCandidate already IN_ZONE — about to be CONFIRMED."""
    return SetupCandidate(
        symbol="BTC/USDT", direction="SHORT",
        trigger_bar_ts=2_500,
        trigger_price=100.0, htf_bias="BEAR",
        target_zone=ZoneSpec(low=100.0, high=110.0, source="HTF_FVG"),
        htf_swing_anchor=115.0, bars_waited=2,
        state="IN_ZONE",
        confluence_score=75, reasons=[],
    )


def _make_mock_order_manager():
    """OrderManager with mock client (dry_run=True for safety)."""
    from exchange import BinanceClient, OrderManager
    mock_client = MagicMock(spec=BinanceClient)
    mock_client.exchange = MagicMock()
    mock_client.market_type = "futures"
    mock_client.testnet = True
    mock_client.to_ccxt_symbol.side_effect = lambda s: f"{s}:USDT" if ":" not in s else s
    mock_client.get_balance = MagicMock(return_value=10000.0)
    mock_client.get_available_margin = MagicMock(return_value=10000.0)
    return OrderManager(mock_client, dry_run=True)


class TestInertWhenNoOrderManager:
    """When order_manager is None (test/paper mode), no order placement
    attempt even on CONFIRMED."""

    def test_no_order_placed_when_order_manager_none(self, tmp_path):
        store = SetupStateStore(tmp_path / "state.json")
        store.candidates.append(_make_in_zone_candidate())

        orc = SafeOrchestrator(
            _minimal_config(), state_dir=str(tmp_path), persist=False,
            setup_state_store=store,
        )
        cand = store.candidates[0]
        result = orc._place_v2_entry_order(cand, current_price=105.0, entry_price=105.0)
        assert result is None


class TestOrderPlacementOnConfirmed:
    """When order_manager is wired AND state goes to CONFIRMED, an entry
    order is placed via OrderManager.open_position()."""

    def test_place_v2_entry_order_calls_open_position(self, tmp_path):
        order_mgr = _make_mock_order_manager()
        store = SetupStateStore(tmp_path / "state.json")
        orc = SafeOrchestrator(
            _minimal_config(), state_dir=str(tmp_path), persist=False,
            setup_state_store=store, order_manager=order_mgr,
        )
        cand = _make_in_zone_candidate()

        with patch.object(order_mgr, "open_position") as spy_open:
            spy_open.return_value = MagicMock()
            result = orc._place_v2_entry_order(
                cand, current_price=105.0, entry_price=105.0,
            )
            assert spy_open.call_count == 1
            kwargs = spy_open.call_args.kwargs
            assert kwargs["symbol"] == "BTC/USDT"
            assert kwargs["direction"] == "SHORT"
            assert kwargs["entry"] == 105.0
            assert kwargs["sl"] > 105.0   # SHORT SL above entry
            assert kwargs["tp1"] < 105.0  # SHORT TP below entry
            assert kwargs["size"] > 0
            assert result is not None

    def test_no_order_when_sl_too_far(self, tmp_path):
        """SLTooFarError from calc_sl → setup rejected, no order."""
        order_mgr = _make_mock_order_manager()
        store = SetupStateStore(tmp_path / "state.json")
        orc = SafeOrchestrator(
            _minimal_config(), state_dir=str(tmp_path), persist=False,
            setup_state_store=store, order_manager=order_mgr,
        )
        cand = SetupCandidate(
            symbol="BTC/USDT", direction="SHORT",
            trigger_bar_ts=2_500,
            trigger_price=100.0, htf_bias="BEAR",
            target_zone=ZoneSpec(low=100.0, high=101.0, source="HTF_FVG"),
            htf_swing_anchor=999.0,  # absurdly far — beyond max_sl_atr
            bars_waited=2, state="IN_ZONE",
            confluence_score=75, reasons=[],
        )

        with patch.object(order_mgr, "open_position") as spy_open:
            result = orc._place_v2_entry_order(
                cand, current_price=105.0, entry_price=105.0,
            )
            assert spy_open.call_count == 0
            assert result is None


class TestAdvanceTriggersEntryOnConfirmed:
    """Integration: when _advance_setup_state_tick transitions IN_ZONE →
    CONFIRMED via confirm_entry, the order placement helper is called."""

    def _engulf_df(self):
        rows = [
            (1_000, 95.0, 96.0, 94.0, 95.5),
            (2_000, 96.0, 97.0, 95.0, 96.5),
            (3_000, 97.0, 105.0, 96.5, 104.0),
            (4_000, 104.0, 106.0, 102.5, 105.5),
            (5_000, 106.0, 106.5, 101.0, 102.0),  # bearish engulfing
        ]
        df = pd.DataFrame(rows, columns=["ts", "open", "high", "low", "close"])
        df["ts"] = pd.to_datetime(df["ts"], unit="ms", utc=True)
        df.set_index("ts", inplace=True)
        return df

    def test_confirmed_triggers_place_entry_call(self, tmp_path):
        order_mgr = _make_mock_order_manager()
        store = SetupStateStore(tmp_path / "state.json")
        store.candidates.append(_make_in_zone_candidate())

        orc = SafeOrchestrator(
            _minimal_config(), state_dir=str(tmp_path), persist=False,
            setup_state_store=store, order_manager=order_mgr,
        )

        with patch.object(orc, "_place_v2_entry_order") as spy:
            orc._advance_setup_state_tick(
                symbol="BTC/USDT",
                current_price=102.0,
                current_bar_ts=5_000,
                df_15m=self._engulf_df(),
            )
            assert spy.call_count == 1
            assert spy.call_args.args[0].state == "CONFIRMED"


class TestNoEntryWhenAdvanceSkipsConfirmation:
    """If confirm_entry returns (False, None), no entry order placed."""

    def test_in_zone_no_engulfing_no_entry(self, tmp_path):
        order_mgr = _make_mock_order_manager()
        store = SetupStateStore(tmp_path / "state.json")
        store.candidates.append(_make_in_zone_candidate())

        orc = SafeOrchestrator(
            _minimal_config(), state_dir=str(tmp_path), persist=False,
            setup_state_store=store, order_manager=order_mgr,
        )

        df = pd.DataFrame(
            {"open": [100.0, 101.0, 102.0], "high": [102.0, 103.0, 104.0],
             "low": [99.0, 100.0, 101.0], "close": [101.0, 102.0, 103.0]},
            index=pd.to_datetime([3_000, 4_000, 5_000], unit="ms", utc=True),
        )

        with patch.object(orc, "_place_v2_entry_order") as spy:
            orc._advance_setup_state_tick(
                symbol="BTC/USDT",
                current_price=103.0,
                current_bar_ts=5_000,
                df_15m=df,
            )
            assert spy.call_count == 0
            assert store.candidates[0].state == "IN_ZONE"
