"""T-20261114-01: FVG pullback entry shadow (smc_v2.fvg_entry: off|shadow; no orders)."""
from types import SimpleNamespace

import pytest

from engine.smc_v2 import luxalgo as lx
from engine.smc_v2.fvg_entry import (
    ROUNDTRIP_COST_PCT,
    FvgPlan,
    FvgShadowBook,
    build_plans,
)

SAFETY = SimpleNamespace(sl_atr_buffer=0.5, min_sl_atr=2.0, max_sl_atr=5.0)
TF = 900_000
TS = [1_700_000_000_000 + i * TF for i in range(16)]


def _ob(bias, bot, top, idx=10, mitigated=-1, internal=True):
    return lx.LuxOrderBlock(bar_high=top, bar_low=bot, idx=idx, ts="", bias=bias,
                            internal=internal, created_idx=idx, mitigated_idx=mitigated)


def _lux(direction="LONG", extra_obs=(), fvgs=None, equals=(), sh=(), sl=(),
         brk_idx=14, fvg_idx=13, ob=None):
    if direction == "LONG":
        ob = ob or _ob(lx.BULL, 95.0, 97.0)
        brk = lx.LuxBreak("BOS", lx.BULL, 100.0, 9, brk_idx, "", True, ob)
        fvgs = [lx.LuxFVG(99.0, 98.0, fvg_idx, lx.BULL)] if fvgs is None else fvgs
    else:
        ob = ob or _ob(lx.BEAR, 103.0, 105.0)
        brk = lx.LuxBreak("CHoCH", lx.BEAR, 100.0, 9, brk_idx, "", True, ob)
        fvgs = [lx.LuxFVG(102.0, 101.0, fvg_idx, lx.BEAR)] if fvgs is None else fvgs
    return lx.LuxResult(
        swing_trend="UNDEF", internal_trend="UNDEF", breaks=[brk], swing_obs=[],
        internal_obs=[ob, *extra_obs], fvgs=fvgs, equals=list(equals), zones=None,
        strong_high=None, strong_low=None,
        swing_high_pivots=list(sh), swing_low_pivots=list(sl),
    )


def _plans(lux, bias="BULL", min_rr=1.8, wick=0.0):
    return build_plans("BTC/USDT", lux, bias, TS, atr=1.0, safety=SAFETY,
                       min_rr=min_rr, wick_buffer_r=wick)


LONG_TP1_OB = _ob(lx.BEAR, 108.0, 109.0)
LONG_EQH = lx.LuxEqual("EQH", 111.0, 111.0, 5, 8)


# ── build_plans ─────────────────────────────────────────────────────────

def test_long_plan_entry_sl_tp1_tp2():
    [p] = _plans(_lux(extra_obs=[LONG_TP1_OB], equals=[LONG_EQH]))
    assert p.direction == "LONG"
    assert p.entry == 99.0                       # FVG near (top) edge
    assert p.sl == pytest.approx(94.5)           # min(FVG low 98, OB low 95) - 0.5 ATR
    assert (p.tp1, p.tp1_src) == (108.0, "LUX_OB")
    assert (p.tp2, p.tp2_src) == (111.0, "LUX_EQH")
    assert p.known_ts == TS[14]


def test_bias_filter_and_undef():
    lux = _lux(extra_obs=[LONG_TP1_OB])
    assert _plans(lux, bias="BEAR") == []
    assert _plans(lux, bias="UNDEF") == []


def test_no_fvg_in_window_means_no_plan():
    assert _plans(_lux(extra_obs=[LONG_TP1_OB], fvgs=[])) == []
    # FVG before the OB candle is not the break's displacement
    old = [lx.LuxFVG(99.0, 98.0, 9, lx.BULL)]
    assert _plans(_lux(extra_obs=[LONG_TP1_OB], fvgs=old)) == []
    # opposite-direction FVG does not count
    bear = [lx.LuxFVG(99.0, 98.0, 13, lx.BEAR)]
    assert _plans(_lux(extra_obs=[LONG_TP1_OB], fvgs=bear)) == []


def test_mitigated_fvg_means_no_plan():
    f = [lx.LuxFVG(99.0, 98.0, 13, lx.BULL, mitigated_idx=14)]
    assert _plans(_lux(extra_obs=[LONG_TP1_OB], fvgs=f)) == []


def test_only_plans_known_on_newest_bars():
    # break 6 bars ago -> stale, never backfilled
    assert _plans(_lux(extra_obs=[LONG_TP1_OB], brk_idx=9, fvg_idx=8,
                       ob=_ob(lx.BULL, 95.0, 97.0, idx=5))) == []


def test_tp1_breaker_and_min_rr():
    near_ob = _ob(lx.BEAR, 104.0, 105.0)                    # < 1.8R (107.1)
    breaker = _ob(lx.BULL, 107.5, 108.5, mitigated=12)      # bullish OB broken -> bearish BB
    [p] = _plans(_lux(extra_obs=[near_ob, breaker, LONG_TP1_OB]))
    assert (p.tp1, p.tp1_src) == (107.5, "LUX_BB")


