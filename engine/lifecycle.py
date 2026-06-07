"""
Efloud Position Lifecycle Manager
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Efloud'un yaşayan pozisyon yönetimi:

  Entry → TP hit → kısmi kâr al → SL break-even
       → Momentum zayıflarsa → daha fazla kapat
       → Geri çekilme → önceki seviyede piramit ekle
       → Ters yönlü confirmation → hedge aç
       → Hedge kârda dönerse → zararsız kapat
       → Re-entry: yeni confirmation → tekrar giriş

Bu sadece "aç/kapat" değil — yaşayan, adapte olan bir sistem.

Veri yapıları:
  Position       — ana pozisyon (long veya short)
  Entry          — pozisyona yapılan her giriş (piramit dahil)
  Exit           — her kısmi veya tam kapanış
  HedgePosition  — ana pozisyonun karşı yönlü koruması
"""

import logging
import uuid
from dataclasses import dataclass, field
from typing import List, Optional, Literal
from datetime import datetime, timezone
import pandas as pd

log = logging.getLogger("efloud.lifecycle")

Direction = Literal["LONG", "SHORT"]
ExitReason = Literal["TP1", "TP2", "SL", "MANUAL", "WEAKNESS", "HEDGE_CLOSE"]


@dataclass
class Entry:
    """Bir pozisyona yapılan her giriş (piramit dahil)."""
    id: str
    price: float
    size: float
    timestamp: str
    reason: str = "initial"   # "initial", "add_on_dip", "re_entry"


@dataclass
class Exit:
    """Pozisyondan yapılan her kısmi/tam kapanış."""
    id: str
    price: float
    size: float
    timestamp: str
    reason: ExitReason
    pnl: float


