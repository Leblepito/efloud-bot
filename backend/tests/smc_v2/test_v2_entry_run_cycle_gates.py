"""Regression: the v2 entry order path must honour run_cycle's no-new-entry gates.

Bug (2026-11-05): run_cycle advances the SMC v2 state machine
(_advance_setup_state_tick) BEFORE it computes

    can_trade = breaker.can_trade and not stale and not balance_unavailable
                and regime.can_open_new_position and not watch_only

and the tick calls _place_v2_entry_order on every CONFIRMED transition.
_place_v2_entry_order only checks the symbol whitelist, the breaker and the
position guard, so with stale/invalid klines, operation.watch_only: true, or a
failed live balance fetch, v1 stopped trading but v2 still sent a live order.

Required (fail-closed): the state machine still advances (EXPIRE / IN_ZONE
transitions are recorded for operator observability) but NO v2 order is
placed while stale / watch_only / balance-unavailable. The setup is held in its
non-terminal state (same as the Po3 gate) so it can still enter on a later,
healthy tick.

The regime gate (RANGING blocks new entries) is deliberately NOT applied to v2
here — that is a separate operator decision.
"""
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pandas as pd

from engine.safe_orchestrator import SafeOrchestrator
from engine.smc_v2.setup_state import SetupCandidate, SetupStateStore
from engine.smc_v2.zones import ZoneSpec

PRICE = 95_000.0
SYMBOL = "BTC/USDT"


def _config(watch_only=False, dry_run=False, require_confirmation=False):
    cfg = {
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
        "operation": {"check_interval_sec": 30, "log_level": "INFO",
                      "watch_only": watch_only, "dry_run": dry_run},
    }
    if not require_confirmation:
        # No engulfing needed: an AWAITING_REENTRY candidate re-entering its
        # zone goes straight to CONFIRMED -> _place_v2_entry_order.
        cfg["smc_v2"] = {"require_confirmation": False}
    # else: key absent -> require_confirmation defaults to True, exactly like
    # configs/config.phase2_1k.yaml (live): IN_ZONE + engulfing -> CONFIRMED.
    return cfg


def _df(end, engulf=False):
    idx = pd.date_range(end=end, periods=60, freq="15min", tz="UTC")
    df = pd.DataFrame({
        "open": [PRICE] * 60, "high": [PRICE * 1.001] * 60,
        "low": [PRICE * 0.999] * 60, "close": [PRICE] * 60,
        "volume": [1000.0] * 60,
    }, index=idx)
    if engulf:
        # prior bullish 95000->95400, current bearish 95450->94900 engulfs it;
        # close 94900 is inside the 94000-96000 zone -> SHORT confirmation.
        df.iloc[-2, :4] = [PRICE, PRICE + 500, PRICE - 50, PRICE + 400]
        df.iloc[-1, :4] = [PRICE + 450, PRICE + 500, PRICE - 150, PRICE - 100]
    return df


def _fresh_df(engulf=False):
    return _df(datetime.now(timezone.utc), engulf)


def _stale_df(engulf=False):
    # 3 days old: fails validate_kline_freshness on every TF (4h * 2.5 = 10h).
    return _df(datetime.now(timezone.utc) - timedelta(days=3), engulf)


def _cand(state="AWAITING_REENTRY", has_left_zone=True):
    return SetupCandidate(
        symbol=SYMBOL, direction="SHORT", trigger_bar_ts=1_000,
        trigger_price=PRICE, htf_bias="BEAR",
        target_zone=ZoneSpec(low=PRICE - 1_000, high=PRICE + 1_000, source="HTF_FVG"),
        htf_swing_anchor=PRICE + 2_000, bars_waited=0, state=state,
        confluence_score=75, reasons=[], has_left_zone=has_left_zone,
    )


def _orch(tmp_path, cand, **cfg):
    store = SetupStateStore(tmp_path / "setup_state.json")
    store.candidates.append(cand)
    orc = SafeOrchestrator(
        _config(**cfg), state_dir=str(tmp_path), persist=False,
        setup_state_store=store, freshness_check=True,
    )
    return orc, store


def _cycle(orc, df, balance=10_000.0):
    return orc.run_cycle(symbol=SYMBOL, df_htf=df, df_mtf=df, df_entry=df,
                         balance=balance)


def _held(store):
    return [c for c in store.candidates if c.symbol == SYMBOL]


