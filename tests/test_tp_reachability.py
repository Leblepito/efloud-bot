"""BT-19: TP2 reachability ceiling on the LIVE smc_v2 target path.

Context (2026-07-26). All three live bots run engine.smc_version: v2, so every
live TP comes from engine/smc_v2/tp_calc.calc_tp_targets. safe_orchestrator
calls it with htf_swings/htf_fvgs/eq_levels ALL EMPTY (documented under
"DELIBERATE SIMPLIFICATIONS for PR #S3c-2"), so in production it always takes
the projection path:

    TP1 = entry +/- min_rr  * risk
    TP2 = entry +/- fib_ext * risk

For V3 that is min_rr=1.0 and fibonacci.ext_tp2=2.618, i.e. a fixed 2.618
TP2/TP1 ratio that has nothing to do with market structure. Measured on the
30d/10sym scalp compare (report 2026-07-25_..._90143864): median TP1 2.232%,
median TP2 5.925%, ratio 2.654 -- and median MFE across the whole 4h max-hold
window 0.478%. TP2 was attached to 28/28 trades and filled on 0.

max_tp_gap_r puts a ceiling on the TP1->TP2 distance. Absent / 0.0 = OFF, and
these tests pin that the OFF path is unchanged.
"""
from types import SimpleNamespace

import pytest

from engine.smc_v2.tp_calc import calc_tp_targets

EMPTY_SWINGS = {"swing_highs": [], "swing_lows": []}


def _cfg(**kw):
    base = {"min_rr": 1.0, "fib_ext": 2.618}
    base.update(kw)
    return SimpleNamespace(**base)


def _call(direction, entry, sl, config):
    return calc_tp_targets(
        direction=direction,
        entry_price=entry,
        sl_price=sl,
        htf_swings=EMPTY_SWINGS,
        htf_fvgs=[],
        eq_levels=[],
        config=config,
    )


# ── The production geometry, pinned ──────────────────────────────────────────

def test_live_call_shape_is_pure_r_projection_long():
    """Empty structure inputs => TP1/TP2 are R multiples, not structure."""
    tp1, tp2, tags = _call("LONG", 100.0, 98.0, _cfg())
    assert tp1 == pytest.approx(102.0)          # entry + 1.0R, risk=2
    assert tp2 == pytest.approx(105.236)        # entry + 2.618R
    assert tags["tp1_source"] == "RR_PROJECTION"
    assert tags["tp2_source"] == "FIB_EXT"


def test_live_call_shape_is_pure_r_projection_short():
    tp1, tp2, tags = _call("SHORT", 100.0, 102.0, _cfg())
    assert tp1 == pytest.approx(98.0)
    assert tp2 == pytest.approx(94.764)
    assert tags["tp1_source"] == "RR_PROJECTION"
    assert tags["tp2_source"] == "FIB_EXT"


def test_tp2_over_tp1_ratio_is_fib_ext_over_min_rr():
    """The 2.654 ratio seen in the report is fib_ext/min_rr, nothing else."""
    entry, sl = 100.0, 98.0
    tp1, tp2, _ = _call("LONG", entry, sl, _cfg(min_rr=1.0, fib_ext=2.618))
    assert (tp2 - entry) / (tp1 - entry) == pytest.approx(2.618)


# ── OFF by default ───────────────────────────────────────────────────────────

def test_missing_attr_is_off():
    """A config without max_tp_gap_r must behave exactly as before BT-19."""
    _, tp2, tags = _call("LONG", 100.0, 98.0, _cfg())
    assert tp2 is not None
    assert tags["tp2_source"] == "FIB_EXT"


def test_zero_is_off():
    _, tp2, tags = _call("LONG", 100.0, 98.0, _cfg(max_tp_gap_r=0.0))
    assert tp2 is not None
    assert tags["tp2_source"] == "FIB_EXT"


def test_none_is_off():
    """`max_tp_gap_r: ` with an empty YAML value arrives as None, not 0.0."""
    _, tp2, tags = _call("LONG", 100.0, 98.0, _cfg(max_tp_gap_r=None))
    assert tp2 is not None
    assert tags["tp2_source"] == "FIB_EXT"


# ── ON: unreachable TP2 is dropped ───────────────────────────────────────────

def test_far_tp2_dropped_long():
    # gap = 2.618R - 1.0R = 1.618R; ceiling 1.0R -> drop
    tp1, tp2, tags = _call("LONG", 100.0, 98.0, _cfg(max_tp_gap_r=1.0))
    assert tp1 == pytest.approx(102.0)          # TP1 untouched
    assert tp2 is None                          # single-target mode
    assert tags["tp2_source"] == "DROPPED_UNREACHABLE"


def test_far_tp2_dropped_short():
    tp1, tp2, tags = _call("SHORT", 100.0, 102.0, _cfg(max_tp_gap_r=1.0))
    assert tp1 == pytest.approx(98.0)
    assert tp2 is None
    assert tags["tp2_source"] == "DROPPED_UNREACHABLE"


def test_generous_ceiling_keeps_tp2():
    _, tp2, tags = _call("LONG", 100.0, 98.0, _cfg(max_tp_gap_r=2.0))
    assert tp2 == pytest.approx(105.236)
    assert tags["tp2_source"] == "FIB_EXT"


def test_boundary_is_inclusive():
    """gap == ceiling is KEPT (strict > drops). Pins the comparison operator."""
    _, tp2, tags = _call("LONG", 100.0, 98.0, _cfg(max_tp_gap_r=1.618))
    assert tp2 is not None
    assert tags["tp2_source"] == "FIB_EXT"


@pytest.mark.parametrize("direction,sl", [("LONG", 98.0), ("SHORT", 102.0)])
def test_tp1_never_touched_by_the_ceiling(direction, sl):
    """The ceiling only ever removes TP2; TP1 must be bit-identical."""
    tp1_off, _, _ = _call(direction, 100.0, sl, _cfg())
    tp1_on, tp2_on, _ = _call(direction, 100.0, sl, _cfg(max_tp_gap_r=0.5))
    assert tp1_on == tp1_off
    assert tp2_on is None


def test_scalp_production_numbers_are_dropped_at_1r():
    """V3's real config: min_rr 1.0, ext_tp2 2.618, SL ~2.33% of price.

    TP1 lands 2.33% out, TP2 6.10% out. A 4h hold whose median MFE is 0.478%
    cannot reach either, but TP2 is the one that is unreachable by construction.
    """
    entry = 100.0
    sl = 97.668                      # 2.332% -- the measured median
    _, tp2_off, _ = _call("LONG", entry, sl, _cfg(min_rr=1.0, fib_ext=2.618))
    assert (tp2_off - entry) / entry == pytest.approx(0.0610, abs=1e-3)
    _, tp2_on, tags = _call(
        "LONG", entry, sl, _cfg(min_rr=1.0, fib_ext=2.618, max_tp_gap_r=1.0))
    assert tp2_on is None
    assert tags["tp2_source"] == "DROPPED_UNREACHABLE"
