"""
Efloud Intent Engine — "İstekli Alım/Satım" Tespiti
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Efloud'un analizlerinde sıkça geçen kritik tanım:
  "İstekli alım göremiyorum" / "İstekli mumlarla geçerse devam eder"

Bu sübjektif tanımı somut metriklere çeviriyoruz:

1. Body Ratio       = |close - open| / (high - low)
   >0.7  = güçlü  (düz gövde, wick az) — istekli
   0.4-0.7 = orta (karma)
   <0.4  = zayıf  (uzun wick, kararsız)

2. Volume Spike     = current_volume / sma(volume, 20)
   >1.5x = güçlü hacim
   1.0-1.5x = normal
   <1.0x = zayıf (düşük ilgi)

3. Consecutive      = ardışık aynı yönlü mum sayısı
   3+ = güçlü trend
   2 = nötr
   0-1 = zayıf

4. Range Expansion  = body / atr(14)
   >1.5x = impulse  (genişleyen hareket)
   1.0-1.5x = normal
   <1.0x = contracting (daralma)

Toplam skor 0-100:
  70+  = "İstekli" (güçlü onay)
  40-70 = "Kararsız" (beklemede)
  <40  = "Zayıf" (erken çıkış veya giriş alma)
"""

import pandas as pd
import numpy as np
from dataclasses import dataclass
from typing import Literal
import logging

log = logging.getLogger("efloud.intent")

IntentLabel = Literal["STRONG_BULL", "STRONG_BEAR", "WEAK_BULL", "WEAK_BEAR", "NEUTRAL"]


@dataclass
class IntentScore:
    score: int              # 0-100
    label: IntentLabel
    direction: str          # "BULL" | "BEAR" | "NEUTRAL"
    body_ratio: float
    volume_ratio: float
    consecutive: int
    range_expansion: float
    reasons: list

    @property
    def is_strong(self) -> bool:
        return self.score >= 70

    @property
    def is_weak(self) -> bool:
        return self.score < 40


class IntentEngine:
    """Son mum(lar)daki 'istekli hareket' tespiti."""

    def __init__(self, atr_period: int = 14, vol_period: int = 20):
        self.atr_period = atr_period
        self.vol_period = vol_period

    def analyze(self, df: pd.DataFrame, lookback_bars: int = 3) -> IntentScore:
        """
        Son N mumun kolektif momentumunu ölç.

        Args:
            df: OHLCV DataFrame
            lookback_bars: Değerlendirilecek mum sayısı (default 3)
        """
        if len(df) < self.atr_period + 5:
            return IntentScore(0, "NEUTRAL", "NEUTRAL", 0, 0, 0, 0,
                               ["Insufficient data"])

        recent = df.iloc[-lookback_bars:]
        last = recent.iloc[-1]

        # 1. Body Ratio (son mum)
        rng = float(last["high"] - last["low"])
        body = abs(float(last["close"] - last["open"]))
        body_ratio = body / rng if rng > 0 else 0

        # Yön (son mum)
        is_bull = last["close"] > last["open"]
        direction = "BULL" if is_bull else "BEAR"

        # 2. Volume Spike
        if "volume" in df.columns and len(df) >= self.vol_period:
            avg_vol = df["volume"].iloc[-self.vol_period:-1].mean()
            last_vol = float(last["volume"])
            vol_ratio = last_vol / avg_vol if avg_vol > 0 else 1.0
        else:
            vol_ratio = 1.0

        # 3. Consecutive
        consec = 1
        for i in range(2, min(lookback_bars + 3, len(df)) + 1):
            b = df.iloc[-i]
            bull = b["close"] > b["open"]
            if (is_bull and bull) or (not is_bull and not bull):
                consec += 1
            else:
                break

        # 4. Range Expansion (body vs ATR)
        atr = self._atr(df, self.atr_period)
        range_exp = body / atr if atr > 0 else 0

        # ── Skor hesapla ──
        score = 0
        reasons = []

        # Body ratio
        if body_ratio > 0.7:
            score += 30; reasons.append(f"Strong body ({body_ratio:.2f})")
        elif body_ratio > 0.4:
            score += 15; reasons.append(f"Medium body ({body_ratio:.2f})")
        else:
            reasons.append(f"Weak body ({body_ratio:.2f}) — long wick")

        # Volume
        if vol_ratio > 1.5:
            score += 25; reasons.append(f"Volume spike ({vol_ratio:.1f}x avg)")
        elif vol_ratio > 1.0:
            score += 10; reasons.append(f"Normal volume ({vol_ratio:.1f}x)")
        else:
            reasons.append(f"Low volume ({vol_ratio:.1f}x) — weak interest")

        # Consecutive
        if consec >= 3:
            score += 25; reasons.append(f"{consec} consecutive same-direction candles")
        elif consec == 2:
            score += 10; reasons.append("2 consecutive")
        else:
            reasons.append("No streak")

        # Range expansion
        if range_exp > 1.5:
            score += 20; reasons.append(f"Impulse move ({range_exp:.1f}x ATR)")
        elif range_exp > 1.0:
            score += 10; reasons.append(f"Normal expansion ({range_exp:.1f}x ATR)")
        else:
            reasons.append(f"Compressed range ({range_exp:.1f}x ATR)")

        score = min(score, 100)

        # Label
        if score >= 70:
            label = "STRONG_BULL" if is_bull else "STRONG_BEAR"
        elif score >= 40:
            label = "WEAK_BULL" if is_bull else "WEAK_BEAR"
        else:
            label = "NEUTRAL"
            direction = "NEUTRAL"

        return IntentScore(
            score=score, label=label, direction=direction,
            body_ratio=round(body_ratio, 3),
            volume_ratio=round(vol_ratio, 2),
            consecutive=consec,
            range_expansion=round(range_exp, 2),
            reasons=reasons
        )

    def check_confirmation(self, df: pd.DataFrame, expected_direction: str,
                           min_score: int = 50) -> bool:
        """
        Belirli bir yönde confirmation geldi mi?
        Efloud: "Confirmation görmeden pozisyon alınmaz."
        """
        intent = self.analyze(df)
        if intent.direction != expected_direction:
            return False
        return intent.score >= min_score

    def check_weakness(self, df: pd.DataFrame, current_direction: str) -> bool:
        """
        Mevcut yönde zayıflama var mı?
        Efloud: "İstekli alım göremiyorum → kısmi kapat."
        """
        intent = self.analyze(df, lookback_bars=3)

        # Ters yönde güçlü intent → tehlike
        if intent.direction != current_direction and intent.score >= 50:
            return True

        # Aynı yönde ama zayıf → momentum kaybı
        if intent.direction == current_direction and intent.score < 40:
            return True

        return False

    @staticmethod
    def _atr(df: pd.DataFrame, period: int = 14) -> float:
        """Average True Range."""
        if len(df) < period + 1:
            return 0
        high = df["high"].values[-period - 1:]
        low = df["low"].values[-period - 1:]
        close = df["close"].values[-period - 1:]
        tr = np.maximum(high[1:] - low[1:],
                        np.maximum(abs(high[1:] - close[:-1]),
                                   abs(low[1:] - close[:-1])))
        return float(np.mean(tr))
