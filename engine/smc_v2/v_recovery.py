"""V-type recovery confirmation — MPA/3.

Kaynak: Efloud (@EfloudTheSurfer) kanal transkript analizi (2026-07-26).
Kaynağın tanımı (AAVEUSDT ve LINKUSDT videolarında birebir):

  "Önemli bulduğumuz destek bölgelerine sert bir şekilde düşen fiyat
   tekrardan bu alandaki imbalance'ını ONARMADAN sert bir şekilde o alanı
   recover ediyorsa buna V type recovery deniyor."

Yani üç şart birlikte aranır:
  1. Bölgeye SERT bir bacakla giriş (displacement niteliğinde düşüş/yükseliş),
  2. Bölgenin/imbalance'ın TAM doldurulmaması (kısmi penetrasyon),
  3. SERT ve hızlı geri kazanım (down leg'in belirgin bir oranı geri alınır).

Bu, mevcut `confirm_entry` (engulfing) mekanizmasının YERİNE geçmez —
EK bir onay yoludur. İmza bilinçli olarak `confirm_entry` ile aynıdır
(`(bool, entry_price|None)`), böylece çağıran tarafta OR olarak
birleştirilebilir.

Güven sırası: kaynak V-recovery'yi tarafsız tanımlıyor, diğer confirmation
tipleriyle KIYASLAMIYOR. Tasarımda en düşük güven puanı (8/20) verilmesi bir
ÇIKARIMDIR; gerekçe yapısal: retest yoktur → giriş fiyatı görece kötü, stop
geniş, R:R düşer. Bu yüzden çağıran, V-recovery ile açılan pozisyonda
`conf_mult=0.5` uygulamalıdır.

Saf fonksiyon — I/O yok, log yok.
"""
from __future__ import annotations

from typing import Optional, Tuple

import pandas as pd

from engine.smc_v2.zones import ZoneSpec


def detect_v_recovery(
    df: pd.DataFrame,
    zone: ZoneSpec,
    direction: str,
    since_ts: int,
    atr: float,
    min_leg_atr: float = 1.0,
    max_leg_bars: int = 6,
    min_recovery_ratio: float = 0.5,
    max_recovery_bars: int = 6,
    max_fill_ratio: float = 0.9,
) -> Tuple[bool, Optional[float]]:
    """Bölgede V-type recovery onayı ara.

    Args:
        df: DatetimeIndex (UTC) + [open, high, low, close]. `confirm_entry`
            ile aynı LTF DataFrame beklenir.
        zone: ZoneSpec — pullback hedef bölgesi (HTF_FVG veya OTE).
        direction: "LONG" | "SHORT".
        since_ts: ms-epoch; yalnız bu zamandan SONRAKİ barlar değerlendirilir
            (tetikten önceki yapı onay sayılmaz — `confirm_entry` ile aynı
            sözleşme).
        atr: ilgili TF'in ATR'si. <= 0 → (False, None).
        min_leg_atr: bölgeye giriş bacağının ATR cinsinden minimum boyu
            ("sert düşüş" şartı).
        max_leg_bars: giriş bacağının en fazla kaç barda oluşabileceği.
        min_recovery_ratio: geri kazanımın, giriş bacağının en az hangi
            oranını geri alması gerektiği (0.5 = yarısı).
        max_recovery_bars: geri kazanım için tanınan bar sayısı ("hızlı"
            şartı).
        max_fill_ratio: bölgenin en fazla hangi oranda doldurulabileceği.
            0.9 → bölgenin %90'ından fazlası doldurulduysa artık "tam
            dolum"dur ve V-recovery SAYILMAZ.

    Returns:
        (True, entry_price) — entry_price geri kazanım barının kapanışı;
        (False, None) aksi halde.
    """
    if df is None or len(df) < 3 or atr is None or atr <= 0:
        return False, None
    if direction not in ("LONG", "SHORT"):
        return False, None

    zone_span = zone.high - zone.low
    if zone_span <= 0:
        return False, None

    timestamps_ms = [int(t.timestamp() * 1000) for t in df.index]
    eligible = [i for i, ts in enumerate(timestamps_ms) if ts > since_ts]
    if len(eligible) < 3:
        return False, None

    start = eligible[0]
    highs = df["high"].values
    lows = df["low"].values
    closes = df["close"].values
    n = len(df)

    # V tepesi/dibi: uygun pencerede ekstremum.
    if direction == "LONG":
        v_idx = min(eligible, key=lambda i: lows[i])
        extreme = lows[v_idx]
        penetration = (zone.high - extreme) / zone_span
    else:
        v_idx = max(eligible, key=lambda i: highs[i])
        extreme = highs[v_idx]
        penetration = (extreme - zone.low) / zone_span

    # (2) Bölgeye girmiş olmalı ama TAM doldurmamalı.
    if penetration <= 0 or penetration > max_fill_ratio:
        return False, None

    # (1) Giriş bacağı sert olmalı: max_leg_bars içindeki karşı ekstremumdan
    #     V noktasına olan mesafe >= min_leg_atr * ATR.
    leg_start = max(start, v_idx - max_leg_bars)
    if leg_start >= v_idx:
        return False, None
    if direction == "LONG":
        leg_origin = float(highs[leg_start:v_idx].max())
        leg_span = leg_origin - extreme
    else:
        leg_origin = float(lows[leg_start:v_idx].min())
        leg_span = extreme - leg_origin
    if leg_span < min_leg_atr * atr:
        return False, None

    # (3) Hızlı geri kazanım: max_recovery_bars içinde bacağın
    #     min_recovery_ratio kadarı geri alınmalı.
    rec_end = min(v_idx + max_recovery_bars, n - 1)
    for j in range(v_idx + 1, rec_end + 1):
        if direction == "LONG":
            recovered = highs[j] - extreme
            # Bölgenin altına gövde kapanışı → tez geçersiz.
            if closes[j] < zone.low:
                return False, None
        else:
            recovered = extreme - lows[j]
            if closes[j] > zone.high:
                return False, None

        if recovered >= min_recovery_ratio * leg_span:
            return True, float(closes[j])

    return False, None
