"""Tests for SMC v2 SetupStateStore wiring in SafeOrchestrator.

PR #S2b ships ONLY the inert opt-in scaffold:
- `setup_state_store` parameter (default None → no behavior change)
- `_advance_setup_state_tick` method (no-op when store is None)
- `confirm_entry` placeholder (always False)

Trigger phase and real confirmation land in PR #S3.
"""
from unittest.mock import MagicMock, patch
import pytest

from engine.safe_orchestrator import SafeOrchestrator


@pytest.fixture
def minimal_config():
    """Smallest config dict that lets SafeOrchestrator construct.

    Mirrors the shape used by existing safe_orchestrator tests in this repo.
    """
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


class TestSetupStateStoreParameter:
    """The new `setup_state_store` parameter is optional and defaults to None.
    When None (default), no behavior changes vs v1."""

    def test_default_none_when_not_passed(self, minimal_config, tmp_path):
        orc = SafeOrchestrator(minimal_config, state_dir=str(tmp_path), persist=False)
        assert orc.setup_state_store is None

    def test_store_attribute_set_when_passed(self, minimal_config, tmp_path):
        from engine.smc_v2.setup_state import SetupStateStore
        store = SetupStateStore(tmp_path / "setup_candidates.json")
        orc = SafeOrchestrator(
            minimal_config,
            state_dir=str(tmp_path),
            persist=False,
            setup_state_store=store,
        )
        assert orc.setup_state_store is store


class TestConfirmEntryPlaceholder:
    """confirm_entry is a stub in PR #S2b — always returns (False, None).
    Real LTF CHoCH/engulfing detection lands in PR #S3.

    The stub MUST exist so _advance_setup_state_tick can call it without
    AttributeError. Tests pin the contract: signature, return type, no
    side effects.
    """

    def test_returns_false_none_tuple(self, minimal_config, tmp_path):
        from engine.smc_v2.zones import ZoneSpec
        orc = SafeOrchestrator(minimal_config, state_dir=str(tmp_path), persist=False)
        result = orc.confirm_entry(
            df_15m=MagicMock(),
            zone=ZoneSpec(low=100.0, high=110.0, source="HTF_FVG"),
            direction="SHORT",
            since_ts=1700000000000,
        )
        assert result == (False, None)

    def test_does_not_mutate_inputs(self, minimal_config, tmp_path):
        from engine.smc_v2.zones import ZoneSpec
        orc = SafeOrchestrator(minimal_config, state_dir=str(tmp_path), persist=False)
        zone = ZoneSpec(low=100.0, high=110.0, source="HTF_FVG")
        orig_low, orig_high = zone.low, zone.high
        orc.confirm_entry(df_15m=MagicMock(), zone=zone, direction="LONG",
                          since_ts=1700000000000)
        assert zone.low == orig_low
        assert zone.high == orig_high


