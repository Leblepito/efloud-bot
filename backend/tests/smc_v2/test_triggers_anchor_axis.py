"""W2/C1 (2026-07-18): triggers → swing_anchor LTF↔HTF eksen düzeltmesi.

`generate_setup_candidates` SL çapası seçerken `select_htf_swing_anchor`'a
`trigger_idx=brk.idx` geçiyordu — brk.idx LTF (15m) DataFrame ordinali,
fonksiyonun beklediği eksen ise HTF (4h) ordinali (docstring: "ordinal of the
CHoCH trigger bar in the HTF DataFrame"). LTF ordinalleri aynı duvar-saati
için HTF'den kat kat büyük olduğundan `swing.idx < trigger_idx` filtresi
fiilen HERKESİ geçiriyordu — tetikten SONRA oluşan HTF swing'i de (lookahead;
"we don't anchor SL on future structure" sözleşmesi ihlali).

Fix default-OFF: `anchor_time_axis=True` iken brk.ts (ms) HTF bar ts_ms
eksenine haritalanır (kapsayan bar HARİÇ — intra-bar oluşum bilinemez,
muhafazakâr dışlama). Toggle OFF → bire bir eski davranış (NET-cost gate
Windows'ta koşulup operatör config'te açana kadar canlı değişmez).
"""
from dataclasses import dataclass

import pandas as pd

from engine.smc import Swing, StructBreak, FVG
from engine.smc_v2.triggers import HtfBar, generate_setup_candidates


def _ms(iso: str) -> int:
    return int(pd.Timestamp(iso).timestamp() * 1000)


# 4h HTF barları: 00:00 / 04:00 / 08:00 / 12:00 / 16:00 (ordinal 0..4).
# High'lar 110 — 120/130 swing'lerini hiçbir bar KIRMAZ (unbroken kalırlar).
def _htf_bars_with_ts():
    times = ["2026-01-01T00:00:00+00:00", "2026-01-01T04:00:00+00:00",
             "2026-01-01T08:00:00+00:00", "2026-01-01T12:00:00+00:00",
             "2026-01-01T16:00:00+00:00"]
    return [HtfBar(ordinal=i, high=110.0, low=90.0, ts_ms=_ms(t))
            for i, t in enumerate(times)]


# LTF CHoCH: 09:15 (HTF bar-2 08:00 penceresi içinde), LTF ordinal 100.
_TRIGGER_ISO = "2026-01-01T09:15:00+00:00"


def _brk(idx=100):
    return StructBreak(kind="CHoCH", direction="BEAR", price=100.0,
                       idx=idx, ts=_TRIGGER_ISO, broken_level=95.0)


def _swings():
    # idx=4 (16:00) tetikten SONRA oluşan swing — lookahead adayı (price 130).
    # idx=1 (04:00) tetikten ÖNCE — doğru çapa (price 120).
    return {
        "swing_highs": [
            Swing(price=130.0, idx=4, ts="t4", is_high=True),
            Swing(price=120.0, idx=1, ts="t1", is_high=True),
        ],
        "swing_lows": [],
    }


def _gen(htf_bars, **kw):
    return generate_setup_candidates(
        symbol="BTC/USDT", htf_bias="BEAR",
        ltf_structure_breaks=[_brk()],
        htf_swings=_swings(), htf_bars=htf_bars,
        htf_fvgs=[FVG(top=99.0, bot=97.0, idx=1, ts="t", direction="BULL")],
        ote_band=(96.0, 98.0), ltf_trigger_idx_min=0, **kw)


def test_axis_fix_excludes_future_htf_swing():
    """PARA TESTİ: toggle ON → tetik anı (09:15) HTF eksenine haritalanır
    (cutoff=ordinal 2); idx=4'teki GELECEK swing (130) elenir, çapa tetikten
    önceki idx=1 swing'i (120) olur. Eski eksen hatası 130'u seçiyordu."""
    cands = _gen(_htf_bars_with_ts(), anchor_time_axis=True)
    assert len(cands) == 1
    assert cands[0].htf_swing_anchor == 120.0, \
        "lookahead: tetik sonrası HTF swing SL çapası OLAMAZ"


def test_axis_default_off_preserves_legacy_behavior():
    """Toggle OFF (default): eski davranış BİREBİR — brk.idx (LTF ordinal=100)
    cutoff'u herkesi geçirir, en-yeni unbroken (gelecekteki 130) seçilir.
    Bu regresyon-donduran testtir: gate koşulmadan canlı davranış değişmez."""
    cands = _gen(_htf_bars_with_ts())
    assert len(cands) == 1
    assert cands[0].htf_swing_anchor == 130.0


def test_axis_fix_falls_back_to_legacy_without_ts():
    """ts_ms taşımayan bar fikstürleri (eski FakeBar'lar / eksik veri):
    haritalama yapılamaz → legacy brk.idx yolu (crash yok, eski davranış)."""
    @dataclass
    class BareBar:
        ordinal: int
        high: float
        low: float
    bars = [BareBar(ordinal=i, high=110.0, low=90.0) for i in range(5)]
    cands = _gen(bars, anchor_time_axis=True)
    assert len(cands) == 1
    assert cands[0].htf_swing_anchor == 130.0  # legacy sonuç


def test_axis_fix_skips_candidate_when_break_precedes_htf_window():
    """Kırılım tüm HTF penceresinden ÖNCE (ts haritası boş küme) → bilinen
    geçmiş yapı yok → cutoff=0 hiçbir swing'i geçirmez → aday atlanır
    (yanlış çapayla emir üretmekten iyidir)."""
    times = ["2026-02-01T00:00:00+00:00", "2026-02-01T04:00:00+00:00"]
    bars = [HtfBar(ordinal=i, high=110.0, low=90.0, ts_ms=_ms(t))
            for i, t in enumerate(times)]  # hepsi tetikten (2026-01-01) SONRA
    cands = _gen(bars, anchor_time_axis=True)
    assert cands == []
