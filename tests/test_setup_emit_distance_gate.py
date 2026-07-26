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


def _orch(monkeypatch, candidates, max_entry_dist_atr=None):
    """Bare orchestrator carrying only what the gate reads."""
    from engine.safe_orchestrator import SafeOrchestrator
    import engine.smc_v2.triggers as triggers

    smc_v2 = {}
    if max_entry_dist_atr is not None:
        smc_v2["max_entry_dist_atr"] = max_entry_dist_atr

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
        """Negative distance (price already at/past the zone) must survive."""
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


class TestFlatFrameSanity:
    """Guards the fixture itself: if ATR != 100 every threshold above is wrong."""

    def test_flat_df_atr_is_100(self):
        from engine.smc_v2.atr import wilder_atr
        assert wilder_atr(_flat_df(30), period=14) == pytest.approx(100.0)

    def test_short_df_atr_is_none(self):
        from engine.smc_v2.atr import wilder_atr
        assert wilder_atr(_flat_df(5), period=14) is None