class TestV2EntryHonoursNoTradeGates:
    def test_control_fresh_tick_places_v2_order(self, tmp_path):
        """Harness sanity: a healthy tick DOES reach the v2 order path."""
        orc, _ = _orch(tmp_path, _cand())
        with patch.object(orc, "_place_v2_entry_order") as spy:
            _cycle(orc, _fresh_df())
        assert spy.call_count == 1

    def test_stale_tick_places_no_v2_order(self, tmp_path):
        orc, store = _orch(tmp_path, _cand())
        with patch.object(orc, "_place_v2_entry_order") as spy:
            result = _cycle(orc, _stale_df())
        assert result.stale_data is True
        assert spy.call_count == 0
        # Held, not consumed: still waiting in its non-terminal state.
        assert [c.state for c in _held(store)] == ["AWAITING_REENTRY"]

    def test_watch_only_places_no_v2_order(self, tmp_path):
        orc, store = _orch(tmp_path, _cand(), watch_only=True)
        with patch.object(orc, "_place_v2_entry_order") as spy:
            _cycle(orc, _fresh_df())
        assert spy.call_count == 0
        assert [c.state for c in _held(store)] == ["AWAITING_REENTRY"]

    def test_live_balance_unavailable_places_no_v2_order(self, tmp_path):
        orc, store = _orch(tmp_path, _cand())
        with patch.object(orc, "_place_v2_entry_order") as spy:
            _cycle(orc, _fresh_df(), balance=None)
        assert spy.call_count == 0
        assert [c.state for c in _held(store)] == ["AWAITING_REENTRY"]

    def test_dry_run_balance_none_is_exempt(self, tmp_path):
        """Mirrors v1 C4: dry-run passes balance=None legitimately."""
        orc, _ = _orch(tmp_path, _cand(), dry_run=True)
        with patch.object(orc, "_place_v2_entry_order") as spy:
            _cycle(orc, _fresh_df(), balance=None)
        assert spy.call_count == 1

    def test_held_setup_enters_on_next_healthy_tick(self, tmp_path):
        orc, _ = _orch(tmp_path, _cand())
        with patch.object(orc, "_place_v2_entry_order") as spy:
            _cycle(orc, _stale_df())
            assert spy.call_count == 0
            _cycle(orc, _fresh_df())
            assert spy.call_count == 1


class TestStateMachineStillAdvancesWhenGated:
    def test_stale_tick_still_records_in_zone_transition(self, tmp_path):
        orc, store = _orch(tmp_path, _cand(state="AWAITING_PULLBACK", has_left_zone=False))
        with patch.object(orc, "_place_v2_entry_order") as spy:
            _cycle(orc, _stale_df())
        assert spy.call_count == 0
        assert [c.state for c in _held(store)] == ["IN_ZONE"]

    def test_watch_only_tick_still_expires_timed_out_setup(self, tmp_path):
        cand = _cand()
        cand.bars_waited = 8  # default pullback_timeout_bars=8 -> 9 > 8 on this bar
        orc, store = _orch(tmp_path, cand, watch_only=True)
        with patch.object(orc, "_place_v2_entry_order") as spy:
            _cycle(orc, _fresh_df())
        assert spy.call_count == 0
        # EXPIRED is terminal and pruned by store.save() at the end of run_cycle.
        assert _held(store) == []


class TestLiveDefaultConfirmationPath:
    """require_confirmation=True (live default): IN_ZONE + engulfing -> order."""

    def _orch(self, tmp_path, **cfg):
        return _orch(tmp_path, _cand(state="IN_ZONE"), require_confirmation=True, **cfg)

    def test_control_fresh_engulfing_places_v2_order(self, tmp_path):
        orc, _ = self._orch(tmp_path)
        with patch.object(orc, "_place_v2_entry_order") as spy:
            _cycle(orc, _fresh_df(engulf=True))
        assert spy.call_count == 1
        assert spy.call_args.kwargs["entry_price"] == PRICE - 100

    def test_stale_engulfing_places_no_v2_order(self, tmp_path):
        orc, store = self._orch(tmp_path)
        with patch.object(orc, "_place_v2_entry_order") as spy:
            _cycle(orc, _stale_df(engulf=True))
        assert spy.call_count == 0
        assert [c.state for c in _held(store)] == ["IN_ZONE"]

    def test_watch_only_engulfing_places_no_v2_order(self, tmp_path):
        orc, store = self._orch(tmp_path, watch_only=True)
        with patch.object(orc, "_place_v2_entry_order") as spy:
            _cycle(orc, _fresh_df(engulf=True))
        assert spy.call_count == 0
        assert [c.state for c in _held(store)] == ["IN_ZONE"]

    def test_balance_unavailable_engulfing_places_no_v2_order(self, tmp_path):
        orc, store = self._orch(tmp_path)
        with patch.object(orc, "_place_v2_entry_order") as spy:
            _cycle(orc, _fresh_df(engulf=True), balance=None)
        assert spy.call_count == 0
        assert [c.state for c in _held(store)] == ["IN_ZONE"]
