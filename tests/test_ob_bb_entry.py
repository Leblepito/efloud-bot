"""OB/BB entry path (2026-09-30): CHoCH kırılımını yapan OrderBlock/BreakerBlock
hedef zone olur; SL çapası bloğun bir önceki mumu (origin) olur.

WHY THIS TEST EXISTS
--------------------
Operatör: "CHoCH kırılımı olur olmaz aynı anda işleme girmek yerine, o CHoCH
kırılımını yapan OB/BB hangisi ise oradan işleme girilsin; SL, gerekli mum
öncesine (origin mum) dayansın." Bu testler üç davranışı sabitler:
  1. _find_causing_ob: BULL CHoCH -> kırılımdan önceki en son BEAR OB;
     BEAR CHoCH -> en son BULL OB. Kırılım fiyatının yanlış tarafındaki
     bloklar elenir.
  2. generate_setup_candidates OB/BB ile: target_zone.source "OB"/"BB",
     htf_swing_anchor = origin mumun low'u (LONG) / high'ı (SHORT).
  3. OB yoksa legacy FVG/OTE yolu korunur (source HTF_FVG/OTE).
"""
import pandas as pd

from engine.smc import StructBreak, OrderBlock
from engine.smc_v2.triggers import _find_causing_ob, generate_setup_candidates
from engine.smc_v2.zones import ZoneSpec


def _ob(idx, direction, bot, top, breaker=False):
    return OrderBlock(
        top=top, bot=bot, eq=(top + bot) / 2, idx=idx, ts="",
        direction=direction, count=1, near_swing=False,
        mitigated=breaker, became_breaker=breaker,
    )


def _brk(kind, direction, idx, price):
    return StructBreak(kind, direction, price, idx, "", price)


def _entry_df(n=100):
    """Flat OHLC frame; origin mum low/high okunabilir olsun."""
    return pd.DataFrame({
        "open": [100.0] * n,
        "high": [101.0] * n,
        "low": [99.0] * n,
        "close": [100.0] * n,
    })


class TestFindCausingOb:

    def test_bull_choch_finds_last_bear_ob(self):
        obs = [
            _ob(10, "BEAR", 90.0, 92.0),
            _ob(20, "BEAR", 88.0, 90.0),   # en son -> kazanan
            _ob(15, "BULL", 80.0, 85.0),   # yanlış yön
        ]
        brk = _brk("CHoCH", "BULL", 30, 95.0)
        assert _find_causing_ob(obs, brk).idx == 20

    def test_bear_choch_finds_last_bull_ob(self):
        obs = [
            _ob(10, "BULL", 105.0, 107.0),
            _ob(22, "BULL", 108.0, 110.0),  # en son -> kazanan
            _ob(18, "BEAR", 100.0, 103.0),  # yanlış yön
        ]
        brk = _brk("CHoCH", "BEAR", 30, 104.0)
        assert _find_causing_ob(obs, brk).idx == 22

    def test_ob_after_break_is_excluded(self):
        """Kırılımdan SONRA oluşan blok (lookahead) asla seçilmez."""
        obs = [_ob(35, "BEAR", 90.0, 92.0)]  # idx > brk.idx
        brk = _brk("CHoCH", "BULL", 30, 95.0)
        assert _find_causing_ob(obs, brk) is None

    def test_ob_on_wrong_side_of_break_is_excluded(self):
        """BULL kırılımda bloğun top'u kırılım fiyatının ÜSTÜNDE olamaz."""
        obs = [_ob(20, "BEAR", 96.0, 98.0)]  # top > brk.price
        brk = _brk("CHoCH", "BULL", 30, 95.0)
        assert _find_causing_ob(obs, brk) is None

    def test_empty_blocks_returns_none(self):
        brk = _brk("CHoCH", "BULL", 30, 95.0)
        assert _find_causing_ob([], brk) is None


class TestGenerateCandidatesObBb:

    def _emit(self, obs, brks, bias="BULL"):
        return generate_setup_candidates(
            symbol="BTC/USDT",
            htf_bias=bias,
            ltf_structure_breaks=brks,
            htf_swings={"swing_highs": [], "swing_lows": []},
            htf_bars=[],
            htf_fvgs=[],
            ote_band=(0.0, 0.0),
            ltf_trigger_idx_min=0,
            ltf_order_blocks=obs,
            df_entry=_entry_df(),
        )

    def test_long_uses_bb_zone_and_origin_low_anchor(self):
        obs = [_ob(20, "BEAR", 90.0, 92.0, breaker=True)]
        brks = [_brk("CHoCH", "BULL", 30, 95.0)]
        cands = self._emit(obs, brks)
        assert len(cands) == 1
        c = cands[0]
        assert c.direction == "LONG"
        assert c.target_zone.source == "BB"          # mitigated -> Breaker
        assert c.target_zone.low == 90.0
        assert c.target_zone.high == 92.0
        # origin mum = idx 19 -> low 99.0 (flat frame)
        assert c.htf_swing_anchor == 99.0
        assert any("BB retest" in r for r in c.reasons)

    def test_short_uses_ob_zone_and_origin_high_anchor(self):
        obs = [_ob(20, "BULL", 108.0, 110.0)]        # breaker=False -> OB
        brks = [_brk("CHoCH", "BEAR", 30, 104.0)]
        cands = self._emit(obs, brks, bias="BEAR")
        assert len(cands) == 1
        c = cands[0]
        assert c.direction == "SHORT"
        assert c.target_zone.source == "OB"
        assert c.htf_swing_anchor == 101.0           # origin high (flat frame)

    def test_no_ob_falls_back_to_legacy_path(self):
        """OB yoksa FVG/OTE yolu korunur (source HTF_FVG/OTE)."""
        brks = [_brk("CHoCH", "BULL", 30, 95.0)]
        cands = self._emit([], brks)
        assert len(cands) == 0  # ote_band=(0,0) degenerate -> skip (legacy davranış)

    def test_ob_bb_with_fvg_fallback(self):
        """OB yok ama HTF FVG varsa legacy FVG yolu çalışır."""
        from engine.smc import FVG, Swing
        fvg = FVG(92.0, 94.0, 25, "", "BEAR")  # LONG pullback: BEAR gap below trigger
        swing = Swing(93.0, 10, "", True)  # anchor için geçmiş bir swing
        cands = generate_setup_candidates(
            symbol="BTC/USDT",
            htf_bias="BULL",
            ltf_structure_breaks=[_brk("CHoCH", "BULL", 30, 95.0)],
            htf_swings={"swing_highs": [], "swing_lows": [swing]},
            htf_bars=[],
            htf_fvgs=[fvg],
            ote_band=(0.0, 0.0),
            ltf_trigger_idx_min=0,
            ltf_order_blocks=[],
            df_entry=_entry_df(),
        )
        assert len(cands) == 1
        assert cands[0].target_zone.source == "HTF_FVG"
