"""
Trade Journal — Her trade'in tam kontekstini persist eder.
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Her trade için kaydedilen bilgiler:
  - ENTRY context: HTF bias, levels, stacked zones, intent score, confluence, reasons
  - EXIT context: exit price, reason (TP1/TP2/SL/WEAKNESS), PnL, final intent
  - ADAPTATIONS: piramit eklemeler, partial kapatmalar, hedge aktivasyonları
  - MARKET STATE: bar index'te fiyat serisi (SL/TP path analizi için)

Dosya: trade_journal.jsonl (her satır bir trade)
"""

import json
import logging
import threading
from pathlib import Path
from dataclasses import dataclass, field, asdict
from typing import List, Optional, Dict, Any
from datetime import datetime

log = logging.getLogger("efloud.journal")


@dataclass
class TradeSnapshot:
    """Bir trade'in tam hayat hikayesi."""
    trade_id: str
    symbol: str
    direction: str                  # "LONG" | "SHORT"
    timeframe: str

    # Entry context
    entry_timestamp: str
    entry_price: float
    sl_initial: float
    tp1_initial: float
    tp2_initial: float
    position_size: float
    htf_bias: str
    intent_score_entry: int
    intent_label_entry: str
    confluence_score: int

    # Slippage & Latency Telemetry
    signal_entry_price: float = 0.0
    actual_fill_price: float = 0.0
    slippage_pct: float = 0.0
    zone_mid: float = 0.0
    ts_signal: Optional[str] = None
    ts_fill: Optional[str] = None
    latency_ms: float = 0.0

    # Market conditions at entry
    confluence_reasons: List[str] = field(default_factory=list)

    # Flags at entry
    in_ote: bool = False
    in_ob: bool = False
    ob_near_swing: bool = False
    has_sfp: bool = False
    zone_at_entry: str = ""         # "PREMIUM" | "DISCOUNT"

    # Nearest levels at entry
    nearest_resistance: float = 0
    nearest_support: float = 0
    stacked_zones_count: int = 0

    # Scenario context
    scenario_kind: Optional[str] = None   # "main" | "invalidation" | "plan_b"
    scenario_name: Optional[str] = None

    # Runtime Agent Team verdict (canonical A7). Populated by
    # SafeOrchestrator._journal_record_entry when an agent team is
    # configured. ``None`` means the team was disabled or skipped.
    # The full dict is preserved so downstream post-mortem analysis
    # (PostMortemAgent) can mine the per-agent verdicts later.
    agent_review: Optional[Dict[str, Any]] = None

    # Adaptations during life
    additions: List[Dict] = field(default_factory=list)
    partial_exits: List[Dict] = field(default_factory=list)
    hedge_opened: bool = False
    hedge_pnl: float = 0.0

    # Exit
    exit_timestamp: Optional[str] = None
    exit_price: Optional[float] = None
    exit_reason: Optional[str] = None
    realized_pnl: float = 0.0
    realized_pnl_pct: float = 0.0
    bars_held: int = 0

    # Post-entry path (analysis için)
    max_favorable_excursion_pct: float = 0.0   # MFE — fiyat en çok ne kadar lehimize gitti
    max_adverse_excursion_pct: float = 0.0     # MAE — fiyat en çok ne kadar aleyhimize gitti

    # Post-mortem
    is_winner: bool = False
    error_tags: List[str] = field(default_factory=list)
    lessons: List[str] = field(default_factory=list)

    # PR C — PnL reconciliation provenance. "estimated" = gross price-diff;
    # "exchange" = net realizedPnl - commission - funding from Binance income.
    pnl_source: str = "estimated"
    realized_pnl_exchange: float = 0.0
    commission_paid: float = 0.0
    funding_paid: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class TradeJournal:
    """Trade kayıtlarını diske yazar ve okur."""

    def __init__(self, journal_path: str = "trade_journal.jsonl"):
        self.path = Path(journal_path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._cache: List[TradeSnapshot] = []
        self._load()

    def _load(self):
        """Mevcut journal'ı yükle."""
        with self._lock:
            if not self.path.exists():
                return
            try:
                with self.path.open("r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if not line:
                            continue
                        data = json.loads(line)
                        snap = TradeSnapshot(**data)
                        self._cache.append(snap)
                log.info(f"Loaded {len(self._cache)} trades from journal")
            except Exception as e:
                log.error(f"Journal load failed: {e}")

    def record_entry(self, snapshot: TradeSnapshot):
        """Yeni trade başladı — full context kaydet."""
        with self._lock:
            existing = self.get(snapshot.trade_id)
            if existing:
                existing.entry_timestamp = snapshot.entry_timestamp
                existing.entry_price = snapshot.entry_price
                existing.sl_initial = snapshot.sl_initial
                existing.tp1_initial = snapshot.tp1_initial
                existing.tp2_initial = snapshot.tp2_initial
                existing.position_size = snapshot.position_size
                existing.htf_bias = snapshot.htf_bias
                existing.intent_score_entry = snapshot.intent_score_entry
                existing.intent_label_entry = snapshot.intent_label_entry
                existing.confluence_score = snapshot.confluence_score
                existing.confluence_reasons = snapshot.confluence_reasons
                existing.scenario_name = snapshot.scenario_name
                existing.signal_entry_price = snapshot.signal_entry_price
                existing.actual_fill_price = snapshot.actual_fill_price
                existing.slippage_pct = snapshot.slippage_pct
                existing.zone_mid = snapshot.zone_mid
                existing.ts_signal = snapshot.ts_signal
                existing.ts_fill = snapshot.ts_fill
                existing.latency_ms = snapshot.latency_ms
                if snapshot.agent_review is not None:
                    existing.agent_review = snapshot.agent_review
                self._persist(existing)
                log.info(f"📝 Journal entry updated (existing): {snapshot.trade_id} {snapshot.direction}")
            else:
                self._cache.append(snapshot)
                log.info(f"📝 Journal entry: {snapshot.trade_id} {snapshot.direction} "
                         f"@ {snapshot.entry_price:.2f}")
                self._persist(snapshot)

    def update_adaptation(self, trade_id: str, kind: str, data: dict):
        """Piramit / partial / hedge güncelleme."""
        with self._lock:
            snap = self.get(trade_id)
            if not snap:
                return
            data["timestamp"] = datetime.utcnow().isoformat()
            if kind == "addition":
                snap.additions.append(data)
            elif kind == "partial":
                snap.partial_exits.append(data)
            elif kind == "hedge_open":
                snap.hedge_opened = True
            elif kind == "hedge_close":
                snap.hedge_pnl = data.get("pnl", 0.0)

    def record_exit(self, trade_id: str, exit_price: float, exit_reason: str,
                     realized_pnl: float, bars_held: int,
                     mfe_pct: float = 0.0, mae_pct: float = 0.0):
        """Trade kapandı — exit context ekle ve diske yaz."""
        with self._lock:
            snap = self.get(trade_id)
            if not snap:
                log.warning(f"Trade {trade_id} not in journal, cannot record exit")
                return

            snap.exit_timestamp = datetime.utcnow().isoformat()
            snap.exit_price = exit_price
            snap.exit_reason = exit_reason
            snap.realized_pnl = realized_pnl
            snap.realized_pnl_pct = (
                (realized_pnl / (snap.entry_price * snap.position_size)) * 100
                if snap.position_size * snap.entry_price > 0 else 0
            )
            snap.bars_held = bars_held
            snap.max_favorable_excursion_pct = mfe_pct
            snap.max_adverse_excursion_pct = mae_pct
            snap.is_winner = realized_pnl > 0

            self._persist(snap)
            log.info(f"📝 Journal exit: {trade_id} {exit_reason} | "
                     f"PnL=${realized_pnl:+.2f} ({snap.realized_pnl_pct:+.2f}%)")

    def update_realized_pnl(self, trade_id: str, realized_pnl: float,
                            pnl_source: str = "exchange",
                            realized_pnl_exchange: float = 0.0,
                            commission_paid: float = 0.0,
                            funding_paid: float = 0.0):
        """Idempotently upgrade a closed trade's PnL to exchange truth.

        Used by the PnL audit sweep (PR C). Mutates the EXISTING snapshot in
        place and rewrites the journal — no duplicate entry row (the bug from
        re-running record_entry+record_exit). No-op if trade_id is unknown.
        """
        with self._lock:
            snap = self.get(trade_id)
            if not snap:
                log.warning(f"update_realized_pnl: {trade_id} not in journal — skip")
                return
            snap.realized_pnl = realized_pnl
            snap.realized_pnl_pct = (
                (realized_pnl / (snap.entry_price * snap.position_size)) * 100
                if snap.position_size * snap.entry_price > 0 else 0
            )
            snap.is_winner = realized_pnl > 0
            snap.pnl_source = pnl_source
            snap.realized_pnl_exchange = realized_pnl_exchange
            snap.commission_paid = commission_paid
            snap.funding_paid = funding_paid
            self._persist(snap)
            log.info(f"📝 Journal PnL reconciled: {trade_id} → ${realized_pnl:+.2f} [{pnl_source}]")

    def attach_lessons(self, trade_id: str, error_tags: List[str], lessons: List[str]):
        """Post-mortem analiz sonuçlarını ekle."""
        with self._lock:
            snap = self.get(trade_id)
            if not snap:
                return
            snap.error_tags = error_tags
            snap.lessons = lessons
            self._persist(snap)

    def _persist(self, snap: TradeSnapshot):
        """Tüm journal'ı yeniden yaz (append only istenmiyor — lesson güncellemesi için)."""
        with self._lock:
            with self.path.open("w", encoding="utf-8") as f:
                for s in self._cache:
                    f.write(json.dumps(s.to_dict(), default=str) + "\n")

    def get(self, trade_id: str) -> Optional[TradeSnapshot]:
        with self._lock:
            for s in self._cache:
                if s.trade_id == trade_id:
                    return s
            return None

    def all_closed(self) -> List[TradeSnapshot]:
        with self._lock:
            return [s for s in self._cache if s.exit_timestamp is not None]

    def recent(self, n: int = 20) -> List[TradeSnapshot]:
        with self._lock:
            closed = self.all_closed()
            return closed[-n:]

    def stats(self) -> dict:
        with self._lock:
            closed = self.all_closed()
            if not closed:
                return {"trades": 0}

            wins = [t for t in closed if t.is_winner]
            losses = [t for t in closed if not t.is_winner]

            total_pnl = sum(t.realized_pnl for t in closed)
            avg_win = sum(t.realized_pnl for t in wins) / len(wins) if wins else 0
            avg_loss = sum(t.realized_pnl for t in losses) / len(losses) if losses else 0

            return {
                "trades": len(closed),
                "wins": len(wins),
                "losses": len(losses),
                "win_rate": round(len(wins) / len(closed) * 100, 1),
                "total_pnl": round(total_pnl, 2),
                "avg_win": round(avg_win, 2),
                "avg_loss": round(avg_loss, 2),
                "profit_factor": round(abs(sum(t.realized_pnl for t in wins) /
                                            sum(t.realized_pnl for t in losses)), 2)
                                 if losses and sum(t.realized_pnl for t in losses) != 0 else 0,
            }

    def update_agent_review(self, trade_id: str, agent_review: Dict[str, Any]):
        """Post-entry: update the agent team review in the snapshot and persist."""
        with self._lock:
            snap = self.get(trade_id)
            if not snap:
                log.warning(f"Trade {trade_id} not in journal, cannot update agent review")
                return
            snap.agent_review = agent_review
            self._persist(snap)
