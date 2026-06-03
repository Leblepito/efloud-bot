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
        # PR #S6 whitelist gate: opt-in to v2 execution in tests by enabling
        # all symbols. Production default is [] (no execution).
        "engine": {"smc_version": "v2", "smc_v2_symbols": ["*"],
                   "smc_v2_shadow": False},
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
    """When order_manager is None (test/paper mode), paper position is created
    directly in local lifecycle state (no exchange order placed)."""

    def test_no_order_placed_when_order_manager_none(self, tmp_path):
        store = SetupStateStore(tmp_path / "state.json")
        store.candidates.append(_make_in_zone_candidate())

        orc = SafeOrchestrator(
            _minimal_config(), state_dir=str(tmp_path), persist=False,
            setup_state_store=store,
        )
        cand = store.candidates[0]
        result = orc._place_v2_entry_order(cand, current_price=105.0, entry_price=105.0)
        assert result is not None
        assert result.symbol == "BTC/USDT"
        assert result.direction == "SHORT"


class TestOrderPlacementOnConfirmed:
    """When order_manager is wired AND state goes to CONFIRMED, an entry
    order is placed via OrderManager.open_position()."""

    def test_place_v2_entry_order_calls_open_position(self, tmp_path):
        """Happy path: all safety gates pass → open_position called.

        Patches tp_calc to return a two-target (tp1+tp2) pair so this test
        exercises the legacy two-target path specifically. The single-target
        (tp2=None) acceptance path is covered in test_single_target_entry.py
        per PR #S6.5.

        Also asserts SMC v2 telemetry kwargs (PR #S5) flow through:
        - entry_setup_source derived from cand.target_zone.source
          (HTF_FVG → FVG_PULLBACK, OTE → OTE_RETRACE)
        - tp1_target_type / tp2_target_type from calc_tp_targets tags
        - bars_to_pullback from cand.bars_waited
        """
        order_mgr = _make_mock_order_manager()
        store = SetupStateStore(tmp_path / "state.json")
        # Set a deeper pocket config so pos_guard doesn't reject on notional
        cfg = _minimal_config()
        cfg["exchange"] = {"leverage": 1}
        orc = SafeOrchestrator(
            cfg, state_dir=str(tmp_path), persist=False,
            setup_state_store=store, order_manager=order_mgr,
        )
        cand = _make_in_zone_candidate()  # source=HTF_FVG, bars_waited=2

        # Patch tp_calc to return both tp1 and tp2 (real fib_ext fallback)
        with patch.object(order_mgr, "open_position") as spy_open, \
             patch("engine.smc_v2.tp_calc.calc_tp_targets") as tp_spy:
            tp_spy.return_value = (95.0, 90.0, {"tp1_source": "LIQUIDITY", "tp2_source": "FVG_FAR"})
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
            assert kwargs["tp2"] < kwargs["tp1"]  # SHORT TP2 below TP1
            assert kwargs["size"] > 0

            # SMC v2 telemetry (PR #S5)
            assert kwargs["entry_setup_source"] == "FVG_PULLBACK"
            assert kwargs["tp1_target_type"] == "LIQUIDITY"
            assert kwargs["tp2_target_type"] == "FVG_FAR"
            assert kwargs["bars_to_pullback"] == 2

            assert result is not None

    def test_place_v2_entry_order_ote_zone_telemetry(self, tmp_path):
        """OTE zone → entry_setup_source = OTE_RETRACE (PR #S5)."""
        order_mgr = _make_mock_order_manager()
        store = SetupStateStore(tmp_path / "state.json")
        cfg = _minimal_config()
        cfg["exchange"] = {"leverage": 1}
        orc = SafeOrchestrator(
            cfg, state_dir=str(tmp_path), persist=False,
            setup_state_store=store, order_manager=order_mgr,
        )
        cand = SetupCandidate(
            symbol="BTC/USDT", direction="SHORT",
            trigger_bar_ts=2_500,
            trigger_price=100.0, htf_bias="BEAR",
            target_zone=ZoneSpec(low=100.0, high=110.0, source="OTE"),
            htf_swing_anchor=115.0, bars_waited=5,
            state="IN_ZONE",
            confluence_score=75, reasons=[],
        )

        with patch.object(order_mgr, "open_position") as spy_open, \
             patch("engine.smc_v2.tp_calc.calc_tp_targets") as tp_spy:
            tp_spy.return_value = (95.0, 90.0, {"tp1_source": "FVG_NEAR", "tp2_source": "FIB_EXT"})
            spy_open.return_value = MagicMock()
            orc._place_v2_entry_order(cand, current_price=105.0, entry_price=105.0)
            kwargs = spy_open.call_args.kwargs
            assert kwargs["entry_setup_source"] == "OTE_RETRACE"
            assert kwargs["tp1_target_type"] == "FVG_NEAR"
            assert kwargs["tp2_target_type"] == "FIB_EXT"
            assert kwargs["bars_to_pullback"] == 5

    def test_tp2_none_accepted_as_single_target(self, tmp_path):
        """PR #S6.5: tp2=None now ACCEPTED as single-target setup.
        Empty htf inputs → calc_tp_targets returns tp2=None → flows through
        to OrderManager.open_position with tp2=None. Lifecycle (PR #S5) and
        exchange (PR #S5.5) handle the single-target path."""
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
            # PR #S6.5: was rejected (call_count=0); now accepted (call_count=1)
            assert spy_open.call_count == 1
            assert result is not None
            kwargs = spy_open.call_args.kwargs
            assert kwargs["tp2"] is None
            assert kwargs["tp2_target_type"] == "NONE"

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


