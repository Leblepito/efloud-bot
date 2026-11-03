"""Efloud price-action notları entegrasyonu (2026-09-30) — birim testler.

Kapsanan konseptler:
  1. Po3 gate (G1): MANIPULATION fazında giriş bloklanır, setup ölmez.
  2. SFP confluence: CHoCH bir SFP ile hizalanınca bonus eklenir.
  3. EQ retest zone: deviasyon sonrası EQ'ya dönüş (FVG'den sonra, OTE'den önce).
  4. RSI confluence: oversold/overbought yakınında OTE bonusu.
  5. Fib extension seçenekleri: TP1'in ötesine düşen en yakın extension.
"""
import pandas as pd

from engine.smc import StructBreak, OrderBlock, SFP, FVG, Swing
from engine.smc_v2.triggers import generate_setup_candidates
from engine.smc_v2.zones import build_pullback_zones, ZoneSpec
from engine.smc_v2.tp_calc import calc_tp_targets
from types import SimpleNamespace


def _ob(idx, direction, bot, top, breaker=False):
    return OrderBlock(
        top=top, bot=bot, eq=(top + bot) / 2, idx=idx, ts="",
        direction=direction, count=1, near_swing=False,
        mitigated=breaker, became_breaker=breaker,
    )


def _brk(kind, direction, idx, price):
    return StructBreak(kind, direction, price, idx, "", price)


def _sfp(idx, direction, price, sweep_level):
    return SFP(price=price, sweep_level=sweep_level, idx=idx, ts="", direction=direction)


def _entry_df(n=100):
    return pd.DataFrame({
        "open": [100.0] * n,
        "high": [101.0] * n,
        "low": [99.0] * n,
        "close": [100.0] * n,
    })


class TestSfpConfluence:

    def _emit(self, sfps, brks, bias="BULL"):
        return generate_setup_candidates(
            symbol="BTC/USDT",
            htf_bias=bias,
            ltf_structure_breaks=brks,
            htf_swings={"swing_highs": [], "swing_lows": [Swing(93.0, 10, "", True)]},
            htf_bars=[],
            htf_fvgs=[],
            ote_band=(90.0, 92.0),
            ltf_trigger_idx_min=0,
            ltf_order_blocks=[],
            df_entry=_entry_df(),
            ltf_sfps=sfps,
        )

    def test_aligned_sfp_adds_bonus(self):
        sfps = [_sfp(20, "BULL", 95.0, 93.0)]
        brks = [_brk("CHoCH", "BULL", 30, 96.0)]
        cands = self._emit(sfps, brks)
        assert len(cands) == 1
        assert cands[0].confluence_score == 10
        assert any("SFP aligned" in r for r in cands[0].reasons)

    def test_misaligned_sfp_no_bonus(self):
        sfps = [_sfp(20, "BEAR", 95.0, 97.0)]  # yanlış yön
        brks = [_brk("CHoCH", "BULL", 30, 96.0)]
        cands = self._emit(sfps, brks)
        assert len(cands) == 1
        assert cands[0].confluence_score == 0

    def test_sfp_after_break_no_bonus(self):
        sfps = [_sfp(35, "BULL", 95.0, 93.0)]  # kırılımdan SONRA (lookahead)
        brks = [_brk("CHoCH", "BULL", 30, 96.0)]
        cands = self._emit(sfps, brks)
        assert len(cands) == 1
        assert cands[0].confluence_score == 0


class TestEqRetestZone:

    def test_long_eq_below_trigger(self):
        zone = build_pullback_zones(
            htf_fvgs=[], ote_band=(80.0, 85.0), direction="LONG",
            trigger_price=95.0, eq_price=90.0,
        )
        assert zone.source == "EQ_RETEST"
        assert zone.low == 90.0 and zone.high == 90.0

    def test_short_eq_above_trigger(self):
        zone = build_pullback_zones(
            htf_fvgs=[], ote_band=(105.0, 110.0), direction="SHORT",
            trigger_price=95.0, eq_price=100.0,
        )
        assert zone.source == "EQ_RETEST"

    def test_fvg_beats_eq(self):
        fvg = FVG(91.0, 93.0, 25, "", "BEAR")
        zone = build_pullback_zones(
            htf_fvgs=[fvg], ote_band=(80.0, 85.0), direction="LONG",
            trigger_price=95.0, eq_price=90.0,
        )
        assert zone.source == "HTF_FVG"

    def test_eq_wrong_side_falls_to_ote(self):
        zone = build_pullback_zones(
            htf_fvgs=[], ote_band=(80.0, 85.0), direction="LONG",
            trigger_price=95.0, eq_price=100.0,  # EQ trigger'ın ÜSTÜNDE
        )
        assert zone.source == "OTE"


class TestRsiConfluence:

    def _emit(self, rsi, brks, bias="BULL"):
        return generate_setup_candidates(
            symbol="BTC/USDT",
            htf_bias=bias,
            ltf_structure_breaks=brks,
            htf_swings={"swing_highs": [], "swing_lows": [Swing(93.0, 10, "", True)]},
            htf_bars=[],
            htf_fvgs=[],
            ote_band=(90.0, 92.0),
            ltf_trigger_idx_min=0,
            ltf_order_blocks=[],
            df_entry=_entry_df(),
            rsi_value=rsi,
        )

    def test_long_oversold_near_bonus(self):
        cands = self._emit(35.0, [_brk("CHoCH", "BULL", 30, 96.0)])
        assert cands[0].confluence_score == 5
        assert any("RSI" in r for r in cands[0].reasons)

    def test_long_neutral_no_bonus(self):
        cands = self._emit(50.0, [_brk("CHoCH", "BULL", 30, 96.0)])
        assert cands[0].confluence_score == 0

    def test_short_overbought_near_bonus(self):
        cands = generate_setup_candidates(
            symbol="BTC/USDT",
            htf_bias="BEAR",
            ltf_structure_breaks=[_brk("CHoCH", "BEAR", 30, 94.0)],
            htf_swings={"swing_highs": [Swing(97.0, 10, "", True)], "swing_lows": []},
            htf_bars=[],
            htf_fvgs=[],
            ote_band=(98.0, 100.0),
            ltf_trigger_idx_min=0,
            ltf_order_blocks=[],
            df_entry=_entry_df(),
            rsi_value=70.0,
        )
        assert cands[0].confluence_score == 5


class TestFibExtOptions:

    def _calc(self, fib_options, fib_ext=1.618, min_rr=1.0):
        return calc_tp_targets(
            direction="LONG",
            entry_price=100.0,
            sl_price=98.0,  # risk = 2.0
            htf_swings={"swing_highs": [], "swing_lows": []},
            htf_fvgs=[],
            eq_levels=[],
            config=SimpleNamespace(
                min_rr=min_rr, fib_ext=fib_ext,
                fib_ext_options=fib_options, max_tp_gap_r=0.0,
            ),
        )

    def test_nearest_extension_beyond_tp1(self):
        # TP1 = 100 + 1.0*2 = 102.0. 1.272*2=102.54 > 102 (seçilir)
        tp1, tp2, tags = self._calc([1.272, 1.618, 2.618, 4.23])
        assert tp2 == 100 + 1.272 * 2.0
        assert tags["tp2_source"] == "FIB_EXT_1.272"

    def test_no_options_legacy_behavior(self):
        tp1, tp2, tags = self._calc([])
        assert tp2 == 100 + 1.618 * 2.0
        assert tags["tp2_source"] == "FIB_EXT"
