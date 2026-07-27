"""BT-23: entry-distance gate inside SafeOrchestrator._emit_setup_candidates.

WHY THIS TEST EXISTS
--------------------
A 30-day / 10-symbol full-pipeline replay showed that not one setup whose
target zone sat further than 4.0x the 15m Wilder ATR(14) from the live price
at emit time ever reached CONFIRMED (0 / 1400). Those dead setups still
consumed SetupStateStore's per-symbol pending cap and evicted reachable ones.
The gate drops them at emit. `smc_v2.max_entry_dist_atr` is the knob; the
default of 0.0 disables it, and an uncomputable ATR skips it, so the gate can
only ever remove setups the replay proved worthless -- never starve the book.

These tests pin the four behaviours that matter:
  1. knob absent / 0.0            -> gate inert, every candidate added
  2. knob 6.0                     -> far candidate dropped, near one kept
  3. ATR uncomputable (short df)  -> fail-open, every candidate added
  4. SHORT direction              -> distance sign measured from the LOW edge

BT-25 (2026-07-27) adds a SECOND, independent gate in the same loop:
`smc_v2.max_zone_overshoot_atr`. BT-23 is one-sided -- it only rejects a zone
too far AHEAD of price, so a zone price has already blown straight through
produces a NEGATIVE near-edge distance and sails through. v2_doctor caught that
live: BNB/USDT bias=BEAR emitted a SHORT whose zone sat 4.2 ATR BELOW price.
The overshoot gate measures the FAR edge instead (width-independent), and its
absence -- not 0.0 -- is the OFF value, because 0.0 means "reject the instant
price is past the far edge". See TestZoneOvershootGate below.
"""
import pandas as pd
import pytest

from engine.smc_v2.setup_state import SetupCandidate
from engine.smc_v2.zones import ZoneSpec


# --- fixtures ---------------------------------------------------------------

class _RecordingStore:
    """Stand-in for SetupStateStore: records what survived the gate.

    A real store would also apply DEFAULT_MAX_PENDING_PER_SYMBOL=3, which is
    exactly the coupling under test -- so it is deliberately not used here.
    """

    def __init__(self):
        self.added = []

    def add(self, cand):
        self.added.append(cand)
        return True


def _flat_df(bars: int) -> pd.DataFrame:
    """OHLC frame whose true range is a constant 100 -> Wilder ATR(14) == 100."""
    return pd.DataFrame({
        "open": [10050.0] * bars,
        "high": [10100.0] * bars,
        "low": [10000.0] * bars,
        "close": [10050.0] * bars,
    })


def _cand(direction: str, low: float, high: float) -> SetupCandidate:
    return SetupCandidate(
        symbol="BTC/USDT",
        direction=direction,
        trigger_bar_ts=1_700_000_000_000,
        trigger_price=10_000.0,
        htf_bias="BULL" if direction == "LONG" else "BEAR",
        target_zone=ZoneSpec(low=low, high=high, source="OTE"),
        htf_swing_anchor=9_000.0,
        bars_waited=0,
        state="AWAITING_PULLBACK",
        confluence_score=3,
        reasons=["test"],
    )


def _orch(monkeypatch, candidates, max_entry_dist_atr=None,
          max_zone_overshoot_atr=None):
    """Bare orchestrator carrying only what the gates read.

    Passing None for either knob leaves the key ABSENT from the config dict,
    which is the OFF state for both. That distinction matters for BT-25: 0.0
    is a live setting there, not a disable.
    """
    from engine.safe_orchestrator import SafeOrchestrator
    import engine.smc_v2.triggers as triggers

    smc_v2 = {}
    if max_entry_dist_atr is not None:
        smc_v2["max_entry_dist_atr"] = max_entry_dist_atr
    if max_zone_overshoot_atr is not None:
        smc_v2["max_zone_overshoot_atr"] = max_zone_overshoot_atr

    orch = SafeOrchestrator.__new__(SafeOrchestrator)
    orch.config = {"smc_v2": smc_v2}
    orch.setup_state_store = _RecordingStore()

    monkeypatch.setattr(
        triggers, "generate_setup_candidates",
        lambda **kwargs: list(candidates),
    )
    return orch


