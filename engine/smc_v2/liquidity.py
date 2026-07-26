"""Likidite olayı sınıflandırması: SWEEP vs GRAB — MPA/2.

Kaynak: Efloud (@EfloudTheSurfer) kanal transkript analizi (2026-07-26).
Kaynak iki likidite alma biçimini AYIRIYOR ve farklı anlamlar yüklüyor:

  GRAB  — dar/hızlı bir fitille belirli bir seviyedeki likiditenin alınması;
          genelde TREND DEVAMI ile ilişkili.
  SWEEP — geniş/majör bir bölgedeki likiditenin toptan temizlenmesi;
          genelde TREND DEĞİŞİMİ ile ilişkili.

Bu ayrım mevcut motorda yoktu (engine/ altında yalnız agents/roles.py'de
kelime olarak geçiyordu). Ayrımın operasyonel değeri rejim eşleşmesinde:
counter-trend bir kurgu SWEEP ister, trend-devam kurgusu GRAB ister. Yanlış
tip gelirse confluence katkısı yarılanır.

Ayrım eşiği (ihlal fazlasının ATR'ye oranı) kaynakta SAYISAL olarak yok —
kaynak "geniş/dar" ayrımını niteliksel veriyor. `sweep_threshold_atr`
varsayılanı 0.5 bir MÜHENDİSLİK ÇIKARIMIDIR ve backtest'te taranmalıdır.

Saf fonksiyon — I/O yok, log yok.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Optional

import pandas as pd

KIND_SWEEP = "SWEEP"
KIND_GRAB = "GRAB"

REGIME_TREND = "TREND_FOLLOWING"
REGIME_COUNTER = "COUNTER_TREND"


@dataclass
class LiquidityEvent:
    """Bir referans seviyenin ihlali + geri kazanımı."""

    kind: str                 # "SWEEP" | "GRAB"
    side: str                 # "UP" (tepe likiditesi) | "DOWN" (dip likiditesi)
    ref_level: float
    extreme: float            # ihlalde görülen uç fiyat
    excess_atr: float         # (uç - ref) / ATR — ayrımın ölçüsü
    idx: int                  # ihlal barının ordinali
    reclaim_idx: int          # seviyenin geri kazanıldığı barın ordinali


def detect_liquidity_event(
    df: pd.DataFrame,
    ref_level: float,
    side: str,
    atr: float,
    sweep_threshold_atr: float = 0.5,
    min_excess_atr: float = 0.10,
    reclaim_bars: int = 3,
) -> Optional[LiquidityEvent]:
    """`df` içindeki SON likidite olayını tespit et ve sınıflandır.

    Bir olay ancak seviye ihlal edilir VE `reclaim_bars` içinde gövde
    kapanışıyla geri kazanılırsa sayılır — kalıcı kırılım likidite olayı
    değil, yapı kırılımıdır (onu `engine.smc.structure()` raporlar).

    Args:
        df: [open, high, low, close] sütunlu DataFrame. Ordinal eksen = konum.
        ref_level: ihlal edilen likidite seviyesi (swing high/low, PDH/PDL,
            equal highs/lows kümesi, kurumsal open vb.).
        side: "UP" → tepe likiditesi (high > ref, short lehine);
              "DOWN" → dip likiditesi (low < ref, long lehine).
        atr: ilgili TF'in ATR değeri. <= 0 ise None döner (sınıflandırılamaz).
        sweep_threshold_atr: excess bu değeri AŞARSA SWEEP, aksi halde GRAB.
        min_excess_atr: bunun altındaki ihlaller gürültü sayılır, olay üretmez.
        reclaim_bars: geri kazanım için tanınan bar sayısı.

    Returns:
        En son geçerli LiquidityEvent, yoksa None.
    """
    if df is None or len(df) < 2 or atr is None or atr <= 0:
        return None
    if side not in ("UP", "DOWN"):
        return None

    highs = df["high"].values
    lows = df["low"].values
    closes = df["close"].values
    n = len(df)

    # En sondan geriye tara — "son olay" isteniyor.
    for i in range(n - 1, -1, -1):
        if side == "UP":
            if highs[i] <= ref_level:
                continue
            excess = (highs[i] - ref_level) / atr
        else:
            if lows[i] >= ref_level:
                continue
            excess = (ref_level - lows[i]) / atr

        if excess < min_excess_atr:
            continue

        # Geri kazanım: reclaim_bars içinde gövde kapanışı seviyenin doğru
        # tarafına dönmeli.
        reclaim_idx = None
        for j in range(i, min(i + reclaim_bars + 1, n)):
            if side == "UP" and closes[j] < ref_level:
                reclaim_idx = j
                break
            if side == "DOWN" and closes[j] > ref_level:
                reclaim_idx = j
                break
        if reclaim_idx is None:
            continue

        return LiquidityEvent(
            kind=KIND_SWEEP if excess > sweep_threshold_atr else KIND_GRAB,
            side=side,
            ref_level=float(ref_level),
            extreme=float(highs[i] if side == "UP" else lows[i]),
            excess_atr=float(excess),
            idx=int(i),
            reclaim_idx=int(reclaim_idx),
        )

    return None


def liquidity_score(
    event: Optional[LiquidityEvent],
    regime: str,
    htf_level: bool = False,
    base: int = 9,
    htf_bonus: int = 4,
    clean_reclaim_bonus: int = 2,
) -> int:
    """Confluence katkısı (0-15). Tasarım §2.3 C3 + güncelleme §B.2.

    Rejim–tip eşleşmesi:
      COUNTER_TREND + SWEEP → tam puan
      COUNTER_TREND + GRAB  → YARIM (counter-trend majör temizlik ister)
      TREND_FOLLOWING + GRAB → tam puan
      TREND_FOLLOWING + SWEEP → tam puan (ancak çağıran `regime_mult`'u
        0.85'e çekmeli — majör sweep trend değişimi habercisi olabilir;
        bu modül risk çarpanı uygulamaz, yalnız puan döner).

    Args:
        event: detect_liquidity_event çıktısı. None → 0.
        regime: "TREND_FOLLOWING" | "COUNTER_TREND".
        htf_level: ihlal edilen seviye HTF likiditesi mi (PDH/PDL/PWH/PWL).
        base / htf_bonus / clean_reclaim_bonus: puan bileşenleri.
    """
    if event is None:
        return 0

    score = base
    if htf_level:
        score += htf_bonus
    if event.reclaim_idx - event.idx <= 1 and event.excess_atr >= 0.5:
        score += clean_reclaim_bonus

    mismatch = regime == REGIME_COUNTER and event.kind == KIND_GRAB
    if mismatch:
        score = score // 2

    return int(min(score, base + htf_bonus + clean_reclaim_bonus))


def regime_risk_multiplier(event: Optional[LiquidityEvent], regime: str) -> float:
    """Trend-devam kurgusunda majör SWEEP geldiyse riski kıs (0.85).

    Gerekçe: kaynak SWEEP'i trend DEĞİŞİMİ ile ilişkilendiriyor. Trend yönünde
    işlem alırken majör bir sweep görmek, tezle çelişen bir emaredir — işlemi
    reddetmeye yetmez ama boyutu küçültmeyi hak eder.
    """
    if event is not None and regime == REGIME_TREND and event.kind == KIND_SWEEP:
        return 0.85
    return 1.0