def test_no_tp1_means_no_plan():
    assert _plans(_lux(extra_obs=[_ob(lx.BEAR, 104.0, 105.0)])) == []


def test_tp2_liquidity_needs_half_r_beyond_tp1():
    close_piv = (6, 109.0)          # < 108 + 0.5*4.5
    [p] = _plans(_lux(extra_obs=[LONG_TP1_OB], sh=[close_piv]))
    assert p.tp2 is None and p.tp2_src == "NONE"
    [p] = _plans(_lux(extra_obs=[LONG_TP1_OB], sh=[close_piv, (7, 112.0)]))
    assert (p.tp2, p.tp2_src) == (112.0, "LUX_LIQ_HIGH")


def test_tp2_wick_buffer():
    [p] = _plans(_lux(extra_obs=[LONG_TP1_OB], equals=[LONG_EQH]), wick=0.1)
    assert p.tp2 == pytest.approx(111.0 - 0.1 * 4.5)


def test_short_plan_mirror():
    tp1_ob = _ob(lx.BULL, 91.0, 92.0)
    eql = lx.LuxEqual("EQL", 89.0, 89.0, 5, 8)
    [p] = _plans(_lux("SHORT", extra_obs=[tp1_ob], equals=[eql]), bias="BEAR")
    assert p.direction == "SHORT"
    assert p.entry == 101.0                      # FVG near (bottom) edge
    assert p.sl == pytest.approx(105.5)          # max(FVG top 102, OB top 105) + 0.5
    assert (p.tp1, p.tp1_src) == (92.0, "LUX_OB")
    assert (p.tp2, p.tp2_src) == (89.0, "LUX_EQL")


def test_sl_too_far_means_no_plan():
    far_ob = _ob(lx.BULL, 90.0, 97.0)            # 99 - 89.5 = 9.5 > 5 ATR
    assert _plans(_lux(extra_obs=[LONG_TP1_OB], ob=far_ob)) == []


# ── FvgShadowBook ───────────────────────────────────────────────────────

def _plan(tp2=111.0, known_ts=0):
    return FvgPlan(symbol="BTC/USDT", direction="LONG", break_ts=known_ts, fvg_ts=known_ts,
                   known_ts=known_ts, entry=99.0, sl=94.5, tp1=108.0, tp2=tp2,
                   tp1_src="LUX_OB", tp2_src="LUX_EQH" if tp2 else "NONE",
                   fvg=(98.0, 99.0), ob=(95.0, 97.0), bias="BULL", trigger="internal-BOS")


def _bar(i, o, h, l, c):
    return (i * TF, o, h, l, c)


def _run(book, plans, bars):
    return book.step("BTC/USDT", plans, bars)


def _events(lines):
    return [ln.split()[2] for ln in lines]


def test_setup_then_fill_then_sl():
    book = FvgShadowBook(timeout_bars=48)
    lines = _run(book, [_plan()], [_bar(0, 100, 101, 99.5, 100)])
    assert _events(lines) == ["setup+"]
    lines = _run(book, [], [_bar(0, 100, 101, 99.5, 100), _bar(1, 100, 100, 98.5, 99),
                            _bar(2, 99, 99, 94, 95)])
    assert _events(lines) == ["filled", "exit"]
    assert "reason=SL" in lines[-1] and "gross_r=-1.00" in lines[-1]


def test_fill_bar_counts_sl_only():
    book = FvgShadowBook(timeout_bars=48)
    lines = _run(book, [_plan()], [_bar(1, 100, 109, 94, 100)])
    assert _events(lines) == ["setup+", "filled", "exit"]
    assert "reason=SL" in lines[-1]


def test_sl_first_when_sl_and_tp_same_bar():
    book = FvgShadowBook(timeout_bars=48)
    lines = _run(book, [_plan()], [_bar(1, 100, 100, 98.9, 99), _bar(2, 99, 112, 94, 100)])
    assert "reason=SL" in lines[-1]


def test_tp1_then_be():
    book = FvgShadowBook(timeout_bars=48)
    lines = _run(book, [_plan()], [_bar(1, 100, 100, 98.9, 99), _bar(2, 99, 108.5, 99.5, 108),
                                   _bar(3, 108, 108, 98.5, 99)])
    assert "reason=BE" in lines[-1]
    r1 = (108.0 - 99.0) / 4.5
    assert f"gross_r={0.5 * r1:+.2f}" in lines[-1]


def test_tp1_then_tp2():
    book = FvgShadowBook(timeout_bars=48)
    lines = _run(book, [_plan()], [_bar(1, 100, 100, 98.9, 99), _bar(2, 99, 108.5, 99.5, 108),
                                   _bar(3, 108, 111.5, 107, 111)])
    assert "reason=TP2" in lines[-1]
    r = 0.5 * (108 - 99) / 4.5 + 0.5 * (111 - 99) / 4.5
    assert f"gross_r={r:+.2f}" in lines[-1]


