"""
Market Regime Detector
━━━━━━━━━━━━━━━━━━━━━━

Bot sadece "trending" piyasada iyi çalışır. Diğer rejimlerde davranışı değişmeli.

Rejimler:
  TRENDING      — normal trade koşulları
  RANGING       — yatay, CHoCH sinyalleri güvenilmez → sadece reversal
  VOLATILE      — aşırı volatil, yeni pozisyon açma
  REVERSAL      — trend dönüşü şüphesi, mevcut pozisyonları gözden geçir
  LOW_LIQUIDITY — likidite düşük, order execution riskli

Algılama yöntemleri:
  - ADX (Average Directional Index) → trend gücü
  - Bollinger Band Width → volatilite / sıkışma
  - ATR ratio → anormal volatilite
  - Swing disorder → yatay piyasa işareti
"""

import numpy as np
import pandas as pd
from dataclasses import dataclass
from typing import Literal
from pathlib import Path
import logging
from engine.regimes.model import RegimeMLModel

log = logging.getLogger("efloud.regime")

Regime = Literal["TRENDING", "RANGING", "VOLATILE", "REVERSAL", "LOW_LIQUIDITY", "UNKNOWN"]


@dataclass
class RegimeAnalysis:
    regime: Regime
    confidence: int              # 0-100
    adx: float
    bb_width: float              # current / avg
    atr_ratio: float             # current / avg
    trend_alignment: bool        # HTF ve MTF aynı yönde mi
    notes: list
    allow_volatile_entries: bool = False

    @property
    def can_open_new_position(self) -> bool:
        """Yeni pozisyon açılabilir mi?"""
        allowed = ["TRENDING", "REVERSAL"]
        if self.allow_volatile_entries:
            allowed.append("VOLATILE")
        return self.regime in allowed

    @property
    def should_tighten_stops(self) -> bool:
        """Mevcut pozisyonlarda stop sıkılaştır?"""
        return self.regime in ("VOLATILE", "REVERSAL")


