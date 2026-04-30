"""
Efloud Scenario Planner — Koşullu Senaryo Üretici
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Efloud örneklerindeki karar ağacı:

  "2300 tutarsa long devam,
   kaybederse 2240 ve WO yeşil kutu arası confirmation ara,
   orada da olmazsa 2090 seviyeleri gündemimde."

Bu, 3 senaryolu bir plan:
  Ana plan     → koşul sağlanırsa beklenen hareket
  Bozulma     → ana plan bozulursa ne olur
  Plan B      → bozulma sonrası yeni fırsat

Her senaryo:
  - Tetik seviyesi (trigger)
  - Confirmation koşulu
  - Entry / SL / TP
  - Geçerlilik şartı (bar limit, zaman limit)
"""

import uuid
import logging
from dataclasses import dataclass, field
from typing import List, Optional, Literal
from datetime import datetime

log = logging.getLogger("efloud.scenario")

ScenarioState = Literal["PENDING", "ACTIVE", "TRIGGERED", "INVALIDATED", "EXPIRED"]


@dataclass
class Scenario:
    id: str
    kind: str                       # "main" | "invalidation" | "plan_b"
    name: str                       # İnsan-dostu açıklama
    direction: str                  # "LONG" | "SHORT"

    trigger_price: float            # Hangi seviyede aktifleşecek
    trigger_condition: str          # "price_reaches" | "price_breaks_below" | "price_breaks_above"

    entry_zone_top: float
    entry_zone_bottom: float
    sl: float
    tp1: float
    tp2: float

    invalidation_price: float       # Bu seviye geçilirse senaryo geçersiz
    expires_after_bars: int = 50    # Kaç bar sonra expire olacak

    confluence_required: int = 50   # Min confluence for entry
    confirmation_required: bool = True  # Intent confirmation gerekli mi

    state: ScenarioState = "PENDING"
    created_at: str = ""
    triggered_at: Optional[str] = None
    note: str = ""

    @property
    def rr_tp1(self) -> float:
        if self.entry_zone_bottom == self.sl:
            return 0
        entry = (self.entry_zone_top + self.entry_zone_bottom) / 2
        return abs(self.tp1 - entry) / abs(entry - self.sl)

    def to_dict(self) -> dict:
        return {
            "id": self.id, "kind": self.kind, "name": self.name,
            "direction": self.direction, "state": self.state,
            "trigger": self.trigger_price,
            "entry_zone": [self.entry_zone_bottom, self.entry_zone_top],
            "sl": self.sl, "tp1": self.tp1, "tp2": self.tp2,
            "rr_tp1": round(self.rr_tp1, 2),
            "note": self.note,
        }


