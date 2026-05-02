"""
Position Guards — Pozisyon bazlı güvenlik kuralları
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Check'ler:
  - Size cap (tek trade max %20 notional)
  - Total exposure (tüm pozisyonlar < 5x equity)
  - Max holding time (default 48h)
  - Max pyramid adds (default 2)
  - Duplicate direction (same sym + same dir = reject)
  - Minimum SL distance (ATR tabanlı, whipsaw'dan kaçınmak için)
"""

import logging
from dataclasses import dataclass
from typing import Optional, List
from datetime import datetime, timedelta

log = logging.getLogger("efloud.posguard")


@dataclass
class PositionCheckResult:
    allowed: bool
    reason: str = ""
    warnings: list = None

    def __post_init__(self):
        if self.warnings is None:
            self.warnings = []


class PositionGuard:
    """
    Her pozisyon açma/ekleme öncesi sorulan guard.
    """

    def __init__(self,
                 max_notional_pct_of_balance: float = 20.0,
                 max_total_exposure_multiplier: float = 5.0,
                 max_holding_hours: float = 48.0,
                 max_pyramid_adds: int = 2,
                 min_sl_distance_atr: float = 0.5,
                 max_sl_distance_atr: float = 5.0,
                 reserve_balance: float = 0.0):
        self.max_size_pct = max_notional_pct_of_balance / 100
        self.max_exposure = max_total_exposure_multiplier
        self.max_hold = max_holding_hours
        self.max_adds = max_pyramid_adds
        self.min_sl_atr = min_sl_distance_atr
        self.max_sl_atr = max_sl_distance_atr
        self.reserve_balance = reserve_balance

    def can_open_position(self,
                            balance: float,
                            entry: float,
                            size: float,
                            sl: float,
                            atr: float,
                            direction: str,
                            symbol: str,
                            existing_positions: list,
                            leverage: int = 1) -> PositionCheckResult:
        """Yeni pozisyon açılabilir mi?"""
        warnings = []

        # 1. Size > 0
        if size <= 0:
            return PositionCheckResult(False, "Size is zero or negative")

        # 2. Size cap
        notional = entry * size
        if leverage > 1:
            notional = notional / leverage  # Margin değeri

        # 2.5 Reserve balance check — bakiye - margin - reserve > 0 olmalı
        if self.reserve_balance > 0:
            free_after_trade = balance - notional - self.reserve_balance
            if free_after_trade < 0:
                return PositionCheckResult(
                    False,
                    f"Reserve violated: balance ${balance:.2f} - "
                    f"margin ${notional:.2f} - reserve ${self.reserve_balance:.2f} = "
                    f"${free_after_trade:.2f} (negatif)"
                )

        max_notional = balance * self.max_size_pct
        # Float tolerance: 1e-6 USDT (well below any Binance increment).
        # Without this, notional=33.30000000001 vs max=33.3 falsely rejects.
        if notional > max_notional + 1e-6:
            return PositionCheckResult(
                False,
                f"Size {notional:.2f} exceeds max {max_notional:.2f} "
                f"({self.max_size_pct*100:.2f}% of balance)"
            )

        # 3. Total exposure (tüm pozisyonların notional/balance oranı)
        total_notional = sum(
            p.avg_entry_price * p.remaining_size
            for p in existing_positions
            if p.is_open
        )
        new_total = total_notional + notional
        exposure_multiple = new_total / balance if balance > 0 else 0
        if exposure_multiple > self.max_exposure:
            return PositionCheckResult(
                False,
                f"Total exposure {exposure_multiple:.2f}x exceeds max {self.max_exposure}x"
            )

        # 4. Duplicate direction check
        for p in existing_positions:
            if (p.is_open and p.symbol == symbol and p.direction == direction
                and p.scenario_id is None):  # hedge değil
                return PositionCheckResult(
                    False,
                    f"Already {direction} open on {symbol} (pos {p.id})"
                )

        # 5. SL distance sanity (ATR tabanlı)
        if atr > 0:
            sl_dist = abs(entry - sl)
            sl_atr_mult = sl_dist / atr
            if sl_atr_mult < self.min_sl_atr:
                return PositionCheckResult(
                    False,
                    f"SL too tight: {sl_atr_mult:.2f} ATR < min {self.min_sl_atr}. "
                    f"Whipsaw risk — reject."
                )
            if sl_atr_mult > self.max_sl_atr:
                warnings.append(
                    f"SL very wide: {sl_atr_mult:.2f} ATR > {self.max_sl_atr}. "
                    f"Consider smaller size."
                )

        # 6. Risk per trade sanity
        risk_amount = abs(entry - sl) * size
        risk_pct = (risk_amount / balance) * 100 if balance > 0 else 0
        if risk_pct > 5:
            return PositionCheckResult(
                False,
                f"Risk per trade {risk_pct:.2f}% exceeds hard cap 5%"
            )

        return PositionCheckResult(True, warnings=warnings)

    def can_add_to_position(self,
                              position,
                              add_size: float,
                              current_price: float) -> PositionCheckResult:
        """Piramit ekleme yapılabilir mi?"""
        warnings = []

        if not position.is_open:
            return PositionCheckResult(False, "Position is closed")

        # Max adds count
        non_initial_entries = [e for e in position.entries if e.reason != "initial"]
        if len(non_initial_entries) >= self.max_adds:
            return PositionCheckResult(
                False,
                f"Max {self.max_adds} pyramid adds reached"
            )

        # Total size sonrası initial'ın 2 katını geçmemeli
        initial_size = position.entries[0].size
        new_total = position.total_size_entered + add_size
        if new_total > initial_size * 2:
            return PositionCheckResult(
                False,
                f"Total size after add ({new_total:.4f}) exceeds 2× initial ({initial_size*2:.4f})"
            )

        # Pozisyon tekrar kârda olmalı (TP1 hit veya current price > avg for long)
        if position.direction == "LONG":
            in_profit = current_price > position.avg_entry_price or position.tp1_hit
        else:
            in_profit = current_price < position.avg_entry_price or position.tp1_hit

        if not in_profit and not position.tp1_hit:
            warnings.append("Adding to losing position — higher risk")

        return PositionCheckResult(True, warnings=warnings)

    def check_holding_time(self, position) -> PositionCheckResult:
        """Pozisyon çok uzun süredir açık mı?"""
        if not position.opened_at:
            return PositionCheckResult(True)

        try:
            opened = datetime.fromisoformat(position.opened_at.replace("Z", ""))
        except Exception:
            return PositionCheckResult(True)

        age = datetime.utcnow() - opened
        hours = age.total_seconds() / 3600

        if hours > self.max_hold:
            return PositionCheckResult(
                False,
                f"Position age {hours:.1f}h exceeds max {self.max_hold}h — force close recommended"
            )

        if hours > self.max_hold * 0.8:
            return PositionCheckResult(
                True,
                warnings=[f"Position aging: {hours:.1f}h / {self.max_hold}h"]
            )

        return PositionCheckResult(True)


def cleanup_orphan_hedges(positions: list, logger=None) -> list:
    """
    Ana pozisyon kapanmış ama hedge hâlâ açık — orphan hedge tespiti.

    Returns: orphan hedge listesi (manual review için)
    """
    orphans = []
    for p in positions:
        if not p.is_open:
            continue
        # Hedge'ler scenario_id "hedge_of_X" formatında
        if p.scenario_id and "hedge_of_" in p.scenario_id:
            parent_id = p.scenario_id.replace("hedge_of_", "")
            parent = next((pp for pp in positions if pp.id == parent_id), None)
            if parent is None or not parent.is_open:
                orphans.append(p)
                if logger:
                    logger.warning(f"🔓 Orphan hedge detected: {p.id} (parent {parent_id} closed)")
    return orphans