class RegimeDetector:

    def __init__(self,
                 adx_period: int = 14,
                 adx_trending_threshold: float = 25,
                 adx_ranging_threshold: float = 20,
                 atr_period: int = 14,
                 volatile_atr_multiplier: float = 2.5,
                 bb_period: int = 20,
                 bb_squeeze_threshold: float = 0.5,
                 allow_volatile_entries: bool = False,
                 ml_can_override_gate: bool = False):
        self.adx_period = adx_period
        self.adx_trend = adx_trending_threshold
        self.adx_range = adx_ranging_threshold
        self.atr_period = atr_period
        self.vol_mult = volatile_atr_multiplier
        self.bb_period = bb_period
        self.bb_squeeze = bb_squeeze_threshold
        self.allow_volatile_entries = allow_volatile_entries
        self.ml_can_override_gate = ml_can_override_gate
        self.weights_path = Path(__file__).resolve().parents[2] / "state" / "regime_model_weights.json"
        self.model = None
        self._load_ml_model()

    def _load_ml_model(self):
        """Auto-load weights for the ML Regime Detector if present on disk."""
        if self.weights_path.exists():
            try:
                self.model = RegimeMLModel(num_features=5, num_classes=5)
                self.model.load_weights(str(self.weights_path))
            except Exception as e:
                log.warning(f"Failed to load RegimeMLModel weights: {e}")
                self.model = None
        else:
            self.model = None


    def analyze(self, df: pd.DataFrame,
                 df_htf: pd.DataFrame = None) -> RegimeAnalysis:
        """Piyasa rejimini tespit et."""
        res = self._analyze_raw(df, df_htf)
        res.allow_volatile_entries = self.allow_volatile_entries
        return res

    def _analyze_raw(self, df: pd.DataFrame,
                  df_htf: pd.DataFrame = None) -> RegimeAnalysis:
        if len(df) < max(self.adx_period * 2, self.bb_period * 2):
            return RegimeAnalysis("UNKNOWN", 0, 0, 0, 0, False,
                                   ["Insufficient data"])

        adx_val = self._adx(df, self.adx_period)
        bb_w_ratio = self._bb_width_ratio(df, self.bb_period)
        atr_ratio = self._atr_ratio(df, self.atr_period)
        notes = []

        # HTF alignment check
        htf_aligned = True
        if df_htf is not None and len(df_htf) > 20:
            htf_trend_up = df_htf["close"].iloc[-1] > df_htf["close"].iloc[-20]
            mtf_trend_up = df["close"].iloc[-1] > df["close"].iloc[-20]
            htf_aligned = htf_trend_up == mtf_trend_up

        # ── Regime decision tree ──
        bb_expansion = bb_w_ratio > 1.4  # BB normalden %40 geniş
        if atr_ratio > self.vol_mult or (atr_ratio > 1.2 and bb_expansion):
            notes.append(f"ATR {atr_ratio:.1f}x + BBW {bb_w_ratio:.2f} — volatile")
            regime = "VOLATILE"
            confidence = 85
        elif adx_val < self.adx_range and bb_w_ratio < self.bb_squeeze:
            notes.append(f"ADX {adx_val:.1f} + BB squeezing ({bb_w_ratio:.2f}) — ranging")
            regime = "RANGING"
            confidence = 75
        elif not htf_aligned and self.adx_range <= adx_val <= self.adx_trend:
            notes.append(f"HTF/MTF diverging + ADX {adx_val:.1f} — possible reversal")
            regime = "REVERSAL"
            confidence = 70
        elif adx_val >= self.adx_trend:
            notes.append(f"ADX {adx_val:.1f} — trending")
            regime = "TRENDING"
            confidence = 80
        else:
            notes.append(f"ADX {adx_val:.1f} — weak trend")
            regime = "TRENDING"
            confidence = 50

        # ── ML Model Inference & Ensembling Layer ──
        if self.model is not None:
            try:
                # Extract features for current state
                feat_adx = adx_val / 100.0
                feat_bbw = min(bb_w_ratio, 5.0) / 2.0
                feat_atr = min(atr_ratio, 5.0) / 2.0
                
                # Returns standard deviation of past 20 elements
                ret = df["close"].iloc[-21:].pct_change().std()
                feat_ret_std = float(min(ret * 100.0, 5.0)) if not pd.isna(ret) else 0.0
                
                # Volume Z-score of past 20 elements
                vol_sub = df["volume"].iloc[-21:]
                feat_vol = 0.0
                vol_std = vol_sub.std()
                if vol_std > 0:
                    feat_vol = float((df["volume"].iloc[-1] - vol_sub.mean()) / vol_std)
                feat_vol = float(max(min(feat_vol, 3.0), -3.0))
                
                X_vec = np.array([[feat_adx, feat_bbw, feat_atr, feat_ret_std, feat_vol]])
                probs = self.model.predict_proba(X_vec)[0]
                ml_idx = np.argmax(probs)
                ml_regime = self.model.class_labels[ml_idx]
                ml_confidence = int(probs[ml_idx] * 100)
                
                notes.append(f"ML Model: {ml_regime} ({ml_confidence}%)")

                # C3: ML is ADVISORY by default — the note above is always logged,
                # but the deterministic regime (which feeds can_open_new_position,
                # the entry gate) is overwritten ONLY when ml_can_override_gate is
                # on. The model is auto-trained on the rule detector's own labels
                # (circular), so by default its output must not reach the gate.
                if ml_confidence >= 65 and self.ml_can_override_gate:
                    # fail-CLOSED: ML may only CONFIRM the deterministic regime or
                    # narrow the gate; it may never promote a gate-blocked regime to
                    # a gate-open one, nor clear should_tighten_stops.
                    det_open = regime in ("TRENDING", "REVERSAL", "VOLATILE")
                    ml_open = ml_regime in ("TRENDING", "REVERSAL", "VOLATILE")
                    det_tighten = regime in ("VOLATILE", "REVERSAL")
                    if (not ml_open or det_open) and not (det_tighten and ml_regime not in ("VOLATILE", "REVERSAL")):
                        regime = ml_regime
                        confidence = int((ml_confidence + confidence) / 2)
                    else:
                        notes.append("ML override suppressed (would widen gate / unset tighten)")
            except Exception as e:
                notes.append(f"ML Inference skipped: {e}")

        return RegimeAnalysis(regime, confidence, adx_val, bb_w_ratio, atr_ratio,
                              htf_aligned, notes)


    @staticmethod
    def _adx(df: pd.DataFrame, period: int = 14) -> float:
        """Wilder's ADX calculation."""
        h, l, c = df["high"].values, df["low"].values, df["close"].values
        n = len(df)
        if n < period + 1:
            return 0

        tr = np.zeros(n)
        plus_dm = np.zeros(n)
        minus_dm = np.zeros(n)

        for i in range(1, n):
            tr[i] = max(h[i] - l[i],
                         abs(h[i] - c[i - 1]),
                         abs(l[i] - c[i - 1]))
            up = h[i] - h[i - 1]
            dn = l[i - 1] - l[i]
            plus_dm[i] = up if (up > dn and up > 0) else 0
            minus_dm[i] = dn if (dn > up and dn > 0) else 0

        def smooth(arr):
            s = np.zeros(n)
            s[period] = np.sum(arr[1:period + 1])
            for i in range(period + 1, n):
                s[i] = s[i - 1] - (s[i - 1] / period) + arr[i]
            return s

        tr_s = smooth(tr)
        plus_s = smooth(plus_dm)
        minus_s = smooth(minus_dm)

        # Avoid div zero
        tr_s = np.where(tr_s == 0, 1e-10, tr_s)
        plus_di = 100 * plus_s / tr_s
        minus_di = 100 * minus_s / tr_s
        di_sum = plus_di + minus_di
        di_sum = np.where(di_sum == 0, 1e-10, di_sum)
        dx = 100 * np.abs(plus_di - minus_di) / di_sum

        adx = np.zeros(n)
        if n > 2 * period:
            adx[2 * period] = np.mean(dx[period + 1:2 * period + 1])
            for i in range(2 * period + 1, n):
                adx[i] = (adx[i - 1] * (period - 1) + dx[i]) / period

        return float(adx[-1]) if n > 2 * period else 0

    @staticmethod
    def _bb_width_ratio(df: pd.DataFrame, period: int = 20) -> float:
        """Current BB width / 50-period avg BB width."""
        if len(df) < period * 2:
            return 1.0
        close = df["close"]
        sma = close.rolling(period).mean()
        std = close.rolling(period).std()
        width = (std * 4) / sma  # 2-sigma band width relative to price
        current = float(width.iloc[-1])
        avg = float(width.iloc[-period * 2:].mean())
        return current / avg if avg > 0 else 1.0

    @staticmethod
    def _atr_ratio(df: pd.DataFrame, period: int = 14) -> float:
        """Current ATR / baseline ATR.
        
        Current = son 'period' bar'ın ATR'ı
        Baseline = daha önceki 3×period bar'ın ATR'ı (son period'ı dışla)
        Bu hesap "son zamanlar daha volatil mi?" sorusunu doğru cevaplar.
        """
        if len(df) < period * 5:
            return 1.0
        h, l, c = df["high"].values, df["low"].values, df["close"].values
        tr = np.maximum(h[1:] - l[1:],
                         np.maximum(abs(h[1:] - c[:-1]),
                                     abs(l[1:] - c[:-1])))
        # Son 'period' bar'daki ortalama TR
        current = float(np.mean(tr[-period:]))
        # Baseline: son period'u dışla, ondan önceki 3×period
        baseline_end = len(tr) - period
        baseline_start = max(0, baseline_end - period * 3)
        baseline = float(np.mean(tr[baseline_start:baseline_end]))
        return current / baseline if baseline > 0 else 1.0