class TestAdvanceSetupStateTick:
    """_advance_setup_state_tick(symbol, current_price, current_bar_ts) operates
    on candidates in self.setup_state_store. Per-tick semantics:

    - bars_waited += 1 (incremented BEFORE timeout check)
    - if bars_waited > timeout: state = EXPIRED, dropped at next save
    - elif AWAITING_PULLBACK and price ∈ zone: state = IN_ZONE
    - if IN_ZONE: call self.confirm_entry; if True, state = CONFIRMED
                  (stub returns False in PR #S2b → nothing happens)

    All operations are scoped to candidates matching `symbol`. Other-symbol
    candidates are untouched in this tick.
    """

    @pytest.fixture
    def store_with_pending(self, tmp_path):
        from engine.smc_v2.setup_state import SetupCandidate, SetupStateStore
        from engine.smc_v2.zones import ZoneSpec
        store = SetupStateStore(tmp_path / "state.json")
        store.add(SetupCandidate(
            symbol="BTC/USDT", direction="SHORT",
            trigger_bar_ts=1700000000000, trigger_price=95000.0,
            htf_bias="BEAR",
            target_zone=ZoneSpec(low=96000.0, high=97000.0, source="HTF_FVG"),
            htf_swing_anchor=98000.0, bars_waited=0,
            state="AWAITING_PULLBACK", confluence_score=75, reasons=[],
        ))
        return store

    def test_inert_when_store_is_none(self, minimal_config, tmp_path):
        """Default-inert: with no store, the method short-circuits with no error."""
        orc = SafeOrchestrator(minimal_config, state_dir=str(tmp_path), persist=False)
        # Explicit precondition: the inert path requires setup_state_store=None
        assert orc.setup_state_store is None
        # Should NOT raise even though setup_state_store is None
        orc._advance_setup_state_tick(
            symbol="BTC/USDT", current_price=96500.0, current_bar_ts=1700000060000,
        )
        # Method short-circuited cleanly (no exception, no state mutation)

    def test_bars_waited_increments(self, minimal_config, tmp_path, store_with_pending):
        orc = SafeOrchestrator(
            minimal_config, state_dir=str(tmp_path), persist=False,
            setup_state_store=store_with_pending,
        )
        orc._advance_setup_state_tick(
            symbol="BTC/USDT", current_price=95500.0,  # outside zone, no transition
            current_bar_ts=1700000060000,
        )
        cand = store_with_pending.candidates[0]
        assert cand.bars_waited == 1
        assert cand.state == "AWAITING_PULLBACK"  # still pending, no zone entry

    def test_price_in_zone_transitions_to_in_zone(
        self, minimal_config, tmp_path, store_with_pending
    ):
        orc = SafeOrchestrator(
            minimal_config, state_dir=str(tmp_path), persist=False,
            setup_state_store=store_with_pending,
        )
        orc._advance_setup_state_tick(
            symbol="BTC/USDT", current_price=96500.0,  # inside [96000, 97000]
            current_bar_ts=1700000060000,
        )
        cand = store_with_pending.candidates[0]
        assert cand.bars_waited == 1
        assert cand.state == "IN_ZONE"

    def test_other_symbol_untouched(
        self, minimal_config, tmp_path, store_with_pending
    ):
        """Ticking BTC must not increment ETH/USDT candidates."""
        from engine.smc_v2.setup_state import SetupCandidate
        from engine.smc_v2.zones import ZoneSpec
        store_with_pending.add(SetupCandidate(
            symbol="ETH/USDT", direction="LONG",
            trigger_bar_ts=1700000000000, trigger_price=2400.0,
            htf_bias="BULL",
            target_zone=ZoneSpec(low=2380.0, high=2390.0, source="OTE"),
            htf_swing_anchor=2350.0, bars_waited=0,
            state="AWAITING_PULLBACK", confluence_score=60, reasons=[],
        ))
        orc = SafeOrchestrator(
            minimal_config, state_dir=str(tmp_path), persist=False,
            setup_state_store=store_with_pending,
        )
        orc._advance_setup_state_tick(
            symbol="BTC/USDT", current_price=96500.0,
            current_bar_ts=1700000060000,
        )
        btc = next(c for c in store_with_pending.candidates if c.symbol == "BTC/USDT")
        eth = next(c for c in store_with_pending.candidates if c.symbol == "ETH/USDT")
        assert btc.bars_waited == 1
        assert eth.bars_waited == 0  # untouched

    def test_expire_on_timeout(self, minimal_config, tmp_path):
        """bars_waited > 8 (default timeout) → state = EXPIRED."""
        from engine.smc_v2.setup_state import SetupCandidate, SetupStateStore
        from engine.smc_v2.zones import ZoneSpec
        store = SetupStateStore(tmp_path / "state.json")
        # Already at bars_waited=8, next tick will push it to 9 > 8 → EXPIRE
        store.add(SetupCandidate(
            symbol="BTC/USDT", direction="SHORT",
            trigger_bar_ts=1700000000000, trigger_price=95000.0,
            htf_bias="BEAR",
            target_zone=ZoneSpec(low=96000.0, high=97000.0, source="HTF_FVG"),
            htf_swing_anchor=98000.0, bars_waited=8,
            state="AWAITING_PULLBACK", confluence_score=75, reasons=[],
        ))
        orc = SafeOrchestrator(
            minimal_config, state_dir=str(tmp_path), persist=False,
            setup_state_store=store,
        )
        orc._advance_setup_state_tick(
            symbol="BTC/USDT", current_price=95500.0,
            current_bar_ts=1700000540000,
        )
        cand = store.candidates[0]
        assert cand.state == "EXPIRED"

    def test_in_zone_calls_confirm_entry(
        self, minimal_config, tmp_path, store_with_pending
    ):
        """When state advances to IN_ZONE AND df_15m is provided,
        confirm_entry is called. PR #S3b added the df_15m-None skip;
        this test provides a fake df_15m so the spy assertion still holds.
        Patched confirm_entry returns (False, None) so state stays IN_ZONE."""
        import pandas as pd
        orc = SafeOrchestrator(
            minimal_config, state_dir=str(tmp_path), persist=False,
            setup_state_store=store_with_pending,
        )
        # Provide a non-None df_15m so PR #S3b's df_15m-None skip doesn't trigger
        fake_df = pd.DataFrame(
            {"open": [1.0], "high": [1.0], "low": [1.0], "close": [1.0]},
            index=pd.to_datetime([1_700_000_060_000], unit="ms", utc=True),
        )
        # Patch confirm_entry to spy on the call
        with patch.object(orc, "confirm_entry", return_value=(False, None)) as spy:
            orc._advance_setup_state_tick(
                symbol="BTC/USDT", current_price=96500.0,
                current_bar_ts=1700000060000, df_15m=fake_df,
            )
            assert spy.call_count == 1
            call_kwargs = spy.call_args.kwargs
            # confirm_entry should be called with the zone, direction, trigger_ts
            assert call_kwargs["direction"] == "SHORT"
            assert call_kwargs["since_ts"] == 1700000000000
        # state remains IN_ZONE (confirm returned False)
        assert store_with_pending.candidates[0].state == "IN_ZONE"

    def test_already_in_zone_stays_in_zone(
        self, minimal_config, tmp_path
    ):
        """A candidate already in IN_ZONE state stays IN_ZONE; only bars_waited
        increments (IN_ZONE is sticky per spec §3 state diagram)."""
        from engine.smc_v2.setup_state import SetupCandidate, SetupStateStore
        from engine.smc_v2.zones import ZoneSpec
        store = SetupStateStore(tmp_path / "state.json")
        store.add(SetupCandidate(
            symbol="BTC/USDT", direction="SHORT",
            trigger_bar_ts=1700000000000, trigger_price=95000.0,
            htf_bias="BEAR",
            target_zone=ZoneSpec(low=96000.0, high=97000.0, source="HTF_FVG"),
            htf_swing_anchor=98000.0, bars_waited=3,
            state="IN_ZONE", confluence_score=75, reasons=[],
        ))
        orc = SafeOrchestrator(
            minimal_config, state_dir=str(tmp_path), persist=False,
            setup_state_store=store,
        )
        # Price now OUTSIDE the zone — IN_ZONE must stay (sticky)
        orc._advance_setup_state_tick(
            symbol="BTC/USDT", current_price=95500.0,
            current_bar_ts=1700000240000,
        )
        cand = store.candidates[0]
        assert cand.state == "IN_ZONE"
        assert cand.bars_waited == 4

    def test_confirmed_setup_not_re_processed(self, minimal_config, tmp_path):
        """CONFIRMED state is terminal — advance must not touch it."""
        from engine.smc_v2.setup_state import SetupCandidate, SetupStateStore
        from engine.smc_v2.zones import ZoneSpec
        store = SetupStateStore(tmp_path / "state.json")
        store.candidates.append(SetupCandidate(
            symbol="BTC/USDT", direction="SHORT",
            trigger_bar_ts=1700000000000, trigger_price=95000.0,
            htf_bias="BEAR",
            target_zone=ZoneSpec(low=96000.0, high=97000.0, source="HTF_FVG"),
            htf_swing_anchor=98000.0, bars_waited=5,
            state="CONFIRMED", confluence_score=75, reasons=[],
        ))
        orc = SafeOrchestrator(
            minimal_config, state_dir=str(tmp_path), persist=False,
            setup_state_store=store,
        )
        orc._advance_setup_state_tick(
            symbol="BTC/USDT", current_price=96500.0,
            current_bar_ts=1700000060000,
        )
        cand = store.candidates[0]
        assert cand.bars_waited == 5  # untouched
        assert cand.state == "CONFIRMED"


