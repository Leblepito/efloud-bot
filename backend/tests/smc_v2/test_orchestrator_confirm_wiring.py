"""Tests for SMC v2 confirm_entry real wiring in SafeOrchestrator.

PR #S3b replaces the (False, None) placeholder with a proxy to
engine.smc_v2.confirmation.confirm_entry. Verifies:
- Proxy returns same value as direct call
- df_15m flows through _advance_setup_state_tick correctly
- IN_ZONE candidate transitions to CONFIRMED when engulfing pattern present
"""
import pandas as pd
import pytest

from engine.safe_orchestrator import SafeOrchestrator
from engine.smc_v2.zones import ZoneSpec


def _engulf_df():
    """DataFrame with a bearish engulfing pattern at ts=5000."""
    rows = [
        (1_000, 95.0, 96.0, 94.0, 95.5),
        (2_000, 96.0, 97.0, 95.0, 96.5),
        (3_000, 97.0, 105.0, 96.5, 104.0),
        (4_000, 104.0, 106.0, 102.5, 105.5),  # prior bullish
        (5_000, 106.0, 106.5, 101.0, 102.0),  # bearish engulfing (close=102 in zone)
    ]
    df = pd.DataFrame(rows, columns=["ts", "open", "high", "low", "close"])
    df["ts"] = pd.to_datetime(df["ts"], unit="ms", utc=True)
    df.set_index("ts", inplace=True)
    return df


def _minimal_config():
    return {
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
    }


class TestConfirmEntryProxy:
    """SafeOrchestrator.confirm_entry is no longer a stub.
    It delegates to engine.smc_v2.confirmation.confirm_entry."""

    def test_proxy_returns_true_for_engulfing(self, tmp_path):
        orc = SafeOrchestrator(_minimal_config(), state_dir=str(tmp_path), persist=False)
        zone = ZoneSpec(low=100.0, high=110.0, source="HTF_FVG")
        confirmed, entry_price = orc.confirm_entry(
            df_15m=_engulf_df(), zone=zone, direction="SHORT", since_ts=2_500,
        )
        assert confirmed is True
        assert entry_price == 102.0

    def test_proxy_returns_false_when_no_engulfing(self, tmp_path):
        orc = SafeOrchestrator(_minimal_config(), state_dir=str(tmp_path), persist=False)
        zone = ZoneSpec(low=100.0, high=110.0, source="HTF_FVG")
        df = pd.DataFrame(
            {"open": [100.0, 101.0], "high": [102.0, 103.0],
             "low": [99.0, 100.0], "close": [101.0, 102.0]},
            index=pd.to_datetime([1_000, 2_000], unit="ms", utc=True),
        )
        confirmed, entry_price = orc.confirm_entry(
            df_15m=df, zone=zone, direction="SHORT", since_ts=500,
        )
        assert confirmed is False
        assert entry_price is None

    def test_proxy_matches_direct_call(self, tmp_path):
        """Proxy result must match calling engine.smc_v2.confirmation.confirm_entry directly."""
        from engine.smc_v2.confirmation import confirm_entry as direct
        orc = SafeOrchestrator(_minimal_config(), state_dir=str(tmp_path), persist=False)
        zone = ZoneSpec(low=100.0, high=110.0, source="HTF_FVG")
        df = _engulf_df()
        direct_result = direct(df_15m=df, zone=zone, direction="SHORT", since_ts=2_500)
        proxy_result = orc.confirm_entry(df_15m=df, zone=zone, direction="SHORT", since_ts=2_500)
        assert direct_result == proxy_result


class TestAdvanceWithRealConfirmation:
    """When _advance_setup_state_tick is called with a real df_15m that
    contains an engulfing pattern, an IN_ZONE candidate should transition
    to CONFIRMED."""

    def _make_in_zone_candidate(self):
        from engine.smc_v2.setup_state import SetupCandidate
        return SetupCandidate(
            symbol="BTC/USDT", direction="SHORT",
            trigger_bar_ts=2_500,
            trigger_price=100.0, htf_bias="BEAR",
            target_zone=ZoneSpec(low=100.0, high=110.0, source="HTF_FVG"),
            htf_swing_anchor=115.0, bars_waited=2,
            state="IN_ZONE",
            confluence_score=75, reasons=[],
        )

    def test_in_zone_transitions_to_confirmed_with_engulfing_df(self, tmp_path):
        from engine.smc_v2.setup_state import SetupStateStore
        store = SetupStateStore(tmp_path / "state.json")
        store.candidates.append(self._make_in_zone_candidate())

        orc = SafeOrchestrator(
            _minimal_config(), state_dir=str(tmp_path), persist=False,
            setup_state_store=store,
        )

        # Engulf at ts=5000 → confirmed
        orc._advance_setup_state_tick(
            symbol="BTC/USDT",
            current_price=102.0,
            current_bar_ts=5_000,
            df_15m=_engulf_df(),
        )
        cand = store.candidates[0]
        assert cand.state == "CONFIRMED"

    def test_in_zone_stays_in_zone_without_engulfing(self, tmp_path):
        """No engulfing pattern → IN_ZONE stays."""
        from engine.smc_v2.setup_state import SetupStateStore
        store = SetupStateStore(tmp_path / "state.json")
        store.candidates.append(self._make_in_zone_candidate())

        orc = SafeOrchestrator(
            _minimal_config(), state_dir=str(tmp_path), persist=False,
            setup_state_store=store,
        )

        # All-bullish DataFrame, no engulfing
        df = pd.DataFrame(
            {"open": [100.0, 101.0, 102.0], "high": [102.0, 103.0, 104.0],
             "low": [99.0, 100.0, 101.0], "close": [101.0, 102.0, 103.0]},
            index=pd.to_datetime([3_000, 4_000, 5_000], unit="ms", utc=True),
        )
        orc._advance_setup_state_tick(
            symbol="BTC/USDT",
            current_price=103.0,
            current_bar_ts=5_000,
            df_15m=df,
        )
        cand = store.candidates[0]
        assert cand.state == "IN_ZONE"