def _make_live_order_manager(max_drift_pct: float, live_price: float):
    """A LIVE (non-dry-run) OrderManager with its entry-drift guard armed and a
    client reporting ``live_price`` (so the drift guard can re-validate)."""
    from exchange import BinanceClient, OrderManager
    mock_client = MagicMock(spec=BinanceClient)
    mock_client.exchange = MagicMock()
    mock_client.market_type = "futures"
    mock_client.testnet = True
    mock_client.to_ccxt_symbol.side_effect = lambda s: f"{s}:USDT" if ":" not in s else s
    mock_client.get_balance = MagicMock(return_value=10000.0)
    mock_client.get_available_margin = MagicMock(return_value=10000.0)
    mock_client.get_price = MagicMock(return_value=live_price)
    return OrderManager(mock_client, dry_run=False, max_entry_drift_pct=max_drift_pct)


class TestV2EntryDriftGuard:
    """C7: the v2 CONFIRMED→order path re-validates the LIVE price via the
    OrderManager entry-drift guard — no separate v2 re-check is needed, and a
    drifted entry is rejected before any market order."""

    def test_v2_entry_rejected_when_live_price_drifted_past_tp1(self, tmp_path):
        # SHORT confirmed at 105 with tp1=95; live has run to 90 (past TP1) — a
        # market short would open SL-only with a TP Binance rejects as -2021.
        order_mgr = _make_live_order_manager(max_drift_pct=1.0, live_price=90.0)
        store = SetupStateStore(tmp_path / "state.json")
        cfg = _minimal_config()
        cfg["exchange"] = {"leverage": 1}
        orc = SafeOrchestrator(
            cfg, state_dir=str(tmp_path), persist=False,
            setup_state_store=store, order_manager=order_mgr,
        )
        cand = _make_in_zone_candidate()  # SHORT, confirmed entry 105
        with patch("engine.smc_v2.tp_calc.calc_tp_targets") as tp_spy:
            tp_spy.return_value = (95.0, 90.0, {"tp1_source": "LIQUIDITY", "tp2_source": "FVG_FAR"})
            result = orc._place_v2_entry_order(
                cand, current_price=105.0, entry_price=105.0,
            )
        assert result is None, "C7: drifted live price must reject the v2 entry"
        order_mgr.client.exchange.create_order.assert_not_called()


class TestSafetyGates:
    """v2 path MUST go through the same safety gates as v1 (PR #S3c-2 fix
    after risk-ops review flagged bypass risk):
    - breaker.check.can_trade
    - pos_guard.can_open_position
    - pos_guard.is_new_entry_allowed
    """

    def test_no_order_when_breaker_halted(self, tmp_path):
        order_mgr = _make_mock_order_manager()
        store = SetupStateStore(tmp_path / "state.json")
        orc = SafeOrchestrator(
            _minimal_config(), state_dir=str(tmp_path), persist=False,
            setup_state_store=store, order_manager=order_mgr,
        )
        cand = _make_in_zone_candidate()

        # Patch breaker to return HALTED
        with patch.object(orc.breaker, "check") as breaker_spy, \
             patch.object(order_mgr, "open_position") as open_spy:
            mock_status = MagicMock()
            mock_status.can_trade = False
            mock_status.state.value = "HALTED"
            breaker_spy.return_value = mock_status
            result = orc._place_v2_entry_order(
                cand, current_price=105.0, entry_price=105.0,
            )
            assert open_spy.call_count == 0
            assert result is None

    def test_no_order_when_pos_guard_rejects(self, tmp_path):
        order_mgr = _make_mock_order_manager()
        store = SetupStateStore(tmp_path / "state.json")
        orc = SafeOrchestrator(
            _minimal_config(), state_dir=str(tmp_path), persist=False,
            setup_state_store=store, order_manager=order_mgr,
        )
        cand = _make_in_zone_candidate()

        # Patch pos_guard to reject
        with patch.object(orc.pos_guard, "can_open_position") as guard_spy, \
             patch.object(order_mgr, "open_position") as open_spy:
            mock_guard_result = MagicMock()
            mock_guard_result.allowed = False
            mock_guard_result.reason = "MAX_OPEN_REACHED"
            guard_spy.return_value = mock_guard_result
            result = orc._place_v2_entry_order(
                cand, current_price=105.0, entry_price=105.0,
            )
            assert open_spy.call_count == 0
            assert result is None

    def test_no_order_when_pause_guard_blocks(self, tmp_path):
        order_mgr = _make_mock_order_manager()
        store = SetupStateStore(tmp_path / "state.json")
        orc = SafeOrchestrator(
            _minimal_config(), state_dir=str(tmp_path), persist=False,
            setup_state_store=store, order_manager=order_mgr,
        )
        cand = _make_in_zone_candidate()

        # is_new_entry_allowed returns a PauseGateDecision with allowed=False
        mock_pause_decision = MagicMock()
        mock_pause_decision.allowed = False
        with patch.object(orc.pos_guard, "is_new_entry_allowed",
                          return_value=mock_pause_decision), \
             patch.object(order_mgr, "open_position") as open_spy:
            result = orc._place_v2_entry_order(
                cand, current_price=105.0, entry_price=105.0,
            )
            assert open_spy.call_count == 0
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