class TestRunCycleAdvanceCall:
    """run_cycle calls _advance_setup_state_tick when store is wired.
    When store is None (default), the method is NOT called (inert path
    must remain truly inert — no overhead even from spying)."""

    def _make_df(self, length=50, base_price=95000.0):
        """Construct a minimal valid OHLCV DataFrame for run_cycle.
        Real shape: DatetimeIndex (UTC), columns [open,high,low,close,volume]."""
        import pandas as pd
        from datetime import datetime, timezone, timedelta
        idx = pd.date_range(
            end=datetime.now(timezone.utc), periods=length, freq="15min", tz="UTC",
        )
        df = pd.DataFrame({
            "open": [base_price] * length,
            "high": [base_price * 1.001] * length,
            "low": [base_price * 0.999] * length,
            "close": [base_price] * length,
            "volume": [1000.0] * length,
        }, index=idx)
        return df

    def test_advance_called_when_store_wired(self, minimal_config, tmp_path):
        from engine.smc_v2.setup_state import SetupStateStore
        store = SetupStateStore(tmp_path / "state.json")
        orc = SafeOrchestrator(
            minimal_config, state_dir=str(tmp_path), persist=False,
            setup_state_store=store, freshness_check=False,
        )
        df = self._make_df()
        with patch.object(orc, "_advance_setup_state_tick") as spy:
            orc.run_cycle(
                symbol="BTC/USDT", df_htf=df, df_mtf=df, df_entry=df,
                balance=10000.0,
            )
            assert spy.call_count == 1
            # Called with current price (last close of df_entry)
            assert spy.call_args.kwargs["symbol"] == "BTC/USDT"
            assert spy.call_args.kwargs["current_price"] == 95000.0

    def test_advance_not_called_when_store_none(self, minimal_config, tmp_path):
        """Inert default: no spy call, no overhead, no v1 behavior change."""
        orc = SafeOrchestrator(
            minimal_config, state_dir=str(tmp_path), persist=False,
            freshness_check=False,
        )
        df = self._make_df()
        with patch.object(orc, "_advance_setup_state_tick") as spy:
            orc.run_cycle(
                symbol="BTC/USDT", df_htf=df, df_mtf=df, df_entry=df,
                balance=10000.0,
            )
            # When store is None, run_cycle must NOT call the advance method
            assert spy.call_count == 0


