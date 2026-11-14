"""T-20261114-01: FVG pullback entry shadow (smc_v2.fvg_entry: off|shadow; no orders)."""
from types import SimpleNamespace

import pytest

from engine.smc_v2 import luxalgo as lx
from engine.smc_v2.fvg_entry import (
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


def _f(line, name):
    return float(line.split(f"{name}=")[1].split()[0])


def _cost_r(cost_pct, entry=99.0, risk=4.5):
    return cost_pct / 100.0 * entry / risk


def test_net_r_sl_canonical_cost():
    # fill bar 1, SL bar 2 -> 0.25 h held; 2 x 0.04 commission + 0.10 SL slip + funding
    book = FvgShadowBook(timeout_bars=48)
    lines = _run(book, [_plan()], [_bar(1, 100, 100, 98.9, 99), _bar(2, 99, 99, 94, 95)])
    pct = 2 * 0.04 + 0.10 + 0.01 * 0.25 / 8
    assert _f(lines[-1], "cost_r") == pytest.approx(_cost_r(pct), abs=0.006)
    assert _f(lines[-1], "net_r") == pytest.approx(-1.0 - _cost_r(pct), abs=0.011)
    assert " v=A " in lines[-1]


def test_cost_tp_slip_lower_than_sl_slip():
    book = FvgShadowBook(timeout_bars=48)
    lines = _run(book, [_plan(tp2=None)], [_bar(1, 100, 100, 98.9, 99), _bar(2, 99, 108.5, 99.5, 108)])
    pct = 2 * 0.04 + 0.05 + 0.01 * 0.25 / 8
    assert _f(lines[-1], "cost_r") == pytest.approx(_cost_r(pct), abs=0.006)


def test_cost_tp1_then_be_weights_slippage():
    book = FvgShadowBook(timeout_bars=48)
    lines = _run(book, [_plan()], [_bar(1, 100, 100, 98.9, 99), _bar(2, 99, 108.5, 99.5, 108),
                                   _bar(3, 108, 108, 98.5, 99)])
    pct = 2 * 0.04 + 0.5 * 0.05 + 0.5 * 0.10 + 0.01 * 0.5 / 8
    assert _f(lines[-1], "cost_r") == pytest.approx(_cost_r(pct), abs=0.006)


def test_cost_funding_grows_with_hold_time():
    short = FvgShadowBook(timeout_bars=500, funding_pct_per_8h=1.0)
    long_ = FvgShadowBook(timeout_bars=500, funding_pct_per_8h=1.0)
    a = _run(short, [_plan()], [_bar(1, 100, 100, 98.9, 99), _bar(2, 99, 99, 94, 95)])
    bars = [_bar(1, 100, 100, 98.9, 99)] + [_bar(i, 99, 99.5, 98.95, 99) for i in range(2, 33)]
    b = _run(long_, [_plan()], bars + [_bar(33, 99, 99, 94, 95)])
    assert _f(b[-1], "cost_r") > _f(a[-1], "cost_r")


def test_cost_params_configurable():
    book = FvgShadowBook(timeout_bars=48, commission_pct=0.0, funding_pct_per_8h=0.0,
                         sl_slip_pct=0.0, exit_slip_pct=0.0)
    lines = _run(book, [_plan()], [_bar(1, 100, 100, 98.9, 99), _bar(2, 99, 99, 94, 95)])
    assert _f(lines[-1], "cost_r") == 0.0 and _f(lines[-1], "net_r") == -1.0


def test_slippage_defaults_match_backtest():
    from backtest.slippage import SlippageConfig
    cfg = SlippageConfig()
    book = FvgShadowBook()
    assert (book.sl_slip_pct, book.exit_slip_pct) == (cfg.sl_slip_pct, cfg.exit_slip_pct)


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


# -- SL variant B (operator SL: OB far wick -/+ 0.2 %) ------------------------

def _plans_b(lux, bias="BULL", min_rr=1.8):
    return build_plans("BTC/USDT", lux, bias, TS, atr=1.0, safety=SAFETY, min_rr=min_rr,
                       sl_mode="ob_pct")


def test_atr_mode_is_variant_a_and_default():
    [p] = _plans(_lux(extra_obs=[LONG_TP1_OB]))
    assert p.variant == "A" and p.key[-1] == "A"


def test_ob_pct_long_sl_math_no_atr_caps():
    [p] = _plans_b(_lux(extra_obs=[LONG_TP1_OB]))
    assert p.variant == "B" and p.key[-1] == "B"
    assert p.entry == 99.0
    assert p.sl == pytest.approx(95.0 * (1 - 0.002))      # OB bottom, not ATR-based
    # far OB that the ATR path rejects (SLTooFar) is still a valid B plan
    far_ob = _ob(lx.BULL, 90.0, 97.0)
    assert _plans(_lux(extra_obs=[LONG_TP1_OB], ob=far_ob)) == []
    [pb] = _plans_b(_lux(extra_obs=[_ob(lx.BEAR, 120.0, 121.0)], ob=far_ob))
    assert pb.sl == pytest.approx(90.0 * 0.998)


def test_ob_pct_short_sl_math():
    tp1_ob = _ob(lx.BULL, 91.0, 92.0)
    [p] = _plans_b(_lux("SHORT", extra_obs=[tp1_ob]), bias="BEAR")
    assert p.sl == pytest.approx(105.0 * 1.002)


def test_ob_pct_custom_pct_and_nonpositive_risk_skipped():
    [p] = build_plans("BTC/USDT", _lux(extra_obs=[LONG_TP1_OB]), "BULL", TS, atr=1.0,
                      safety=SAFETY, min_rr=1.8, sl_mode="ob_pct", sl_pct=0.01)
    assert p.sl == pytest.approx(95.0 * 0.99)
    # OB sitting above the entry -> stop above entry -> no valid long plan
    high_ob = _ob(lx.BULL, 99.5, 101.0)
    assert _plans_b(_lux(extra_obs=[LONG_TP1_OB], ob=high_ob)) == []


def test_ob_pct_tp1_uses_variant_risk():
    # B risk = 99 - 94.81 = 4.19 -> min 1.8R = 106.54; OB at 106.6 qualifies for B ...
    ob = _ob(lx.BEAR, 106.6, 107.5)
    [pb] = _plans_b(_lux(extra_obs=[ob]))
    assert pb.tp1 == 106.6
    # ... but not for A (risk 4.5 -> 107.1)
    assert _plans(_lux(extra_obs=[ob])) == []


def test_unknown_sl_mode_rejected():
    with pytest.raises(ValueError):
        build_plans("BTC/USDT", _lux(), "BULL", TS, atr=1.0, safety=SAFETY, min_rr=1.8,
                    sl_mode="nope")


def test_two_variants_two_independent_tracks():
    a = _plan()
    b = FvgPlan(**{**a.__dict__, "sl": 94.0, "variant": "B"})
    book = FvgShadowBook(timeout_bars=48)
    lines = _run(book, [a, b], [_bar(1, 100, 100, 98.9, 99)])
    assert _events(lines) == ["setup+", "setup+", "filled", "filled"]
    assert any(" v=A " in ln for ln in lines) and any(" v=B " in ln for ln in lines)
    # low 94.4: A stopped (94.5), B (94.0) still alive
    lines = _run(book, [], [_bar(2, 99, 99, 94.4, 95)])
    assert _events(lines) == ["exit"] and " v=A " in lines[0]
    lines = _run(book, [], [_bar(3, 95, 95, 93.9, 94)])
    assert _events(lines) == ["exit"] and " v=B " in lines[0]


def test_every_line_carries_variant_tag():
    book = FvgShadowBook(timeout_bars=2)
    lines = _run(book, [_plan()], [_bar(i, 100, 101, 99.5, 100) for i in (1, 2, 3)])
    assert lines and all(" v=A " in ln for ln in lines)
