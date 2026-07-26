"""TP2 must never sit INSIDE TP1. Regression tripwire for a live incident.

WHAT HAPPENED. In state_1k/trade_journal.jsonl, 559 of 694 live orders
(80.5%) were sent to the exchange with TP2 CLOSER to entry than TP1. The
"TP1 partial + TP2 runner" design ran backwards: of 409 closed trades, 276
(67.5%) exited at TP2 and only 37 (9%) at TP1, so the runner filled first and
the partial almost never did. Daily inversion rate collapsed 100% -> 45.7% ->
35.5% -> 0% across 2026-05-29..06-01, bracketing commit eb7ffff
("fix(safety): critical ops hardening -- deviation TP2 ...", 2026-05-30).

So this is already fixed. These tests exist so it cannot come back silently:
the v2 calculator's ordering guard is three lines (`if fib_tp2 > tp1`) and is
exactly the kind of thing a refactor drops.
"""
from types import SimpleNamespace

import pytest

from engine.smc_v2.tp_calc import calc_tp_targets


def _cfg(min_rr=1.8, fib_ext=1.618, max_tp_gap_r=0.0):
    return SimpleNamespace(min_rr=min_rr, fib_ext=fib_ext, max_tp_gap_r=max_tp_gap_r)


def _call(direction, entry, sl, cfg):
    return calc_tp_targets(
        direction=direction, entry_price=entry, sl_price=sl,
        htf_swings={"swing_highs": [], "swing_lows": []},
        htf_fvgs=[], eq_levels=[], config=cfg,
    )


@pytest.mark.parametrize("direction,entry,sl", [("LONG", 100.0, 98.0), ("SHORT", 100.0, 102.0)])
@pytest.mark.parametrize("min_rr,fib_ext", [
    (1.8, 1.618),   # V1 live: min_rr > fib_ext -> the inversion-prone case
    (2.2, 1.618),   # V2 live: even wider gap
    (1.0, 2.618),   # V3: fib_ext > min_rr -> TP2 legitimately beyond TP1
    (1.618, 1.618), # exactly equal -> must NOT emit a coincident TP2
])
def test_tp2_is_never_inside_tp1(direction, entry, sl, min_rr, fib_ext):
    tp1, tp2, tags = _call(direction, entry, sl, _cfg(min_rr=min_rr, fib_ext=fib_ext))
    if tp2 is None:
        return                      # single-target mode is a valid answer
    if direction == "LONG":
        assert tp2 > tp1, f"LONG TP2 {tp2} inside TP1 {tp1} (tags={tags})"
    else:
        assert tp2 < tp1, f"SHORT TP2 {tp2} inside TP1 {tp1} (tags={tags})"


@pytest.mark.parametrize("direction,sl", [("LONG", 98.0), ("SHORT", 102.0)])
def test_live_config_yields_single_target_not_an_inverted_one(direction, sl):
    """The live V1 numbers (min_rr 1.8 > fib_ext 1.618) cannot produce a valid
    TP2 from the fib projection, because the projection lands short of TP1.
    The correct answer is tp2=None (single-target mode, which the lifecycle
    supports end-to-end) -- NOT a TP2 sitting between entry and TP1. Pinning
    this makes the operator-visible consequence explicit: on V1 and V2 there
    is currently no runner target at all."""
    tp1, tp2, tags = _call(direction, 100.0, sl, _cfg(min_rr=1.8, fib_ext=1.618))
    assert tp2 is None
    assert tags["tp2_source"] == "NONE"
    assert abs(tp1 - 100.0) == pytest.approx(1.8 * 2.0)


@pytest.mark.parametrize("direction,sl", [("LONG", 98.0), ("SHORT", 102.0)])
def test_v3_style_config_does_produce_a_runner(direction, sl):
    """Counterpart to the above: when fib_ext exceeds min_rr the guard must let
    TP2 through, otherwise 'never inverted' would be trivially satisfied by
    never emitting a TP2 at all."""
    tp1, tp2, tags = _call(direction, 100.0, sl, _cfg(min_rr=1.0, fib_ext=2.618))
    assert tp2 is not None
    assert tags["tp2_source"] == "FIB_EXT"
    assert abs(tp2 - 100.0) > abs(tp1 - 100.0)
