"""v3.2 Entry-anchored SMC TP targeting — RANGE_EQ (0.50) + MTF liquidity.

Spec: docs/superpowers/specs/2026-07-11-tp-entry-anchored-targeting-and-bugfix-batch-design.md
Bölüm 2 (D1/D2): smc_tp_targeting açıkken TP blok havuzuna entry-TF range EQ
ve MTF likiditesi eklenir; bayrak kapalıyken davranış bit-bit aynı kalır.
"""

from types import SimpleNamespace
from unittest.mock import MagicMock

import pandas as pd

from engine.signals import generate_signals


def _flat_ohlc(n: int = 60, base: float = 101.5) -> pd.DataFrame:
    """Constant-range bars: high-low 0.4 → ATR14 = 0.4, buffer = 0.2."""
    return pd.DataFrame({
        "open": [base] * n,
        "high": [base + 0.2] * n,
        "low": [base - 0.2] * n,
        "close": [base] * n,
        "volume": [1000] * n,
    })


def _mock_engine(break_obj, e_range, htf_swing_highs=(), htf_swing_lows=(),
                 mtf_swings=((), ()), trend="BULL"):
    engine = MagicMock()
    engine.analyze.return_value = {
        "trend": trend,
        "active_fvgs": [],
        "active_obs": [],
        "swing_highs": list(htf_swing_highs),
        "swing_lows": list(htf_swing_lows),
        "eq_highs": [],
        "eq_lows": [],
        "range": e_range,
    }
    # 1st swings() call = MTF, 2nd = entry TF
    engine.swings.side_effect = [tuple(mtf_swings), ([], [])]
    # 1st structure() call = MTF breaks, 2nd = entry breaks
    engine.structure.side_effect = [[], [break_obj]]
    engine.order_blocks.return_value = []
    engine.sfps.return_value = []
    engine.range_info.return_value = e_range
    engine.ote.return_value = None
    engine.equal_levels.return_value = []
    return engine


def _long_break(price=102.0):
    return SimpleNamespace(direction="BULL", kind="CHoCH", idx=45,
                           ts="2026-07-11T00:00", price=price)


def _short_break(price=102.0):
    return SimpleNamespace(direction="BEAR", kind="CHoCH", idx=45,
                           ts="2026-07-11T00:00", price=price)


def _range(lo, hi, close):
    eq = (lo + hi) / 2
    return SimpleNamespace(
        lo=lo, hi=hi, eq=eq,
        premium=close > eq, discount=close < eq,
        dev_bull=False, dev_bear=False,
    )


