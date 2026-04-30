"""
Efloud Level Engine — Seviye Hiyerarşisi
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Efloud'un kullandığı tüm seviyeleri tespit eder:

• MO (Monthly Open)    — aylık açılış
• WO (Weekly Open)     — haftalık açılış
• DO (Daily Open)      — günlük açılış
• PWO/PMO/PDO          — önceki dönem açılışları
• Monday High/Low      — pazartesinin en yüksek/düşük (forex)
• Range H/L/EQ          — range sınırları + ortası
• RH / RL              — mutlak range high/low
• Stacked zones        — yığılmış seviye bölgeleri

"Yığılmış" tanımı: 3+ seviye, aralarında ≤0.5% fark
→ Bu bölgeler Efloud'un "güçlü S/R" dediği yerler.
"""

import pandas as pd
from dataclasses import dataclass, field
from typing import List, Optional
import logging

log = logging.getLogger("efloud.levels")


@dataclass
class Level:
    name: str           # "MO", "WO", "PWO", "Range High", vs.
    price: float
    kind: str           # "open", "swing", "equal", "range", "equilibrium"
    strength: int = 1   # 1 = basit, 3+ = stacked zone
    timestamp: str = ""
    note: str = ""

    def __repr__(self):
        marker = "★" * min(self.strength, 3)
        return f"{self.name:>12} @ {self.price:>10.2f} {marker}"


@dataclass
class StackedZone:
    """3+ seviyenin birbirine yakın olduğu bölge."""
    center: float
    top: float
    bottom: float
    levels: List[Level]
    strength: int

    @property
    def label(self) -> str:
        names = "/".join(sorted(set(l.name for l in self.levels)))
        return names