def _emit(orch, current_price=10_000.0, df_entry=None):
    orch._emit_setup_candidates(
        symbol="BTC/USDT",
        htf_bias="BULL",
        ltf_structure_breaks=[],
        htf_swings={"swing_highs": [], "swing_lows": []},
        htf_bars=[],
        htf_fvgs=[],
        ote_band=(9_000.0, 9_500.0),
        ltf_trigger_idx_min=0,
        current_price=current_price,
        df_entry=df_entry,
    )
    return orch.setup_state_store.added


# --- tests ------------------------------------------------------------------

class TestEmitDistanceGate:

    def test_knob_absent_gate_is_inert(self, monkeypatch):
        """No max_entry_dist_atr in config -> nothing is dropped, however far."""
        near = _cand("LONG", 9_600.0, 9_700.0)      # 3 ATR away
        far = _cand("LONG", 7_900.0, 8_000.0)       # 20 ATR away
        orch = _orch(monkeypatch, [near, far])      # knob absent entirely
        assert _emit(orch, df_entry=_flat_df(30)) == [near, far]

    def test_knob_zero_gate_is_inert(self, monkeypatch):
        """Explicit 0.0 is the documented OFF value."""
        near = _cand("LONG", 9_600.0, 9_700.0)
        far = _cand("LONG", 7_900.0, 8_000.0)
        orch = _orch(monkeypatch, [near, far], max_entry_dist_atr=0.0)
        assert _emit(orch, df_entry=_flat_df(30)) == [near, far]

    def test_long_far_candidate_dropped(self, monkeypatch):
        """LONG: distance is price -> zone HIGH edge. 20 ATR > 6.0 -> dropped."""
        near = _cand("LONG", 9_600.0, 9_700.0)      # (10000-9700)/100 = 3.0
        far = _cand("LONG", 7_900.0, 8_000.0)       # (10000-8000)/100 = 20.0
        orch = _orch(monkeypatch, [near, far], max_entry_dist_atr=6.0)
        assert _emit(orch, df_entry=_flat_df(30)) == [near]
        assert orch._v2_gate_rejects == 1

    def test_short_far_candidate_dropped(self, monkeypatch):
        """SHORT: distance is zone LOW edge -> price. Sign must not flip."""
        near = _cand("SHORT", 10_300.0, 10_400.0)   # (10300-10000)/100 = 3.0
        far = _cand("SHORT", 12_000.0, 12_100.0)    # (12000-10000)/100 = 20.0
        orch = _orch(monkeypatch, [near, far], max_entry_dist_atr=6.0)
        assert _emit(orch, df_entry=_flat_df(30)) == [near]
        assert orch._v2_gate_rejects == 1

    def test_boundary_is_inclusive(self, monkeypatch):
        """Exactly at the limit passes -- the drop test is strictly greater-than."""
        at = _cand("LONG", 9_300.0, 9_400.0)        # (10000-9400)/100 = 6.0
        just_over = _cand("LONG", 9_290.0, 9_399.0)  # 6.01
        orch = _orch(monkeypatch, [at, just_over], max_entry_dist_atr=6.0)
        assert _emit(orch, df_entry=_flat_df(30)) == [at]

    def test_price_inside_or_past_zone_never_dropped(self, monkeypatch):
        """Negative distance (price already at/past the zone) must survive.

        BT-25 note: this stays true and is NOT a regression -- it is the exact
        hole BT-25 documents. `max_entry_dist_atr` alone can never reject an
        overshot zone, by construction. This test never sets
        `max_zone_overshoot_atr`, so it pins the BT-23 gate in isolation;
        TestZoneOvershootGate covers the other side.
        """
        inside = _cand("LONG", 9_900.0, 10_100.0)   # near edge above price
        orch = _orch(monkeypatch, [inside], max_entry_dist_atr=6.0)
        assert _emit(orch, df_entry=_flat_df(30)) == [inside]

    def test_atr_uncomputable_fails_open(self, monkeypatch):
        """Frame shorter than period+1 -> wilder_atr None -> nothing dropped."""
        far = _cand("LONG", 7_900.0, 8_000.0)       # 20 ATR if ATR existed
        orch = _orch(monkeypatch, [far], max_entry_dist_atr=6.0)
        assert _emit(orch, df_entry=_flat_df(5)) == [far]

    def test_no_df_entry_fails_open(self, monkeypatch):
        """Caller that never passes a frame keeps the pre-BT-23 behaviour."""
        far = _cand("LONG", 7_900.0, 8_000.0)
        orch = _orch(monkeypatch, [far], max_entry_dist_atr=6.0)
        assert _emit(orch, df_entry=None) == [far]

    def test_no_current_price_fails_open(self, monkeypatch):
        far = _cand("LONG", 7_900.0, 8_000.0)
        orch = _orch(monkeypatch, [far], max_entry_dist_atr=6.0)
        assert _emit(orch, current_price=None, df_entry=_flat_df(30)) == [far]

    def test_store_none_short_circuits(self, monkeypatch):
        """Inert when the v2 store is not wired -- unchanged by BT-23."""
        orch = _orch(monkeypatch, [_cand("LONG", 7_900.0, 8_000.0)],
                     max_entry_dist_atr=6.0)
        orch.setup_state_store = None
        # _emit() reads the store back, so call the method directly here.
        orch._emit_setup_candidates(
            symbol="BTC/USDT", htf_bias="BULL", ltf_structure_breaks=[],
            htf_swings={"swing_highs": [], "swing_lows": []}, htf_bars=[],
            htf_fvgs=[], ote_band=(9_000.0, 9_500.0), ltf_trigger_idx_min=0,
            current_price=10_000.0, df_entry=_flat_df(30),
        )  # must not raise