@dataclass
class Position:
    """Ana trade pozisyonu — canlı, adapte olabilen."""
    id: str
    symbol: str
    direction: Direction
    entries: List[Entry] = field(default_factory=list)
    exits: List[Exit] = field(default_factory=list)

    sl: float = 0.0
    tp1: float = 0.0
    # tp2 = None signals single-target mode (SMC v2). v1 always sets a numeric tp2.
    # Lifecycle's partial_close TP1 branch checks `pos.tp2 is None` to trigger
    # a full close instead of the legacy 50% partial + BE-SL move (spec §6).
    tp2: Optional[float] = 0.0
    initial_sl: float = 0.0   # Original SL set at open time — never modified (sl can move to BE)

    # Lifecycle flags
    tp1_hit: bool = False
    tp2_hit: bool = False
    sl_moved_to_be: bool = False   # SL break-even'a çekildi mi

    # Weakness churn protection
    weakness_exit_count: int = 0
    last_weakness_ts: Optional[str] = None

    # Hedge linking
    hedge_id: Optional[str] = None

    # Scenario tracking
    scenario_id: Optional[str] = None

    opened_at: str = ""
    closed_at: Optional[str] = None

    # Per-bar excursion tracking (updated by orchestrator each cycle).
    # mae_pct = max % the bar's worst price went against avg_entry.
    # mfe_pct = max % the bar's best price went in favor of avg_entry.
    # Both are monotonic — once raised, never decrease for this position.
    # Surfaced to TradeJournal at close so Phase 0 evidence can separate
    # H2 (SL too tight: MAE ≤ sl_distance) from H3 (price ran far: MAE >>).
    mae_pct: float = 0.0
    mfe_pct: float = 0.0

    # SMC v2 telemetry (PR #S5) — populated by v2 entry path, None for v1.
    # Surfaced to DB trades table for post-mortem analysis (which entry doctrine
    # fired, what target type drove TP1/TP2, how long the pullback waited).
    entry_setup_source: Optional[str] = None   # "FVG_PULLBACK" | "OTE_RETRACE" | "V1_LEGACY" | None
    tp1_target_type:    Optional[str] = None   # "LIQUIDITY"    | "FVG_NEAR"    | "RR_PROJECTION" | None
    tp2_target_type:    Optional[str] = None   # "FVG_FAR"      | "FIB_EXT"     | "NONE"          | None
    bars_to_pullback:   Optional[int] = None   # bars elapsed AWAITING_PULLBACK → IN_ZONE

    @property
    def is_open(self) -> bool:
        return self.remaining_size > 0.0001

    @property
    def total_size_entered(self) -> float:
        # Skip entries with None size (in-flight entries, journal rows). Bug-hunt
        # #15 (PR #170 follow-up): same None-arithmetic pattern as realized_pnl.
        return sum(e.size for e in self.entries if e.size is not None)

    @property
    def total_size_exited(self) -> float:
        # Skip exits with None size (in-flight exits, journal rows). Bug-hunt
        # #15 (PR #170 follow-up): same None-arithmetic pattern as realized_pnl.
        return sum(e.size for e in self.exits if e.size is not None)

    @property
    def remaining_size(self) -> float:
        return self.total_size_entered - self.total_size_exited

    @property
    def avg_entry_price(self) -> float:
        """Ağırlıklı ortalama giriş fiyatı — KALAN envanterin maliyet temeli.

        Average-cost: entries/exits zaman sırasıyla işlenir, her exit running
        ortalamadan düşülür. Böylece kısmi bir çıkıştan (TP1) SONRA yapılan piramit
        ekleme ortalamayı doğru günceller (çıkmış miktarın maliyet temeli geride
        kalmaz). Çıkıştan sonra ekleme yapılmayan yaygın durumda bu, basit
        tüm-girişler ortalamasıyla AYNIdır → davranış değişmez.
        """
        if not self.entries:
            return 0
        # Merge entries(+) / exits(−) chronologically; tie-break entries before
        # exits so inventory always exists before it is reduced.
        events = sorted(
            [(e.timestamp, 0, e.size, e.price) for e in self.entries]
            + [(x.timestamp, 1, x.size, 0.0) for x in self.exits],
            key=lambda ev: (ev[0], ev[1]),
        )
        # Bug-hunt #15 (PR #170 follow-up): skip events whose entry size or price
        # is None — they can't contribute to the running weighted average, and
        # including them would raise TypeError on price * sz. The fallback at the
        # bottom of the method still uses the simple-all-entries average which
        # also has its own None-skip guard, so partial-None data is handled.
        cost = 0.0
        size = 0.0
        for _ts, kind, sz, price in events:
            if kind == 0:  # entry
                if sz is None or price is None:
                    continue
                cost += price * sz
                size += sz
            elif size > 1e-12:  # exit: remove at the running average
                if sz is None:
                    continue
                cost -= sz * (cost / size)
                size -= sz
        if size > 1e-9:
            return cost / size
        # Fully exited (or float underflow) → fall back to the simple all-entries
        # average so post-close reporting still gets a sane number.
        total_size = self.total_size_entered
        # Skip entries with None price or size. Bug-hunt #15 (PR #170 follow-up):
        # e.price * e.size raised TypeError if either was None. Reuses the
        # total_size_entered None-filter, so we only need to guard e.price here.
        weighted = sum(e.price * e.size for e in self.entries
                      if e.price is not None and e.size is not None)
        return (weighted / total_size if total_size > 0 else 0)

    @property
    def realized_pnl(self) -> float:
        # Skip exits with None pnl (open in-flight exits, journal entries without
        # realized PnL). Bug-hunt #14 (PR #168 follow-up): previously sum() raised
        # TypeError on int + None when an exit was recorded with pnl=None (edge
        # case from remaining-inventory cost-basis math in PR #164 / #167 LOW
        # batch). Without this guard, run_cycle crashed every tick via
        # SafeOrchestrator.run_cycle:944 -> breaker.record_trade.
        return sum(e.pnl for e in self.exits if e.pnl is not None)

    def unrealized_pnl(self, current_price: float) -> float:
        if not self.is_open:
            return 0
        if current_price is None:
            # Bug-hunt #15 (PR #170 follow-up): price_map can carry None for
            # symbols whose WS snapshot is stale or never landed. Returning 0
            # keeps lifecycle math intact; the next tick with a real price
            # resumes the calculation.
            return 0
        avg = self.avg_entry_price
        diff = (current_price - avg) if self.direction == "LONG" else (avg - current_price)
        return diff * self.remaining_size

    def update_excursion(self, high: float, low: float) -> None:
        """Update mae_pct/mfe_pct from this bar's price extremes.

        LONG: adverse = bar low below avg; favorable = bar high above avg.
        SHORT: adverse = bar high above avg; favorable = bar low below avg.

        Monotonic max: once raised, mae_pct/mfe_pct never decrease for this
        position. Zero or negative inputs are silently ignored.
        """
        avg = self.avg_entry_price
        if avg <= 0 or high <= 0 or low <= 0:
            return
        if self.direction == "LONG":
            adverse = max(0.0, (avg - low) / avg * 100.0)
            favorable = max(0.0, (high - avg) / avg * 100.0)
        else:  # SHORT
            adverse = max(0.0, (high - avg) / avg * 100.0)
            favorable = max(0.0, (avg - low) / avg * 100.0)
        if adverse > self.mae_pct:
            self.mae_pct = adverse
        if favorable > self.mfe_pct:
            self.mfe_pct = favorable

    def to_dict(self) -> dict:
        """Compact summary (counts of entries/exits) — used by report/UI snapshots."""
        return {
            "id": self.id, "symbol": self.symbol, "direction": self.direction,
            "avg_entry": round(self.avg_entry_price, 8),
            "remaining_size": round(self.remaining_size, 8),
            "sl": self.sl, "tp1": self.tp1, "tp2": self.tp2,
            "tp1_hit": self.tp1_hit, "tp2_hit": self.tp2_hit,
            "sl_at_be": self.sl_moved_to_be,
            "realized_pnl": round(self.realized_pnl, 2),
            "entries": len(self.entries), "exits": len(self.exits),
            "hedge_id": self.hedge_id, "scenario_id": self.scenario_id,
        }

    def to_full_dict(self) -> dict:
        """Lossless serialization — preserves entries/exits for state restore.

        Required to restore lifecycle.positions after a bot restart so that
        PositionGuard's duplicate-direction check (existing_positions=lifecycle)
        still rejects re-opens. See 2026-05-08 stacking bug.
        """
        return {
            "id": self.id, "symbol": self.symbol, "direction": self.direction,
            "entries": [e.__dict__ for e in self.entries],
            "exits": [e.__dict__ for e in self.exits],
            "sl": self.sl, "tp1": self.tp1, "tp2": self.tp2,
            "initial_sl": self.initial_sl,
            "tp1_hit": self.tp1_hit, "tp2_hit": self.tp2_hit,
            "sl_moved_to_be": self.sl_moved_to_be,
            "weakness_exit_count": self.weakness_exit_count,
            "last_weakness_ts": self.last_weakness_ts,
            "hedge_id": self.hedge_id, "scenario_id": self.scenario_id,
            "opened_at": self.opened_at, "closed_at": self.closed_at,
            # Per-bar excursion (PR #57) — must survive restarts so
            # restart-spanning trades don't reset MAE/MFE to 0 and
            # underreport Phase 0 evidence.
            "mae_pct": self.mae_pct, "mfe_pct": self.mfe_pct,
            # SMC v2 telemetry (PR #S5) — None for v1-opened positions.
            "entry_setup_source": self.entry_setup_source,
            "tp1_target_type": self.tp1_target_type,
            "tp2_target_type": self.tp2_target_type,
            "bars_to_pullback": self.bars_to_pullback,
            # Breaker-dedup flag (C2): STEP 5 records a closed position's
            # realized PnL to the CircuitBreaker once and sets this runtime
            # attribute. It MUST persist — lifecycle never prunes closed
            # positions, so without this a restart re-counts the PnL and
            # corrupts daily_pnl / consecutive_losses / peak_balance.
            "_reported_to_breaker": getattr(self, "_reported_to_breaker", False),
        }

    @classmethod
    def from_full_dict(cls, d: dict) -> "Position":
        """Inverse of to_full_dict.

        Backwards-compat: pre-PR-E state files may not contain mae_pct /
        mfe_pct keys; default to 0.0 so a state-volume upgrade does not
        crash.
        """
        pos = cls(
            id=d["id"], symbol=d["symbol"], direction=d["direction"],
            entries=[Entry(**e) for e in d.get("entries", [])],
            exits=[Exit(**e) for e in d.get("exits", [])],
            sl=d.get("sl", 0.0), tp1=d.get("tp1", 0.0), tp2=d.get("tp2", 0.0),
            initial_sl=d.get("initial_sl", 0.0),
            tp1_hit=d.get("tp1_hit", False),
            tp2_hit=d.get("tp2_hit", False),
            sl_moved_to_be=d.get("sl_moved_to_be", False),
            weakness_exit_count=d.get("weakness_exit_count", 0),
            last_weakness_ts=d.get("last_weakness_ts"),
            hedge_id=d.get("hedge_id"),
            scenario_id=d.get("scenario_id"),
            opened_at=d.get("opened_at", ""),
            closed_at=d.get("closed_at"),
            mae_pct=d.get("mae_pct", 0.0),
            mfe_pct=d.get("mfe_pct", 0.0),
            # SMC v2 telemetry (PR #S5) — None when restoring pre-PR-#S5 state files.
            entry_setup_source=d.get("entry_setup_source"),
            tp1_target_type=d.get("tp1_target_type"),
            tp2_target_type=d.get("tp2_target_type"),
            bars_to_pullback=d.get("bars_to_pullback"),
        )
        # Restore the breaker-dedup flag (C2). Pre-fix state files lack the
        # key → default False. Without this, STEP 5 re-records an already
        # counted closed position's PnL to the breaker after a restart.
        pos._reported_to_breaker = bool(d.get("_reported_to_breaker", False))
        return pos