def test_single_target_exits_full_at_tp1():
    book = FvgShadowBook(timeout_bars=48)
    lines = _run(book, [_plan(tp2=None)], [_bar(1, 100, 100, 98.9, 99), _bar(2, 99, 108.5, 99.5, 108)])
    assert "reason=TP1" in lines[-1] and "gross_r=+2.00" in lines[-1]


def test_net_r_subtracts_costs():
    book = FvgShadowBook(timeout_bars=48)
    lines = _run(book, [_plan()], [_bar(1, 100, 100, 98.9, 99), _bar(2, 99, 99, 94, 95)])
    net = float(lines[-1].split("net_r=")[1].split()[0])
    assert net == pytest.approx(-1.0 - ROUNDTRIP_COST_PCT * 99.0 / 4.5, abs=0.01)


def test_ran_away_cancel_and_expiry():
    book = FvgShadowBook(timeout_bars=48)
    lines = _run(book, [_plan()], [_bar(1, 100, 108.2, 99.5, 108)])
    assert _events(lines) == ["setup+", "cancelled"]
    book = FvgShadowBook(timeout_bars=2)
    lines = _run(book, [_plan()], [_bar(i, 100, 101, 99.5, 100) for i in (1, 2, 3)])
    assert _events(lines) == ["setup+", "expired"]


def test_dedup_and_one_open_plan_per_key():
    book = FvgShadowBook(timeout_bars=48)
    bars = [_bar(1, 100, 101, 99.5, 100)]
    assert _events(_run(book, [_plan()], bars)) == ["setup+"]
    assert _run(book, [_plan()], bars) == []                      # same plan again
    other = _plan(known_ts=TF)
    assert _run(book, [other], bars + [_bar(2, 100, 101, 99.5, 100)]) == []  # key busy


def test_bars_are_walked_once():
    book = FvgShadowBook(timeout_bars=48)
    bars = [_bar(1, 100, 100, 98.9, 99)]
    assert _events(_run(book, [_plan()], bars)) == ["setup+", "filled"]
    assert _run(book, [], bars) == []


def _short_plan():
    return FvgPlan(symbol="BTC/USDT", direction="SHORT", break_ts=0, fvg_ts=0, known_ts=0,
                   entry=101.0, sl=105.5, tp1=92.0, tp2=89.0, tp1_src="LUX_OB", tp2_src="LUX_EQL",
                   fvg=(101.0, 102.0), ob=(103.0, 105.0), bias="BEAR", trigger="internal-CHoCH")


def test_short_book_fill_tp1_tp2():
    book = FvgShadowBook(timeout_bars=48)
    lines = _run(book, [_short_plan()], [_bar(1, 100, 101.2, 100, 101), _bar(2, 100, 100.5, 91.5, 92),
                                         _bar(3, 92, 95, 88.5, 89)])
    assert _events(lines) == ["setup+", "filled", "exit"]
    r = 0.5 * (101 - 92) / 4.5 + 0.5 * (101 - 89) / 4.5
    assert "reason=TP2" in lines[-1] and f"gross_r={r:+.2f}" in lines[-1]


def test_short_book_sl_and_ran_away():
    book = FvgShadowBook(timeout_bars=48)
    lines = _run(book, [_short_plan()], [_bar(1, 100, 101.2, 100, 101), _bar(2, 101, 106, 100, 105)])
    assert "reason=SL" in lines[-1]
    book = FvgShadowBook(timeout_bars=48)
    lines = _run(book, [_short_plan()], [_bar(1, 100, 100.5, 91.8, 92)])
    assert _events(lines) == ["setup+", "cancelled"]


def test_tp1_bar_touching_be_exits_at_be_not_tp2():
    book = FvgShadowBook(timeout_bars=48)
    lines = _run(book, [_plan()], [_bar(1, 100, 100, 98.9, 99), _bar(2, 99, 111.5, 98.5, 110)])
    r1 = (108.0 - 99.0) / 4.5
    assert "reason=BE" in lines[-1] and f"gross_r={0.5 * r1:+.2f}" in lines[-1]


def test_plan_skipped_while_busy_is_not_retried():
    book = FvgShadowBook(timeout_bars=48)
    other = _plan(known_ts=TF)
    _run(book, [_plan()], [_bar(1, 100, 101, 99.5, 100)])
    assert _run(book, [other], [_bar(2, 100, 101, 99.5, 100)]) == []
    # first plan closes on bar 3; the skipped plan must not open afterwards
    _run(book, [], [_bar(3, 100, 108.5, 99.5, 108)])
    assert _run(book, [other], [_bar(4, 100, 101, 99.5, 100)]) == []
