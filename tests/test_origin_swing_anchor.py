import pandas as pd
from engine.smc import StructBreak
from engine.smc_v2.triggers import generate_setup_candidates, _impulse_leg


def _df():
    rows = [(100, 101, 99, 100)] * 5
    rows += [(100, 100.5, 95, 96), (96, 98, 95.5, 97), (97, 104, 97, 103), (103, 110, 102, 109)]
    return pd.DataFrame(rows, columns=["open", "high", "low", "close"])


def _brk(direction="BULL"):
    return StructBreak(idx=8, ts="2026-10-01T00:00:00", price=105.0, direction=direction, kind="CHOCH")


def test_impulse_leg_long():
    assert _impulse_leg(_df(), _brk(), "LONG", 12) == (95.0, 110.0)


def test_impulse_leg_disabled():
    assert _impulse_leg(_df(), _brk(), "LONG", 0) is None


def test_ote_fallback_uses_leg_origin_anchor():
    out = generate_setup_candidates(
        symbol="X", htf_bias="BULL", ltf_structure_breaks=[_brk()],
        htf_swings={"swing_highs": [], "swing_lows": []}, htf_bars=[], htf_fvgs=[],
        ote_band=(0.0, 0.0), ltf_trigger_idx_min=0, df_entry=_df(),
        origin_swing_lookback=12, ote_zone_entry=True)
    assert len(out) == 1
    c = out[0]
    assert c.htf_swing_anchor == 95.0
    assert c.target_zone.source == "OTE"
    assert abs(c.target_zone.low - (110 - 0.786 * 15)) < 1e-9
    assert abs(c.target_zone.high - (110 - 0.618 * 15)) < 1e-9