class ScenarioPlanner:
    """
    Mevcut piyasa durumuna göre 3 senaryo üretir ve takip eder.
    """

    def __init__(self):
        self.scenarios: List[Scenario] = []

    def plan_three_scenarios(
        self,
        current_price: float,
        htf_bias: str,
        nearest_support: float,
        nearest_resistance: float,
        stacked_zones: list = None,
        range_low: float = 0,
        range_high: float = 0,
    ) -> List[Scenario]:
        """
        Mevcut duruma göre 3 senaryo kur.

        Efloud mantığı (ETH örneği):
          Ana plan:    "$2300 tutarsa long devam"
          Bozulma:    "$2300 kaybederse $2240'a düşer"
          Plan B:     "$2240 de tutmazsa $2090 hedef"
        """
        scenarios = []
        is_bull = htf_bias == "BULL"

        # ── Ana senaryo ──
        if is_bull:
            main = self._build_long_continuation(current_price, nearest_resistance)
        else:
            main = self._build_short_continuation(current_price, nearest_support)
        if main:
            scenarios.append(main)

        # ── Bozulma senaryosu ──
        if is_bull:
            invalid = self._build_invalidation_long(current_price, nearest_support,
                                                     stacked_zones)
        else:
            invalid = self._build_invalidation_short(current_price, nearest_resistance,
                                                      stacked_zones)
        if invalid:
            scenarios.append(invalid)

        # ── Plan B ──
        if is_bull:
            plan_b = self._build_plan_b_long(nearest_support, range_low,
                                              stacked_zones)
        else:
            plan_b = self._build_plan_b_short(nearest_resistance, range_high,
                                                stacked_zones)
        if plan_b:
            scenarios.append(plan_b)

        # Register
        for s in scenarios:
            s.created_at = datetime.utcnow().isoformat()
            self.scenarios.append(s)

        log.info(f"📋 {len(scenarios)} scenarios planned (bias={htf_bias})")
        for s in scenarios:
            log.info(f"   {s.kind.upper():<13} {s.name}")
        return scenarios

    def _build_long_continuation(self, price: float, resistance: float) -> Optional[Scenario]:
        """Ana plan — trend yönünde devam (longs).
        
        Mantık: fiyat şu an geri çekilmede olabilir, HTF bullish bias var.
        Giriş: mevcut fiyat etrafında ± %0.3 band.
        SL: en yakın swing low (risk = ATR tabanlı yaklaşık %1.5-2).
        TP1: en yakın güçlü direnç.
        TP2: TP1 uzaktaysa fib ext 1.618.
        """
        # Minimum mesafe kontrolü
        if resistance <= price * 1.005:
            # Direnç çok yakın — fib extension tabanlı hedef üret
            # Normal trade mesafesi kullan
            risk = price * 0.015  # %1.5 risk
            tp1 = price * 1.025   # %2.5 hedef  → R:R 1.67
            tp2 = price * 1.05    # %5 hedef → R:R 3.33
        else:
            risk = price * 0.015
            tp1 = resistance * 0.999
            tp2 = price + (tp1 - price) * 1.618

        sl = price - risk

        return Scenario(
            id=str(uuid.uuid4())[:8], kind="main",
            name=f"LONG continuation → {tp1:.2f}",
            direction="LONG",
            trigger_price=price, trigger_condition="price_reaches",
            entry_zone_top=price * 1.003, entry_zone_bottom=price * 0.997,
            sl=sl, tp1=tp1, tp2=tp2,
            invalidation_price=sl,
            state="ACTIVE",
            note=f"HTF bullish bias aktif, hedef {tp1:.2f}"
        )

    def _build_short_continuation(self, price: float, support: float) -> Optional[Scenario]:
        """Ana plan — trend yönünde devam (shorts)."""
        if support >= price * 0.995:
            risk = price * 0.015
            tp1 = price * 0.975
            tp2 = price * 0.95
        else:
            risk = price * 0.015
            tp1 = support * 1.001
            tp2 = price - (price - tp1) * 1.618

        sl = price + risk

        return Scenario(
            id=str(uuid.uuid4())[:8], kind="main",
            name=f"SHORT continuation → {tp1:.2f}",
            direction="SHORT",
            trigger_price=price, trigger_condition="price_reaches",
            entry_zone_top=price * 1.003, entry_zone_bottom=price * 0.997,
            sl=sl, tp1=tp1, tp2=tp2,
            invalidation_price=sl,
            state="ACTIVE",
            note=f"HTF bearish bias aktif, hedef {tp1:.2f}"
        )

    def _build_invalidation_long(self, price: float, support: float,
                                   stacked_zones: list) -> Optional[Scenario]:
        """
        Bozulma — ana plan bozulursa ne olur.
        Efloud: "2300 kaybederse 2240'a düşer, orada confirmation yakalarsam ekle."
        """
        if support == 0 or support >= price:
            return None

        # Destek bölgesi: stacked zone varsa onu kullan
        support_zone_top = support
        support_zone_bot = support * 0.995
        if stacked_zones:
            for z in stacked_zones:
                if z.bottom <= support <= z.top:
                    support_zone_top = z.top
                    support_zone_bot = z.bottom
                    break

        sl = support_zone_bot * 0.995
        risk = support_zone_top - sl
        tp1 = support_zone_top + risk * 2  # Orta hedef
        tp2 = support_zone_top + risk * 3.5

        return Scenario(
            id=str(uuid.uuid4())[:8], kind="invalidation",
            name=f"Re-entry at {support_zone_bot:.2f}-{support_zone_top:.2f}",
            direction="LONG",
            trigger_price=support_zone_top, trigger_condition="price_breaks_below",
            entry_zone_top=support_zone_top, entry_zone_bottom=support_zone_bot,
            sl=sl, tp1=tp1, tp2=tp2,
            invalidation_price=sl,
            state="PENDING",
            note=f"Ana plan bozulursa {support:.2f} bölgesinde confirmation arayıp re-entry"
        )

    def _build_invalidation_short(self, price: float, resistance: float,
                                    stacked_zones: list) -> Optional[Scenario]:
        if resistance == 0 or resistance <= price:
            return None

        res_zone_bot = resistance
        res_zone_top = resistance * 1.005
        if stacked_zones:
            for z in stacked_zones:
                if z.bottom <= resistance <= z.top:
                    res_zone_bot = z.bottom
                    res_zone_top = z.top
                    break

        sl = res_zone_top * 1.005
        risk = sl - res_zone_bot
        tp1 = res_zone_bot - risk * 2
        tp2 = res_zone_bot - risk * 3.5

        return Scenario(
            id=str(uuid.uuid4())[:8], kind="invalidation",
            name=f"Re-entry at {res_zone_bot:.2f}-{res_zone_top:.2f}",
            direction="SHORT",
            trigger_price=res_zone_bot, trigger_condition="price_breaks_above",
            entry_zone_top=res_zone_top, entry_zone_bottom=res_zone_bot,
            sl=sl, tp1=tp1, tp2=tp2,
            invalidation_price=sl,
            state="PENDING",
            note=f"Ana plan bozulursa {resistance:.2f} bölgesinde confirmation arayıp re-entry"
        )

    def _build_plan_b_long(self, support: float, range_low: float,
                            stacked_zones: list) -> Optional[Scenario]:
        """
        Plan B — bozulma da tutmazsa en son hedef.
        Efloud: "2240 de tutmazsa 2090'a."
        """
        if range_low == 0:
            return None

        # En güçlü yığılmış destek bölgesini bul
        target_zone = None
        if stacked_zones:
            candidates = [z for z in stacked_zones
                          if z.top < support and z.top > range_low * 0.95]
            if candidates:
                target_zone = max(candidates, key=lambda z: z.strength)

        if target_zone:
            zone_top = target_zone.top
            zone_bot = target_zone.bottom
        else:
            zone_top = range_low * 1.02
            zone_bot = range_low

        sl = zone_bot * 0.98
        risk = zone_top - sl
        tp1 = zone_top + risk * 2
        tp2 = zone_top + risk * 4

        return Scenario(
            id=str(uuid.uuid4())[:8], kind="plan_b",
            name=f"Deep pullback LONG at {zone_bot:.2f}-{zone_top:.2f}",
            direction="LONG",
            trigger_price=zone_top, trigger_condition="price_breaks_below",
            entry_zone_top=zone_top, entry_zone_bottom=zone_bot,
            sl=sl, tp1=tp1, tp2=tp2,
            invalidation_price=sl,
            expires_after_bars=100,
            state="PENDING",
            note="İki destek de tutmazsa en derin pullback fırsatı"
        )

    def _build_plan_b_short(self, resistance: float, range_high: float,
                              stacked_zones: list) -> Optional[Scenario]:
        if range_high == 0:
            return None

        target_zone = None
        if stacked_zones:
            candidates = [z for z in stacked_zones
                          if z.bottom > resistance and z.bottom < range_high * 1.05]
            if candidates:
                target_zone = max(candidates, key=lambda z: z.strength)

        if target_zone:
            zone_top = target_zone.top
            zone_bot = target_zone.bottom
        else:
            zone_top = range_high
            zone_bot = range_high * 0.98

        sl = zone_top * 1.02
        risk = sl - zone_bot
        tp1 = zone_bot - risk * 2
        tp2 = zone_bot - risk * 4

        return Scenario(
            id=str(uuid.uuid4())[:8], kind="plan_b",
            name=f"Deep pullback SHORT at {zone_bot:.2f}-{zone_top:.2f}",
            direction="SHORT",
            trigger_price=zone_bot, trigger_condition="price_breaks_above",
            entry_zone_top=zone_top, entry_zone_bottom=zone_bot,
            sl=sl, tp1=tp1, tp2=tp2,
            invalidation_price=sl,
            expires_after_bars=100,
            state="PENDING",
            note="İki direnç de tutmazsa en uç short fırsatı"
        )

    # ── Senaryo takibi ──

    def check_triggers(self, current_price: float) -> List[Scenario]:
        """
        Fiyat hangi senaryoları tetikledi?
        
        Trigger koşulları yönlüdür:
        - LONG senaryo + "price_breaks_below": fiyat trigger_price altına düşerse tetikle
        - LONG senaryo + "price_reaches": fiyat entry zone'a girerse tetikle
        - SHORT senaryo + "price_breaks_above": fiyat trigger_price üstüne çıkarsa tetikle
        
        Ek kural: PENDING senaryo sadece belirlenen yönde hareket halinde tetiklenir.
        Invalidation price'ı zaten geçilmişse tetiklenmez (geç kalmış senaryo).
        """
        triggered = []
        for s in self.scenarios:
            if s.state != "PENDING":
                continue

            is_long = s.direction == "LONG"
            
            # Geç kalmış senaryo kontrolü — fiyat zaten invalidation geçmiş mi?
            if (is_long and current_price <= s.invalidation_price):
                s.state = "EXPIRED"
                log.info(f"⏰ SCENARIO EXPIRED (late): {s.name}")
                continue
            if (not is_long and current_price >= s.invalidation_price):
                s.state = "EXPIRED"
                log.info(f"⏰ SCENARIO EXPIRED (late): {s.name}")
                continue

            is_triggered = False
            if s.trigger_condition == "price_breaks_below" and current_price <= s.trigger_price:
                is_triggered = True
            elif s.trigger_condition == "price_breaks_above" and current_price >= s.trigger_price:
                is_triggered = True
            elif s.trigger_condition == "price_reaches":
                if s.entry_zone_bottom <= current_price <= s.entry_zone_top:
                    is_triggered = True

            if is_triggered:
                s.state = "TRIGGERED"
                s.triggered_at = datetime.utcnow().isoformat()
                triggered.append(s)
                log.info(f"⚡ SCENARIO TRIGGERED: {s.kind} | {s.name}")

        return triggered

    def invalidate_scenarios(self, current_price: float):
        """Fiyat hangi senaryoları geçersiz kıldı?
        
        Sadece ACTIVE ve TRIGGERED durumundaki senaryolar için invalidation kontrolü yapılır.
        PENDING senaryolar tetiklenmeden invalidate olmaz.
        """
        for s in self.scenarios:
            # PENDING'ler için expire kontrolü ayrı
            if s.state not in ("ACTIVE", "TRIGGERED"):
                continue
            is_long = s.direction == "LONG"
            if (is_long and current_price <= s.invalidation_price) or \
               (not is_long and current_price >= s.invalidation_price):
                s.state = "INVALIDATED"
                log.info(f"❌ SCENARIO INVALIDATED: {s.name} @ {current_price:.2f}")

    def active_scenarios(self) -> List[Scenario]:
        return [s for s in self.scenarios if s.state in ("ACTIVE", "PENDING", "TRIGGERED")]
