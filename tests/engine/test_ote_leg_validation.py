"""H6 (2026-06-20 algorithm audit): OTE band built from mismatched swing legs.

``engine.smc.SMCEngine.ote`` used bare ``sh[-1]``/``sl[-1]`` with no check that
the two swings actually bracket ONE directional impulse leg. For a BULL OTE the
leg must be low-then-high (``sl.idx < sh.idx``); for BEAR it must be
high-then-low (``sh.idx < sl.idx``). Only the degenerate ``d <= 0`` case was
guarded, so two swings from unrelated moments (wrong chronological order for
the given trend) still produced a "valid" OTE band -- feeding both the +10
confluence bonus and the entry pullback refinement on a structure that isn't
really the impulse leg the trend claims it is.

Fix: reject (return None) when the swings don't bracket the claimed leg,
same as the existing d<=0 guard -- this only makes the gate MORE conservative
(never accepts a leg it previously would have rejected).
"""
from types import SimpleNamespace

from engine.smc import SMCEngine


def _swing(idx, price):
    return SimpleNamespace(idx=idx, price=price)


def test_bull_ote_rejects_mismatched_leg_order():
    """sl AFTER sh chronologically is NOT an up-leg (high-then-low = down move)."""
    eng = SMCEngine()
    sh = [_swing(idx=5, price=110.0)]
    sl = [_swing(idx=50, price=100.0)]  # low happens AFTER the high -- wrong order for BULL
    assert eng.ote(sh, sl, "BULL") is None


def test_bull_ote_accepts_valid_leg_order():
    """sl BEFORE sh chronologically IS a real up-leg -- must still work post-fix."""
    eng = SMCEngine()
    sh = [_swing(idx=50, price=110.0)]
    sl = [_swing(idx=5, price=100.0)]  # low, then high -- valid up-leg
    ote = eng.ote(sh, sl, "BULL")
    assert ote is not None
    assert ote.direction == "BULL"


def test_bear_ote_rejects_mismatched_leg_order():
    """sh AFTER sl chronologically is NOT a down-leg (low-then-high = up move)."""
    eng = SMCEngine()
    sh = [_swing(idx=50, price=110.0)]
    sl = [_swing(idx=5, price=100.0)]  # high happens AFTER the low -- wrong order for BEAR
    assert eng.ote(sh, sl, "BEAR") is None


def test_bear_ote_accepts_valid_leg_order():
    """sh BEFORE sl chronologically IS a real down-leg -- must still work post-fix."""
    eng = SMCEngine()
    sh = [_swing(idx=5, price=110.0)]
    sl = [_swing(idx=50, price=100.0)]  # high, then low -- valid down-leg
    ote = eng.ote(sh, sl, "BEAR")
    assert ote is not None
    assert ote.direction == "BEAR"


def test_ote_still_none_on_degenerate_price():
    """Pre-existing guard (d<=0) must keep working after the ordering check is added."""
    eng = SMCEngine()
    sh = [_swing(idx=50, price=100.0)]
    sl = [_swing(idx=5, price=110.0)]  # sl price above sh price -> d<=0
    result = eng.ote(sh, sl, "BULL")
    assert result is None