class PositionLifecycle:
    """
    Pozisyon yönetim motoru.
    Canlı adapte olabilen trade orkestratörü.
    """

    def __init__(self):
        self.positions: List[Position] = []

    # ── Yeni pozisyon aç ──

    def open_position(self, symbol: str, direction: Direction,
                       entry_price: float, size: float,
                       sl: float, tp1: float, tp2: Optional[float],
                       scenario_id: Optional[str] = None,
                       *,
                       entry_setup_source: Optional[str] = None,
                       tp1_target_type: Optional[str] = None,
                       tp2_target_type: Optional[str] = None,
                       bars_to_pullback: Optional[int] = None) -> Position:
        """İlk giriş ile yeni pozisyon aç.

        SMC v2 telemetry kwargs (PR #S5) are keyword-only to keep the positional
        signature stable for existing v1 callers. v1 path passes none of them.
        `tp2` accepts None for single-target setups (v2 may produce these).
        """
        now = datetime.utcnow().isoformat()
        pos_id = str(uuid.uuid4())[:8]

        entry = Entry(str(uuid.uuid4())[:8], entry_price, size, now, "initial")
        pos = Position(
            id=pos_id, symbol=symbol, direction=direction,
            entries=[entry],
            sl=sl, tp1=tp1, tp2=tp2,           # tp2=None preserves single-target marker
            initial_sl=sl,         # snapshot at open — preserves zone for reporting
            scenario_id=scenario_id,
            opened_at=now,
            entry_setup_source=entry_setup_source,
            tp1_target_type=tp1_target_type,
            tp2_target_type=tp2_target_type,
            bars_to_pullback=bars_to_pullback,
        )
        self.positions.append(pos)
        tp2_str = f"{tp2:.2f}" if tp2 is not None else "NONE(single-target)"
        log.info(f"🟢 OPEN {direction} {symbol} size={size:.4f} @ {entry_price:.2f} | SL={sl:.2f} TP1={tp1:.2f} TP2={tp2_str}")
        return pos

    # ── Piramit ekleme ──

    def add_to_position(self, pos: Position, price: float, size: float,
                        reason: str = "add_on_dip") -> bool:
        """
        Mevcut pozisyona ekleme (piramit).
        Efloud örnek: "RH'de kâr realize ettim, EQ'ya düşünce sattıklarımı geri ekledim."
        """
        if not pos.is_open:
            log.warning(f"Cannot add to closed position {pos.id}")
            return False

        now = datetime.utcnow().isoformat()
        entry = Entry(str(uuid.uuid4())[:8], price, size, now, reason)
        pos.entries.append(entry)

        new_avg = pos.avg_entry_price
        log.info(f"➕ ADD {pos.direction} {pos.symbol} size={size:.4f} @ {price:.2f} "
                 f"| New avg={new_avg:.2f} | Reason={reason}")
        return True

    # ── Kısmi kapama ──

    def partial_close(self, pos: Position, price: float, size_pct: float,
                      reason: ExitReason = "TP1") -> bool:
        """
        Pozisyonun bir kısmını kapat.
        size_pct: 0.5 = %50, 0.25 = %25

        Single-target branch (SMC v2, PR #S5): when `pos.tp2 is None` and
        reason is "TP1", close 100% of the position instead of a 50% partial
        followed by a BE-SL move. Inert under v1 (v1 always sets numeric tp2).
        """
        if not pos.is_open:
            return False

        if reason == "TP1" and pos.tp2 is None:
            # Mark TP1 hit before delegating to close_position so downstream
            # consumers (DB persistence, reconcile, notifications) see the same
            # tp1_hit=True flag they would see in the legacy two-target path.
            pos.tp1_hit = True
            return self.close_position(pos, price, "TP1")

        size = pos.remaining_size * size_pct
        now = datetime.utcnow().isoformat()
        avg = pos.avg_entry_price
        diff = (price - avg) if pos.direction == "LONG" else (avg - price)
        pnl = diff * size

        pos.exits.append(Exit(str(uuid.uuid4())[:8], price, size, now, reason, pnl))

        if reason == "TP1":
            pos.tp1_hit = True
            # SL'yi break-even'a çek
            pos.sl = avg
            pos.sl_moved_to_be = True
            log.info(f"🎯 TP1 HIT {pos.symbol} | Closed {size_pct*100:.0f}% @ {price:.2f} "
                     f"| PnL=${pnl:+.2f} | SL → BE @ {avg:.2f}")
        elif reason == "WEAKNESS":
            log.info(f"⚠️  WEAKNESS close {pos.symbol} | {size_pct*100:.0f}% @ {price:.2f} "
                     f"| PnL=${pnl:+.2f}")
        else:
            log.info(f"📉 PARTIAL {reason} {pos.symbol} | {size_pct*100:.0f}% @ {price:.2f}")

        return True

    # ── Tam kapatma ──

    def close_position(self, pos: Position, price: float,
                        reason: ExitReason = "TP2") -> bool:
        """Pozisyonu tamamen kapat."""
        if not pos.is_open:
            return False

        size = pos.remaining_size
        now = datetime.utcnow().isoformat()
        avg = pos.avg_entry_price
        diff = (price - avg) if pos.direction == "LONG" else (avg - price)
        pnl = diff * size

        pos.exits.append(Exit(str(uuid.uuid4())[:8], price, size, now, reason, pnl))
        pos.closed_at = now

        total_pnl = pos.realized_pnl
        pnl_pct = (total_pnl / (avg * pos.total_size_entered)) * 100 if avg > 0 else 0

        emoji = "✅" if total_pnl > 0 else "❌"
        log.info(f"{emoji} CLOSE {pos.symbol} {pos.direction} @ {price:.2f} | "
                 f"Reason={reason} | Total PnL=${total_pnl:+.2f} ({pnl_pct:+.2f}%)")
        return True

    # ── Hedge ──

    def open_hedge(self, main_pos: Position, hedge_price: float, hedge_size: float,
                    sl: float, tp1: float, tp2: float) -> Optional[Position]:
        """
        Ana pozisyona karşı yönlü hedge aç.
        Efloud örnek: "Long pozisyonuma hedge olarak $2310'dan short açtım."
        """
        if main_pos.hedge_id is not None:
            log.warning(f"Position {main_pos.id} already has hedge")
            return None

        hedge_dir: Direction = "SHORT" if main_pos.direction == "LONG" else "LONG"

        hedge = self.open_position(
            main_pos.symbol, hedge_dir, hedge_price, hedge_size,
            sl, tp1, tp2
        )
        hedge.scenario_id = f"hedge_of_{main_pos.id}"
        main_pos.hedge_id = hedge.id

        log.info(f"🛡️  HEDGE opened for {main_pos.id} ({main_pos.direction}) "
                 f"| Hedge={hedge.id} ({hedge_dir}) @ {hedge_price:.2f}")
        return hedge

    def close_hedge_breakeven(self, hedge: Position, current_price: float) -> bool:
        """
        Hedge kârda gittikten sonra giriş noktasına gelirse zararsız kapat.
        Efloud örnek: "Short %5.5 düştü, sonra giriş noktasına döndü, zararsız kapattım."
        """
        avg = hedge.avg_entry_price
        # ±%0.2 tolerans
        if abs(current_price - avg) / avg > 0.002:
            return False
        return self.close_position(hedge, current_price, "HEDGE_CLOSE")

    # ── Tick / bar güncellemesi ──

    def on_tick(self, price_map: dict, intent_checker=None):
        """
        Her fiyat güncellemesinde pozisyonları değerlendir.

        Args:
            price_map: {"BTC/USDT": 43521.0, ...}
            intent_checker: callable(pos) -> bool, True = momentum zayıf
        """
        for pos in list(self.positions):
            if not pos.is_open:
                continue

            price = price_map.get(pos.symbol)
            if price is None:
                continue

            is_long = pos.direction == "LONG"

            # SL check
            if (is_long and price <= pos.sl) or (not is_long and price >= pos.sl):
                self.close_position(pos, price, "SL")
                continue

            # TP2 check (full close) — skip in single-target mode (SMC v2)
            if pos.tp2 is not None:
                if (is_long and price >= pos.tp2) or (not is_long and price <= pos.tp2):
                    self.close_position(pos, price, "TP2")
                    continue

            # TP1 check (%50 close + BE)
            if not pos.tp1_hit:
                if (is_long and price >= pos.tp1) or (not is_long and price <= pos.tp1):
                    self.partial_close(pos, price, 0.5, "TP1")
                    continue

            # Hedge break-even check
            if pos.scenario_id and "hedge_of_" in pos.scenario_id:
                if self.close_hedge_breakeven(pos, price):
                    continue

            # Weakness check (momentum zayıfladı mı?)
            # ── Churn protection ──
            # Max 3 WEAKNESS exits per position to prevent geometric-decay churn.
            # Min 4 bars (≈4 min on 1m) between consecutive WEAKNESS exits.
            # Min remaining size 0.01 to avoid dust exits.
            MAX_WEAKNESS_EXITS = 3
            WEAKNESS_COOLDOWN_BARS = 4   # minutes between weakness exits
            MIN_REMAINING_NOTIONAL_USDT = 5.0   # dust floor (notional, not asset units)

            if intent_checker and pos.tp1_hit and pos.weakness_exit_count < MAX_WEAKNESS_EXITS:
                # Cooldown check
                if pos.last_weakness_ts:
                    try:
                        last_t = datetime.fromisoformat(pos.last_weakness_ts)
                        elapsed = (datetime.now(timezone.utc) - last_t).total_seconds() / 60.0
                        if elapsed < WEAKNESS_COOLDOWN_BARS:
                            continue
                    except (ValueError, TypeError):
                        pass  # bad timestamp — allow the check

                # Dust check — compare NOTIONAL (remaining_size × price), not asset
                # units. Comparing the contract count to a USDT constant suppressed
                # weakness exits on high-priced assets (0.005 BTC ≈ $500 < 0.01) and
                # never fired for sub-$1 coins (bug-hunt #12).
                if pos.remaining_size * price < MIN_REMAINING_NOTIONAL_USDT:
                    continue

                if intent_checker(pos):
                    pos.weakness_exit_count += 1
                    pos.last_weakness_ts = datetime.now(timezone.utc).isoformat()
                    self.partial_close(pos, price, 0.25, "WEAKNESS")

    # ── Query ──

    def open_positions(self, symbol: Optional[str] = None) -> List[Position]:
        return [p for p in self.positions if p.is_open and
                (symbol is None or p.symbol == symbol)]

    def same_direction_open(self, symbol: str, direction: Direction) -> Optional[Position]:
        for p in self.positions:
            if p.is_open and p.symbol == symbol and p.direction == direction \
               and p.scenario_id is None:  # hedge değil
                return p
        return None

    def get_hedge_of(self, pos: Position) -> Optional[Position]:
        if pos.hedge_id is None:
            return None
        for p in self.positions:
            if p.id == pos.hedge_id:
                return p
        return None

    @property
    def total_realized_pnl(self) -> float:
        return sum(p.realized_pnl for p in self.positions)
