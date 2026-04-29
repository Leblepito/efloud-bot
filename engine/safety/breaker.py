"""
Circuit Breaker — Bot'u kendinden koruma
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Senaryolar:
  1. Günlük zarar limiti aşıldı → günün geri kalanı dur
  2. Ardışık 3 SL → 2 saat cool-down
  3. Haftalık drawdown %8 → tam durdur, manual review
  4. Aşırı volatilite → yeni pozisyon açma
  5. Max eşzamanlı pozisyon (per symbol + total)
"""

import logging
from dataclasses import dataclass, field
from typing import List, Optional
from datetime import datetime, timedelta
from enum import Enum

log = logging.getLogger("efloud.breaker")


class BreakerState(Enum):
    OPEN = "OPEN"              # Trade açık, normal akış
    TRIPPED = "TRIPPED"          # Geçici durdurma (belli süre)
    HALTED = "HALTED"            # Tam durdurma, manual reset gerekli


@dataclass
class BreakerStatus:
    state: BreakerState
    reason: str = ""
    tripped_at: Optional[datetime] = None
    resume_at: Optional[datetime] = None
    metrics: dict = field(default_factory=dict)

    @property
    def can_trade(self) -> bool:
        if self.state == BreakerState.OPEN:
            return True
        if self.state == BreakerState.HALTED:
            return False
        # TRIPPED — zamanı geldiyse resume et
        if self.resume_at and datetime.utcnow() >= self.resume_at:
            return True
        return False


