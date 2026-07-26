"""W2/C2 (2026-07-18): stale engulfing → yalnız SON KAPANMIŞ bar onayı.

`confirm_entry` since_ts'ten bu yana TÜM barları tarayıp İLK engulfing'de
onay veriyordu — onay barı 30 bar önce kalmış olabilir (stale). Canlı emir
ŞİMDİKİ fiyattan açıldığı için bayat bir mum formasyonuyla giriş, onay
fiyatıyla gerçek giriş fiyatı arasında keyfi sapma yaratır.

Fix default-OFF: `last_bar_only=True` iken yalnız son kapanmış (prior,current)
çifti değerlendirilir — onay "şu an tazedir" semantiği. Toggle OFF → birebir
eski davranış (NET-cost gate Windows'ta koşulup operatör config'te
`smc_v2.confirm_last_bar_only: true` yapana kadar canlı değişmez).
"""
import pandas as pd

from engine.smc_v2.confirmation import confirm_entry
from engine.smc_v2.zones import ZoneSpec


def _df(rows, start="2026-01-01T00:00:00+00:00"):
    idx = pd.date_range(start, periods=len(rows), freq="15min", tz="UTC")
    return pd.DataFrame(rows, index=idx, columns=["open", "high", "low", "close"])


_ZONE = ZoneSpec(low=95.0, high=105.0, source="HTF_FVG")


def _ms(ts) -> int:
    return int(pd.Timestamp(ts).timestamp() * 1000)


def _stale_engulf_df():
    """Bar1→Bar2: bearish engulfing (zone içinde, ESKİ). Sonrası nötr barlar;
    son çift engulfing DEĞİL."""
    return _df([
        [100, 101, 99, 100.5],   # 0
        [100, 102, 99, 101.0],   # 1 bullish (prior)
        [101.5, 102, 97, 99.0],  # 2 bearish engulfs 1 → ESKİ onay (close 99, zonda)
        [99, 100, 98, 99.5],     # 3 nötr
        [99.5, 100, 98, 99.2],   # 4 nötr — SON bar, engulfing değil
    ])


def test_stale_engulfing_rejected_when_last_bar_only():
    """PARA TESTİ: eski onay ortada kaldı, son bar tazelemiyorsa
    last_bar_only=True onay VERMEMELİ (eski kod stale bar-2'de onaylıyordu)."""
    df = _stale_engulf_df()
    ok, px = confirm_entry(df_15m=df, zone=_ZONE, direction="SHORT",
                           since_ts=0, last_bar_only=True)
    assert ok is False
    assert px is None


def test_stale_engulfing_still_confirms_when_toggle_off():
    """Toggle OFF (default): eski davranış BİREBİR — geçmişteki ilk engulfing
    onaylanır. Regresyon-donduran test: gate koşulmadan canlı değişmez."""
    df = _stale_engulf_df()
    ok, px = confirm_entry(df_15m=df, zone=_ZONE, direction="SHORT", since_ts=0)
    assert ok is True
    assert px == 99.0  # bar-2'nin close'u (stale onay)


def test_fresh_last_bar_engulfing_confirms_in_both_modes():
    """Engulfing SON çiftte ise iki mod da onaylar (aynı fiyat)."""
    df = _df([
        [100, 101, 99, 100.5],
        [99, 100, 98, 99.5],
        [100, 102, 99, 101.0],   # bullish (prior)
        [101.5, 102, 97, 99.0],  # SON bar: bearish engulfing, zonda
    ])
    for flag in (False, True):
        ok, px = confirm_entry(df_15m=df, zone=_ZONE, direction="SHORT",
                               since_ts=0, last_bar_only=flag)
        assert ok is True, f"last_bar_only={flag}"
        assert px == 99.0


def test_last_bar_only_respects_since_ts():
    """Son bar tetikten ÖNCE kapanmışsa (ts <= since_ts) onay yok —
    C6 'yalnız tetik SONRASI' guard'ı bu modda da geçerli."""
    df = _df([
        [100, 102, 99, 101.0],
        [101.5, 102, 97, 99.0],  # son bar engulfing AMA since_ts sonrası değil
    ])
    since = _ms(df.index[-1])  # son barın ts'i dahil değil (strictly >)
    ok, px = confirm_entry(df_15m=df, zone=_ZONE, direction="SHORT",
                           since_ts=since, last_bar_only=True)
    assert ok is False
    assert px is None


def test_last_bar_only_long_direction():
    """LONG simetrisi: son çift bullish engulfing → onay."""
    df = _df([
        [100, 101, 99, 100.5],
        [101, 102, 99, 99.5],    # bearish (prior)
        [99.0, 103, 98, 102.0],  # SON bar: bullish engulfing
    ])
    zone = ZoneSpec(low=98.0, high=103.0, source="HTF_FVG")
    ok, px = confirm_entry(df_15m=df, zone=zone, direction="LONG",
                           since_ts=0, last_bar_only=True)
    assert ok is True
    assert px == 102.0