class TestRangeEqTp1:
    """Range içi trade'de 0.50 (EQ) TP1 adayı olmalı — kullanıcı gereksinimi."""

    def test_long_discount_entry_targets_range_eq(self):
        # Range 100-110, EQ=105. Entry 102 (discount). SL → 101.1, risk 0.9.
        # EQ dist 3.0 (3.33R) ≥ min_rr_tp1 → TP1 = EQ. TP2 = range hi 110.
        e_range = _range(100.0, 110.0, close=101.5)
        eng = _mock_engine(_long_break(102.0), e_range,
                           htf_swing_highs=[SimpleNamespace(price=120.0, idx=5)])
        df = _flat_ohlc()

        sigs = generate_signals(
            eng, df, df, df, min_confluence=0, min_rr=1.5, recency_bars=40,
            smc_tp_targeting=True, min_rr_tp1=0.5, blended_rr_target=1.5,
        )

        assert len(sigs) == 1
        sig = sigs[0]
        assert sig.tp1 == 105.0, f"TP1 should be range EQ 105.0, got {sig.tp1}"
        assert sig.meta["tp1_source"] == "RANGE_EQ"
        assert sig.tp2 == 110.0, f"TP2 should be range hi, got {sig.tp2}"

    def test_short_premium_entry_targets_range_eq(self):
        # Range 90-110, EQ=100. Entry 102 (premium). TP1 = EQ 100, TP2 = lo 90.
        e_range = _range(90.0, 110.0, close=101.5)
        eng = _mock_engine(_short_break(102.0), e_range,
                           htf_swing_lows=[SimpleNamespace(price=80.0, idx=5)],
                           trend="BEAR")
        df = _flat_ohlc()

        sigs = generate_signals(
            eng, df, df, df, min_confluence=0, min_rr=1.5, recency_bars=40,
            smc_tp_targeting=True, min_rr_tp1=0.5, blended_rr_target=1.5,
        )

        assert len(sigs) == 1
        sig = sigs[0]
        assert sig.tp1 == 100.0, f"TP1 should be range EQ 100.0, got {sig.tp1}"
        assert sig.meta["tp1_source"] == "RANGE_EQ"
        assert sig.tp2 == 90.0

    def test_long_premium_entry_does_not_get_eq_below(self):
        # Entry EQ'nun ÜZERİNDE (premium) → LONG için EQ kâr yönünde değil,
        # blok havuzuna girmemeli; TP1 sonraki yapı (range hi) olmalı.
        e_range = _range(84.0, 104.0, close=101.5)  # EQ=94 < entry 102
        eng = _mock_engine(_long_break(102.0), e_range)
        df = _flat_ohlc()

        sigs = generate_signals(
            eng, df, df, df, min_confluence=0, min_rr=1.5, recency_bars=40,
            smc_tp_targeting=True, min_rr_tp1=0.5, blended_rr_target=1.5,
        )

        assert len(sigs) == 1
        assert sigs[0].tp1 == 104.0  # range hi — EQ (94) asla değil
        assert sigs[0].meta["tp1_source"] == "RANGE_HI"


class TestMtfLiquidityTp1:
    """MTF (orta TF) likiditesi blok havuzunda olmalı — 15m↔HTF köprüsü."""

    def test_mtf_swing_nearer_than_htf_wins_tp1(self):
        # HTF swing 120 çok uzak; MTF swing 106 yakın → TP1 = 106.
        # Range EQ entry'nin altında (LONG'a aday değil).
        e_range = _range(84.0, 110.0, close=101.5)  # EQ=97 < entry
        mtf_high = SimpleNamespace(price=106.0, idx=10)
        eng = _mock_engine(
            _long_break(102.0), e_range,
            htf_swing_highs=[SimpleNamespace(price=120.0, idx=5)],
            mtf_swings=([mtf_high], []),
        )
        df = _flat_ohlc()

        sigs = generate_signals(
            eng, df, df, df, min_confluence=0, min_rr=1.5, recency_bars=40,
            smc_tp_targeting=True, min_rr_tp1=0.5, blended_rr_target=1.5,
        )

        assert len(sigs) == 1
        sig = sigs[0]
        assert sig.tp1 == 106.0, f"TP1 should be MTF swing 106.0, got {sig.tp1}"
        assert sig.meta["tp1_source"] == "LIQ_MTF"
        assert sig.tp2 == 110.0  # sonraki blok: range hi


class TestLegacyPathUnchanged:
    """Bayrak kapalıyken (default) davranış bit-bit aynı — regresyon."""

    def test_flag_off_ignores_eq_and_mtf(self):
        # Aynı fixture'lar, smc_tp_targeting KAPALI → legacy: TP1 = HTF hedefi
        # (120), EQ/MTF blokları yok sayılır.
        e_range = _range(100.0, 110.0, close=101.5)
        mtf_high = SimpleNamespace(price=106.0, idx=10)
        eng = _mock_engine(
            _long_break(102.0), e_range,
            htf_swing_highs=[SimpleNamespace(price=120.0, idx=5)],
            mtf_swings=([mtf_high], []),
        )
        df = _flat_ohlc()

        sigs = generate_signals(
            eng, df, df, df, min_confluence=0, min_rr=1.5, recency_bars=40,
        )

        assert len(sigs) == 1
        assert sigs[0].tp1 == 120.0  # legacy: en yakın HTF hedefi ≥ min_rr
        assert sigs[0].meta.get("tp1_source") is None  # legacy meta boş