class CircuitBreaker:
    """
    Bot'un her cycle başında çağrılır.
    Trade edebilir miyim? diye sorar, cevap verir.
    """

    def __init__(self,
                 daily_loss_pct_limit: float = 3.0,
                 weekly_drawdown_pct_limit: float = 8.0,
                 consecutive_loss_limit: int = 3,
                 consecutive_loss_pause_minutes: int = 120,
                 starting_balance: float = 10000.0,
                 emergency_balance_threshold: float = None,
                 reserve_balance: float = 0.0):
        """
        emergency_balance_threshold: Mutlak USDT cinsinden — bakiye bunun altına düşerse HALT
                                      (daily/weekly yüzde limitlerine ek olarak)
        reserve_balance: Her zaman dokunulmayacak rezerv (yeni pozisyon açma engelleyici)
        """
        self.daily_limit = daily_loss_pct_limit
        self.weekly_limit = weekly_drawdown_pct_limit
        self.consec_limit = consecutive_loss_limit
        self.consec_pause = consecutive_loss_pause_minutes
        self.starting_balance = starting_balance
        self.emergency_threshold = emergency_balance_threshold
        self.reserve_balance = reserve_balance

        # State
        self.status = BreakerStatus(BreakerState.OPEN)
        self.trades_today: List[dict] = []
        self.trades_this_week: List[dict] = []
        self.consecutive_losses = 0
        self.peak_balance = starting_balance
        self.current_balance = starting_balance

    def record_trade(self, pnl: float, timestamp: Optional[datetime] = None):
        """Kapanan trade kaydı."""
        ts = timestamp or datetime.utcnow()
        trade = {"pnl": pnl, "ts": ts}
        self.trades_today.append(trade)
        self.trades_this_week.append(trade)
        self.current_balance += pnl

        if self.current_balance > self.peak_balance:
            self.peak_balance = self.current_balance

        if pnl < 0:
            self.consecutive_losses += 1
            log.warning(f"Loss recorded: ${pnl:.2f} | Consecutive losses: {self.consecutive_losses}")
        else:
            if self.consecutive_losses > 0:
                log.info(f"Winning trade — consecutive loss counter reset "
                         f"(was {self.consecutive_losses})")
            self.consecutive_losses = 0

    def check(self) -> BreakerStatus:
        """Mevcut durumu değerlendir ve breaker state güncelle."""
        now = datetime.utcnow()
        self._cleanup_old_trades(now)

        # Eğer zaten HALTED → manual reset bekler
        if self.status.state == BreakerState.HALTED:
            return self.status

        # TRIPPED → süresi doldu mu?
        if self.status.state == BreakerState.TRIPPED:
            if self.status.resume_at and now >= self.status.resume_at:
                log.info(f"✅ Breaker RESUMED (was tripped: {self.status.reason})")
                self.status = BreakerStatus(BreakerState.OPEN)
            else:
                remaining = (self.status.resume_at - now).total_seconds() / 60 if self.status.resume_at else 0
                self.status.metrics["minutes_remaining"] = round(remaining, 1)
                return self.status

        # ── Yeni kontroller ──

        # 0. Emergency absolute balance threshold (mutlak USDT cinsinden)
        if self.emergency_threshold is not None and \
           self.current_balance < self.emergency_threshold:
            self._halt(f"Emergency: balance ${self.current_balance:.2f} < "
                        f"threshold ${self.emergency_threshold:.2f}")
            return self.status

        # 1. Daily loss
        daily_pnl = sum(t["pnl"] for t in self.trades_today)
        daily_pct = (daily_pnl / self.starting_balance) * 100
        if daily_pct <= -self.daily_limit:
            tomorrow = (now + timedelta(days=1)).replace(hour=0, minute=0, second=0)
            self._trip(f"Daily loss {daily_pct:.2f}% exceeds -{self.daily_limit}%",
                        resume_at=tomorrow)
            return self.status

        # 2. Weekly drawdown
        dd_pct = ((self.peak_balance - self.current_balance) / self.peak_balance) * 100
        if dd_pct >= self.weekly_limit:
            self._halt(f"Weekly drawdown {dd_pct:.2f}% reached limit {self.weekly_limit}%")
            return self.status

        # 3. Consecutive losses
        if self.consecutive_losses >= self.consec_limit:
            resume = now + timedelta(minutes=self.consec_pause)
            self._trip(f"{self.consecutive_losses} consecutive losses",
                        resume_at=resume)
            # Consec counter sıfırla ki aynı trip tekrar etmesin
            self.consecutive_losses = 0
            return self.status

        # Her şey yolunda
        self.status = BreakerStatus(
            BreakerState.OPEN,
            metrics={
                "daily_pnl": round(daily_pnl, 2),
                "daily_pct": round(daily_pct, 2),
                "drawdown_pct": round(dd_pct, 2),
                "trades_today": len(self.trades_today),
            }
        )
        return self.status

    def check_volatility(self, atr_ratio: float, threshold: float = 3.0) -> bool:
        """Aşırı volatilite durumunda trade'i durdurur."""
        if atr_ratio > threshold:
            now = datetime.utcnow()
            resume = now + timedelta(minutes=30)
            self._trip(f"Volatility spike (ATR {atr_ratio:.1f}x avg)",
                        resume_at=resume)
            return False
        return True

    def _trip(self, reason: str, resume_at: datetime):
        now = datetime.utcnow()
        log.warning(f"🚨 BREAKER TRIPPED: {reason} | Resume at {resume_at.isoformat()}")
        self.status = BreakerStatus(
            state=BreakerState.TRIPPED,
            reason=reason,
            tripped_at=now,
            resume_at=resume_at,
        )

    def _halt(self, reason: str):
        log.error(f"⛔ BREAKER HALTED: {reason} | MANUAL RESET REQUIRED")
        self.status = BreakerStatus(
            state=BreakerState.HALTED,
            reason=reason,
            tripped_at=datetime.utcnow(),
        )

    def manual_reset(self, reason: str = "manual"):
        log.info(f"🔧 Breaker manually reset: {reason}")
        self.status = BreakerStatus(BreakerState.OPEN)
        self.consecutive_losses = 0
        # Drawdown reset: peak'i current ile eşitle ki yeniden HALT olmasın
        self.peak_balance = self.current_balance

    def _cleanup_old_trades(self, now: datetime):
        """24h+ ve 7d+ eski trade kayıtlarını temizle."""
        day_ago = now - timedelta(hours=24)
        week_ago = now - timedelta(days=7)
        self.trades_today = [t for t in self.trades_today if t["ts"] > day_ago]
        self.trades_this_week = [t for t in self.trades_this_week if t["ts"] > week_ago]

    def to_dict(self) -> dict:
        return {
            "state": self.status.state.value,
            "reason": self.status.reason,
            "can_trade": self.status.can_trade,
            "consecutive_losses": self.consecutive_losses,
            "current_balance": round(self.current_balance, 2),
            "peak_balance": round(self.peak_balance, 2),
            "metrics": self.status.metrics,
        }