class TestZoneOvershootGate:
    """BT-25: reject zones price has already travelled PAST.

    Geometry, with ATR == 100 and current_price == 10_000 throughout:

      LONG  -> zone sits BELOW price, price falls in, far edge = zone LOW.
               overshoot = (zone_low - price) / atr
               zone_low ABOVE price  => positive => price fell through the zone
      SHORT -> zone sits ABOVE price, price rises in, far edge = zone HIGH.
               overshoot = (price - zone_high) / atr
               zone_high BELOW price => positive => price rose past the zone

    The far edge is used rather than the near edge on purpose: a near-edge
    rule would be zone-width sensitive and would falsely reject price sitting
    legitimately inside a wide (1-3 ATR) OTE band.
    """

    def test_knob_absent_gate_is_inert(self, monkeypatch):
        """No max_zone_overshoot_atr -> an overshot zone still gets added.

        This is the pre-BT-25 live behaviour and must be what an un-migrated
        config keeps doing.
        """
        past = _cand("LONG", 10_200.0, 10_300.0)     # overshoot +2.0
        orch = _orch(monkeypatch, [past], max_entry_dist_atr=6.0)
        assert _emit(orch, df_entry=_flat_df(30)) == [past]

    def test_long_overshot_zone_dropped(self, monkeypatch):
        """LONG whose zone is entirely above price: price already fell past."""
        normal = _cand("LONG", 9_600.0, 9_700.0)     # overshoot (9600-10000)/100 = -4.0
        past = _cand("LONG", 10_200.0, 10_300.0)     # overshoot (10200-10000)/100 = +2.0
        orch = _orch(monkeypatch, [normal, past], max_zone_overshoot_atr=0.5)
        assert _emit(orch, df_entry=_flat_df(30)) == [normal]
        assert orch._v2_gate_rejects == 1

    def test_short_overshot_zone_dropped(self, monkeypatch):
        """SHORT whose zone is entirely below price -- the live BNB/USDT case.

        v2_doctor logged BNB bias=BEAR, EMIT=1, dist_atr=[-4.2]: the SHORT
        target zone was 4.2 ATR BELOW price. BT-23 measures -4.2 and lets it
        through; here it is rejected.
        """
        normal = _cand("SHORT", 10_300.0, 10_400.0)  # overshoot (10000-10400)/100 = -4.0
        past = _cand("SHORT", 9_580.0, 9_620.0)      # overshoot (10000-9620)/100 = +3.8
        orch = _orch(monkeypatch, [normal, past], max_zone_overshoot_atr=0.5)
        assert _emit(orch, df_entry=_flat_df(30)) == [normal]
        assert orch._v2_gate_rejects == 1

    def test_price_inside_zone_is_kept(self, monkeypatch):
        """Price straddled by a WIDE zone must survive -- the reason the far
        edge is measured instead of the near one. Zone is 2 ATR wide and
        contains the price; a near-edge rule would have rejected it."""
        wide = _cand("LONG", 9_900.0, 10_100.0)      # overshoot (9900-10000)/100 = -1.0
        orch = _orch(monkeypatch, [wide], max_zone_overshoot_atr=0.5)
        assert _emit(orch, df_entry=_flat_df(30)) == [wide]

    def test_price_exactly_on_far_edge_is_kept(self, monkeypatch):
        """overshoot == 0.0 with the knob at 0.0 -> strictly-greater-than keeps it."""
        touching = _cand("LONG", 10_000.0, 10_100.0)  # overshoot exactly 0.0
        orch = _orch(monkeypatch, [touching], max_zone_overshoot_atr=0.0)
        assert _emit(orch, df_entry=_flat_df(30)) == [touching]

    def test_zero_is_a_live_setting_not_off(self, monkeypatch):
        """0.0 must NOT read as disabled -- that is why absence is the OFF value.

        One tick past the far edge is enough to reject when the knob is 0.0.
        """
        one_tick_past = _cand("LONG", 10_001.0, 10_100.0)   # overshoot +0.01
        orch = _orch(monkeypatch, [one_tick_past], max_zone_overshoot_atr=0.0)
        assert _emit(orch, df_entry=_flat_df(30)) == []
        assert orch._v2_gate_rejects == 1

    def test_boundary_is_inclusive(self, monkeypatch):
        """Exactly at the allowance passes; a hair over is dropped."""
        at = _cand("LONG", 10_050.0, 10_200.0)       # overshoot exactly 0.5
        just_over = _cand("LONG", 10_051.0, 10_200.0)  # overshoot 0.51
        orch = _orch(monkeypatch, [at, just_over], max_zone_overshoot_atr=0.5)
        assert _emit(orch, df_entry=_flat_df(30)) == [at]
        assert orch._v2_gate_rejects == 1

    def test_gate_runs_when_only_overshoot_knob_is_set(self, monkeypatch):
        """ATR must be computed when EITHER gate is on.

        Pre-BT-25 the ATR call was guarded by `max_entry_dist_atr > 0.0`
        alone, so a config that set only the overshoot knob would compute no
        ATR and the new gate would never fire. Pins the structural change.
        """
        past = _cand("LONG", 10_200.0, 10_300.0)
        orch = _orch(monkeypatch, [past], max_zone_overshoot_atr=0.5)
        assert "max_entry_dist_atr" not in orch.config["smc_v2"]
        assert _emit(orch, df_entry=_flat_df(30)) == []

    def test_both_gates_active_each_drops_its_own(self, monkeypatch):
        """Far-ahead zone -> BT-23; overshot zone -> BT-25; reachable -> kept."""
        too_far = _cand("LONG", 7_900.0, 8_000.0)    # near edge 20.0 ATR ahead
        overshot = _cand("LONG", 10_200.0, 10_300.0)  # overshoot +2.0
        good = _cand("LONG", 9_600.0, 9_700.0)       # 3.0 ahead, overshoot -4.0
        orch = _orch(monkeypatch, [too_far, overshot, good],
                     max_entry_dist_atr=6.0, max_zone_overshoot_atr=0.5)
        assert _emit(orch, df_entry=_flat_df(30)) == [good]
        assert orch._v2_gate_rejects == 2

    def test_atr_uncomputable_fails_open(self, monkeypatch):
        """Short frame -> wilder_atr None -> overshot candidate survives."""
        past = _cand("LONG", 10_200.0, 10_300.0)
        orch = _orch(monkeypatch, [past], max_zone_overshoot_atr=0.5)
        assert _emit(orch, df_entry=_flat_df(5)) == [past]

    def test_no_df_entry_fails_open(self, monkeypatch):
        past = _cand("LONG", 10_200.0, 10_300.0)
        orch = _orch(monkeypatch, [past], max_zone_overshoot_atr=0.5)
        assert _emit(orch, df_entry=None) == [past]

    def test_no_current_price_fails_open(self, monkeypatch):
        past = _cand("LONG", 10_200.0, 10_300.0)
        orch = _orch(monkeypatch, [past], max_zone_overshoot_atr=0.5)
        assert _emit(orch, current_price=None, df_entry=_flat_df(30)) == [past]


class TestFlatFrameSanity:
    """Guards the fixture itself: if ATR != 100 every threshold above is wrong."""

    def test_flat_df_atr_is_100(self):
        from engine.smc_v2.atr import wilder_atr
        assert wilder_atr(_flat_df(30), period=14) == pytest.approx(100.0)

    def test_short_df_atr_is_none(self):
        from engine.smc_v2.atr import wilder_atr
        assert wilder_atr(_flat_df(5), period=14) is None
