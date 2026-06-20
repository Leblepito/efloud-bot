"""
Circuit Breaker — Bot'u kendinden koruma
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Senaryolar:
  1. Günlük zarar limiti aşıldı → günün geri kalanı dur
  2. Ardışık 3 SL → 2 saat cool-down
  3. Haftalık drawdown %8 → tam durdur, manual review
  4. Emergency balance threshold → HALT

Volatilite per-symbol RegimeDetector'da filtrelenir (VOLATILE → can_open_new_position=False),
burada global trip'lenmez — tek sembolün spike'ı tüm portföyü kilitlemesin.
"""

import logging
from dataclasses import dataclass, field
from typing import List, Optional
from datetime import datetime, timedelta
from enum import Enum

log = logging.getLogger("efloud.breaker")


def _parse_dt(value) -> Optional[datetime]:
    """Parse an ISO datetime string back to datetime; pass through None/datetime."""
    if value is None or isinstance(value, datetime):
        return value
    try:
        return datetime.fromisoformat(value)
    except (ValueError, TypeError):
        return None


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
                 starting_balance: float = None,
                 emergency_balance_threshold: float = None,
                 reserve_balance: float = 0.0):
        """
        emergency_balance_threshold: Mutlak USDT cinsinden — bakiye bunun altına düşerse HALT
                                      (daily/weekly yüzde limitlerine ek olarak)
        reserve_balance: Her zaman dokunulmayacak rezerv (yeni pozisyon açma engelleyici)
        """
        import os
        is_dev = os.environ.get("ENV", "dev") == "dev"
        if starting_balance is None:
            if not is_dev:
                raise ValueError("starting_balance must be explicitly configured in production mode")
            starting_balance = 10000.0
        elif starting_balance <= 0:
            raise ValueError("starting_balance must be positive")

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

    def sync_balance(self, live_balance: float):
        """Sync current_balance from live exchange data (mark-to-market equity).

        Without this, current_balance only updates via record_trade(pnl), which is
        REALIZED-only — so unrealized PnL on open positions would not be reflected,
        and the breaker would track a stale value drifting from the actual wallet.

        Updates peak_balance too (high-watermark for drawdown calc).

        Does NOT touch breaker state (HALTED stays HALTED until manual_reset). This
        is by design — HALT is a safety stop requiring human acknowledgment, not an
        automatic recovery on balance bounce.
        """
        self.current_balance = float(live_balance)
        if self.current_balance > self.peak_balance:
            self.peak_balance = self.current_balance

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

    def record_trade_correction(self, old_pnl: float, new_pnl: float):
        """M4: re-apply an exchange-truth PnL correction (from the audit sweep) to
        the breaker after a trade was already recorded with an estimate.

        A sign-flipped local estimate (a net-loss trade fed as a WIN) wrongly
        RESETS the consecutive-loss counter, weakening consecutive_loss_limit.
        Here we (1) adjust current_balance by the delta and (2) update the matching
        most-recent today's trade and RECOMPUTE the consecutive-loss counter from
        the tail — the canonical "trailing losses" definition record_trade itself
        maintains. This correctly restores a count the win-reset erased (e.g.
        loss, loss, est-win→0 then corrected to loss → 3), which a naive +1 cannot.

        The counter is recomputed PURELY from the corrected exchange-truth ledger:
        a win→loss correction restores a trailing loss the reset erased (earlier
        trip), and a genuine loss→win correction decrements it (clamped ≥0). No
        monotonic "only-adds" guarantee is implied — it simply tracks the corrected
        ledger. Trip/halt logic is unchanged — the next check() reads the new count.
        Default-OFF at the call site."""
        self.current_balance += (new_pnl - old_pnl)
        if self.current_balance > self.peak_balance:
            self.peak_balance = self.current_balance
        # Update the matching (most-recent, by value) today's trade in place. The
        # same dict object is shared with trades_this_week, so both stay coherent.
        for trade in reversed(self.trades_today):
            if abs(trade["pnl"] - old_pnl) < 1e-9:
                trade["pnl"] = new_pnl
                break
        # Recompute trailing-loss count from the corrected ledger.
        recomputed = 0
        for trade in reversed(self.trades_today):
            if trade["pnl"] < 0:
                recomputed += 1
            else:
                break
        if recomputed != self.consecutive_losses:
            log.warning(
                f"PnL audit corrected (${old_pnl:.2f}→${new_pnl:.2f}); "
                f"consecutive losses {self.consecutive_losses}→{recomputed}"
            )
        self.consecutive_losses = recomputed

    def check(self, now: Optional[datetime] = None) -> BreakerStatus:
        """Mevcut durumu değerlendir ve breaker state güncelle.

        `now`: optional sim-time. Live mode passes None → wall-clock. Backtest
        engine passes the current bar timestamp so cooldowns resolve in sim-time
        rather than wall-clock (otherwise a 120-min cooldown wastes 120 REAL
        minutes of backtest while sim-time advances unbounded).
        """
        if now is None:
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

        # 1. Daily loss — sum only trades since calendar midnight so the window
        # matches the calendar-midnight resume below. Summing the rolling-24h
        # trades_today instead left a late-day loss counted past midnight, so the
        # breaker immediately re-tripped at resume and the halt stretched ~1 extra
        # day (bug-hunt #11).
        _midnight = now.replace(hour=0, minute=0, second=0, microsecond=0)
        today_trades = [t for t in self.trades_today if t["ts"] >= _midnight]
        # Skip trades with missing/None pnl (open positions, journal entry without
        # realized PnL). Bug-hunt #13: previously sum() raised TypeError when a
        # trade's pnl field was None, causing run_cycle to fail every tick.
        daily_pnl = sum(t["pnl"] for t in today_trades if t.get("pnl") is not None)
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
                "trades_today": len(today_trades),
            }
        )
        return self.status

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
            # tripped_at / resume_at make the HALTED/TRIPPED state recoverable
            # after a restart. Without them, restore_from_dict could not tell a
            # cooldown that already elapsed from one still pending, and a HALT's
            # audit trail (when it tripped) would be lost. ISO strings so the
            # dict survives a plain json.dump without a custom serializer.
            "tripped_at": self.status.tripped_at.isoformat() if self.status.tripped_at else None,
            "resume_at": self.status.resume_at.isoformat() if self.status.resume_at else None,
            "metrics": self.status.metrics,
        }

    def restore_from_dict(self, d: dict) -> None:
        """Rebuild breaker state from a persisted to_dict() payload.

        Full-fidelity counterpart to to_dict(): restores not just the balance /
        peak / consecutive-loss counters (which the old partial restore handled)
        but the actual OPEN/TRIPPED/HALTED *state*, its reason, and the
        tripped_at / resume_at timestamps. This is the fix for the restart-
        un-halt safety gap (incident 2026-05-14): a HALTED breaker that is not
        restored as HALTED would let the bot resume trading on the next cycle
        without operator acknowledgment.

        Tolerant of legacy payloads written before this field set existed: if
        there is no usable "state" key, the balance/consec fields are still
        restored and the breaker stays OPEN (prior behavior).
        """
        # Legacy numeric/counter fields — restored regardless of state.
        self.current_balance = d.get("current_balance", self.current_balance)
        self.peak_balance = d.get("peak_balance", self.peak_balance)
        self.consecutive_losses = d.get("consecutive_losses", self.consecutive_losses)

        state_str = d.get("state")
        if not state_str:
            # Pre-fix breaker.json — no state recorded. Keep OPEN default.
            return
        try:
            state = BreakerState(state_str)
        except ValueError:
            log.warning(f"Unknown breaker state '{state_str}' in persisted dict — defaulting OPEN")
            return

        if state == BreakerState.OPEN:
            self.status = BreakerStatus(BreakerState.OPEN, metrics=d.get("metrics", {}))
            return

        self.status = BreakerStatus(
            state=state,
            reason=d.get("reason", ""),
            tripped_at=_parse_dt(d.get("tripped_at")),
            resume_at=_parse_dt(d.get("resume_at")),
            metrics=d.get("metrics", {}),
        )
        log.info(f"♻️  Restored breaker {state.value} state: {self.status.reason}")

    def restore_from_db_row(self, row: Optional[dict]) -> None:
        """Apply a breaker_state DB-mirror row (migration 010) as a HALT fallback.

        Summary-level: the DB row only mirrors the halt flag + reason + timestamp,
        not the full TRIPPED cooldown machinery. Used on a box where the primary
        file StateStore was lost (VPS rebuild) so a HALT acknowledged by the
        operator is not silently forgotten. A non-halted (or missing) row is a
        no-op — the file StateStore stays authoritative.
        """
        if not row or not row.get("halted"):
            return
        self.status = BreakerStatus(
            state=BreakerState.HALTED,
            reason=row.get("halted_reason") or "restored from DB mirror",
            tripped_at=_parse_dt(row.get("halted_at")),
        )
        log.warning(f"♻️  Restored HALTED state from DB mirror: {self.status.reason}")