class TestRunCycleSaveState:
    """After run_cycle advances candidates, the orchestrator MUST call
    store.save() so state survives restart. Inert when store is None."""

    def _make_df(self, length=50, base_price=95000.0):
        import pandas as pd
        from datetime import datetime, timezone
        idx = pd.date_range(
            end=datetime.now(timezone.utc), periods=length, freq="15min", tz="UTC",
        )
        return pd.DataFrame({
            "open": [base_price] * length,
            "high": [base_price * 1.001] * length,
            "low": [base_price * 0.999] * length,
            "close": [base_price] * length,
            "volume": [1000.0] * length,
        }, index=idx)

    def test_save_called_when_store_wired(self, minimal_config, tmp_path):
        from engine.smc_v2.setup_state import SetupStateStore
        store = SetupStateStore(tmp_path / "state.json")
        orc = SafeOrchestrator(
            minimal_config, state_dir=str(tmp_path), persist=False,
            setup_state_store=store, freshness_check=False,
        )
        df = self._make_df()
        with patch.object(store, "save") as spy:
            orc.run_cycle(
                symbol="BTC/USDT", df_htf=df, df_mtf=df, df_entry=df,
                balance=10000.0,
            )
            assert spy.call_count == 1

    def test_save_not_called_when_store_none(self, minimal_config, tmp_path):
        """Inert default: no save attempt (no AttributeError, no overhead)."""
        orc = SafeOrchestrator(
            minimal_config, state_dir=str(tmp_path), persist=False,
            freshness_check=False,
        )
        df = self._make_df()
        # Should complete without AttributeError (no store.save attempt)
        orc.run_cycle(
            symbol="BTC/USDT", df_htf=df, df_mtf=df, df_entry=df,
            balance=10000.0,
        )

    def test_save_called_even_on_no_candidates(self, minimal_config, tmp_path):
        """Empty store still saves (writes empty file) — operator can confirm
        the orchestrator is actively persisting."""
        from engine.smc_v2.setup_state import SetupStateStore
        store = SetupStateStore(tmp_path / "state.json")
        # No candidates added
        orc = SafeOrchestrator(
            minimal_config, state_dir=str(tmp_path), persist=False,
            setup_state_store=store, freshness_check=False,
        )
        df = self._make_df()
        with patch.object(store, "save") as spy:
            orc.run_cycle(
                symbol="BTC/USDT", df_htf=df, df_mtf=df, df_entry=df,
                balance=10000.0,
            )
            assert spy.call_count == 1