class LevelEngine:
    """Tüm Efloud seviyelerini tek sefer hesaplar."""

    def __init__(self, stacking_threshold_pct: float = 0.5):
        self.stack_thr = stacking_threshold_pct / 100.0

    def extract_all(
        self,
        df_daily: pd.DataFrame,
        df_weekly: Optional[pd.DataFrame] = None,
        df_monthly: Optional[pd.DataFrame] = None,
        df_current: Optional[pd.DataFrame] = None,
        range_lookback: int = 50,
    ) -> List[Level]:
        """
        Tüm seviyeleri tek listede döndürür.

        Args:
            df_daily: günlük mumlar (DO, PDO için)
            df_weekly: haftalık (WO, PWO için) — None ise daily'den türet
            df_monthly: aylık (MO, PMO için) — None ise daily'den türet
            df_current: analiz yapılan TF (Range için)
        """
        levels = []

        # ── Günlük açılışlar ──
        if df_daily is not None and len(df_daily) > 2:
            last = df_daily.iloc[-1]
            prev = df_daily.iloc[-2]
            levels.append(Level("DO", float(last["open"]), "open", 1,
                                str(df_daily.index[-1]), "Today open"))
            levels.append(Level("PDO", float(prev["open"]), "open", 1,
                                str(df_daily.index[-2]), "Yesterday open"))

        # ── Haftalık açılışlar ──
        if df_weekly is None and df_daily is not None:
            df_weekly = self._resample(df_daily, "W-MON")
        if df_weekly is not None and len(df_weekly) > 2:
            levels.append(Level("WO", float(df_weekly.iloc[-1]["open"]), "open", 1,
                                str(df_weekly.index[-1]), "This week open"))
            levels.append(Level("PWO", float(df_weekly.iloc[-2]["open"]), "open", 1,
                                str(df_weekly.index[-2]), "Prev week open"))

            # Monday H/L (last completed week)
            if len(df_weekly) > 1:
                # Daily'den son pazartesi mumunu bul
                if df_daily is not None:
                    monday = self._find_last_monday(df_daily)
                    if monday is not None:
                        levels.append(Level("MondayH", float(monday["high"]), "swing", 1,
                                            str(monday.name), "Monday high"))
                        levels.append(Level("MondayL", float(monday["low"]), "swing", 1,
                                            str(monday.name), "Monday low"))

        # ── Aylık açılışlar ──
        if df_monthly is None and df_daily is not None:
            df_monthly = self._resample(df_daily, "ME")
        if df_monthly is not None and len(df_monthly) > 2:
            levels.append(Level("MO", float(df_monthly.iloc[-1]["open"]), "open", 1,
                                str(df_monthly.index[-1]), "This month open"))
            levels.append(Level("PMO", float(df_monthly.iloc[-2]["open"]), "open", 1,
                                str(df_monthly.index[-2]), "Prev month open"))

        # ── Range H/L/EQ (current TF) ──
        if df_current is not None and len(df_current) >= range_lookback:
            recent = df_current.iloc[-range_lookback:]
            rh = float(recent["high"].max())
            rl = float(recent["low"].min())
            eq = (rh + rl) / 2.0
            levels.append(Level("Range High", rh, "range", 1, "", f"Last {range_lookback} bars"))
            levels.append(Level("Range Low", rl, "range", 1, "", f"Last {range_lookback} bars"))
            levels.append(Level("Equilibrium", eq, "equilibrium", 1, "", "Range midpoint"))

        # ── Absolute RH/RL (daily last 200 bars) ──
        if df_daily is not None and len(df_daily) >= 30:
            lookback = min(200, len(df_daily))
            d = df_daily.iloc[-lookback:]
            levels.append(Level("RH", float(d["high"].max()), "range", 2, "",
                                f"Absolute high, last {lookback}D"))
            levels.append(Level("RL", float(d["low"].min()), "range", 2, "",
                                f"Absolute low, last {lookback}D"))

        return levels

    def detect_stacked_zones(self, levels: List[Level]) -> List[StackedZone]:
        """
        3+ seviye birbirine ≤%0.5 yakınsa → StackedZone.
        Efloud: "Birikmiş seviyeler güçlü S/R oluşturur."
        """
        if not levels:
            return []

        sorted_lvl = sorted(levels, key=lambda l: l.price)
        zones = []
        used = set()

        for i, anchor in enumerate(sorted_lvl):
            if i in used:
                continue
            cluster = [anchor]
            used_tmp = {i}

            for j in range(i + 1, len(sorted_lvl)):
                other = sorted_lvl[j]
                if abs(other.price - anchor.price) / anchor.price <= self.stack_thr:
                    cluster.append(other)
                    used_tmp.add(j)
                else:
                    break

            if len(cluster) >= 3:
                used |= used_tmp
                prices = [l.price for l in cluster]
                zones.append(StackedZone(
                    center=sum(prices) / len(prices),
                    top=max(prices),
                    bottom=min(prices),
                    levels=cluster,
                    strength=len(cluster),
                ))
                # Bu seviyeleri stacked olarak işaretle
                for l in cluster:
                    l.strength = len(cluster)

        return zones

    def get_nearest_levels(self, price: float, levels: List[Level],
                            n: int = 5) -> tuple:
        """Fiyatın altındaki ve üstündeki en yakın n seviye."""
        above = sorted([l for l in levels if l.price > price],
                       key=lambda l: l.price)[:n]
        below = sorted([l for l in levels if l.price < price],
                       key=lambda l: l.price, reverse=True)[:n]
        return above, below

    @staticmethod
    def _resample(df: pd.DataFrame, freq: str) -> pd.DataFrame:
        """Daily → weekly/monthly resample."""
        try:
            agg = df.resample(freq).agg({
                "open": "first", "high": "max",
                "low": "min", "close": "last",
                "volume": "sum" if "volume" in df.columns else "first",
            })
            return agg.dropna()
        except Exception as e:
            log.warning(f"Resample {freq} failed: {e}")
            return pd.DataFrame()

    @staticmethod
    def _find_last_monday(df_daily: pd.DataFrame):
        """Son tamamlanmış pazartesi mumunu bul (index.dayofweek == 0)."""
        try:
            mondays = df_daily[df_daily.index.dayofweek == 0]
            if len(mondays) > 0:
                return mondays.iloc[-1]
        except Exception:
            pass
        return None