class TestTriggerPhaseInert:
    """PR #S3c-1: orchestrator emits SetupCandidates only when
    setup_state_store is wired. v1 path (store=None) unchanged."""

    def test_inert_when_store_none(self, tmp_path):
        """No store → no _emit_setup_candidates side effect."""
        orc = SafeOrchestrator(_minimal_config(), state_dir=str(tmp_path), persist=False)
        orc._emit_setup_candidates(
            symbol="BTC/USDT",
            htf_bias="BEAR",
            ltf_structure_breaks=[],
            htf_swings={"swing_highs": [], "swing_lows": []},
            htf_bars=[],
            htf_fvgs=[],
            ote_band=(0.0, 0.0),
            ltf_trigger_idx_min=0,
        )

    def test_emits_to_store_when_wired(self, tmp_path):
        from engine.smc_v2.setup_state import SetupStateStore
        from engine.smc import StructBreak, Swing, FVG
        from dataclasses import dataclass

        @dataclass
        class FakeBar:
            ordinal: int
            high: float
            low: float

        store = SetupStateStore(tmp_path / "state.json")
        orc = SafeOrchestrator(
            _minimal_config(), state_dir=str(tmp_path), persist=False,
            setup_state_store=store,
        )
        ltf_brks = [
            StructBreak(kind="CHoCH", direction="BEAR", price=100.0,
                        idx=25, ts="t25", broken_level=95.0),
        ]
        orc._emit_setup_candidates(
            symbol="BTC/USDT",
            htf_bias="BEAR",
            ltf_structure_breaks=ltf_brks,
            htf_swings={"swing_highs": [Swing(120.0, 10, "t10", True)],
                        "swing_lows": []},
            htf_bars=[FakeBar(ordinal=15, high=115, low=100)],
            htf_fvgs=[FVG(top=115.0, bot=110.0, idx=12, ts="t12", direction="BULL")],
            ote_band=(105.0, 108.0),
            ltf_trigger_idx_min=20,
        )
        assert len(store.candidates) == 1
        assert store.candidates[0].symbol == "BTC/USDT"
        assert store.candidates[0].direction == "SHORT"
        assert store.candidates[0].state == "AWAITING_PULLBACK"

    def test_per_symbol_cap_respected(self, tmp_path):
        """If store cap is reached, additional candidates are silently dropped."""
        from engine.smc_v2.setup_state import SetupStateStore, SetupCandidate
        from engine.smc import StructBreak, Swing, FVG
        from dataclasses import dataclass

        @dataclass
        class FakeBar:
            ordinal: int
            high: float
            low: float

        store = SetupStateStore(tmp_path / "state.json", max_pending_per_symbol=1)
        store.add(SetupCandidate(
            symbol="BTC/USDT", direction="SHORT", trigger_bar_ts=10,
            trigger_price=99.0, htf_bias="BEAR",
            target_zone=ZoneSpec(low=100.0, high=110.0, source="HTF_FVG"),
            htf_swing_anchor=120.0, bars_waited=0,
            state="AWAITING_PULLBACK", confluence_score=0, reasons=[],
        ))

        orc = SafeOrchestrator(
            _minimal_config(), state_dir=str(tmp_path), persist=False,
            setup_state_store=store,
        )
        ltf_brks = [
            StructBreak(kind="CHoCH", direction="BEAR", price=100.0,
                        idx=25, ts="t25", broken_level=95.0),
        ]
        orc._emit_setup_candidates(
            symbol="BTC/USDT",
            htf_bias="BEAR",
            ltf_structure_breaks=ltf_brks,
            htf_swings={"swing_highs": [Swing(120.0, 10, "t10", True)],
                        "swing_lows": []},
            htf_bars=[FakeBar(ordinal=15, high=115, low=100)],
            htf_fvgs=[FVG(top=115.0, bot=110.0, idx=12, ts="t12", direction="BULL")],
            ote_band=(105.0, 108.0),
            ltf_trigger_idx_min=20,
        )
        # Cap was 1; pre-existing 1 candidate → new one dropped
        assert len(store.candidates) == 1
