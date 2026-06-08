"""
Safe Orchestrator v2.1 — Güvenlik Katmanları Entegre
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Önceki orchestrator'un üstüne:
  - Circuit breaker check (her cycle başında)
  - Regime detection (trading kararı rejime göre)
  - Data freshness validation
  - Position guards (size, exposure, SL distance)
  - State persistence
  - Exchange reconciliation
"""

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Optional, TYPE_CHECKING
from dataclasses import dataclass

import pandas as pd

if TYPE_CHECKING:
    from engine.smc_v2.setup_state import SetupStateStore
    from engine.smc_v2.zones import ZoneSpec

from .smc import SMCEngine
from .levels import LevelEngine
from .intent import IntentEngine
from .signals import generate_signals
from .scenarios import ScenarioPlanner
from .lifecycle import PositionLifecycle, Position
from .journal import TradeJournal, TradeSnapshot
from .report import ReportEngine
from .regimes import RegimeDetector, RegimeAnalysis
from .safety import (
    CircuitBreaker, StateStore, PositionGuard, load_pause_config,
    OrphanProtector, load_orphan_protection_config,
    validate_kline_freshness, validate_kline_integrity,
    StaleDataError, cleanup_orphan_hedges
)
from utils.logging import new_trace_id, set_trace_id

log = logging.getLogger("efloud.safe_orch")


def _sizing_balance(client, source, live_balance: float) -> float:
    """Choose which balance metric to feed into position sizing.

    Args:
        client: BinanceClient instance, or None in dry_run.
        source: 'total' | 'available' | None. None and unknown values fall
            back to 'total' (with a warning) for backward compatibility.
        live_balance: the balance already fetched by the caller; used when
            client is None (dry_run) and as the 'total' return value.

    Returns:
        Float USDT amount to use as the 'balance' parameter for
        calc_position_size().

    Contract:
        - 'total' → live_balance (totalMarginBalance, already fetched)
        - 'available' → client.get_available_margin() (availableBalance)
        - None / typo → live_balance + log warning
        - client is None → live_balance (no exchange call, dry_run safe)

    Worked example ('available' mode, $2000 wallet, 10% notional cap, 5x lev):

        Step  | Event                  | wallet | locked | avail | next sizing
        ------|------------------------|--------|--------|-------|--------------
        0     | start                  | 2000   | 0      | 2000  | —
        1     | trade 1 opens (m=200)  | 2000   | 200    | 1800  | —
        2     | trade 2 signal         | 2000   | 200    | 1800  | 1800×10% = 180
        3     | trade 2 opens          | 2000   | 380    | 1620  | —
        4     | trade 3 signal         | 2000   | 380    | 1620  | 1620×10% = 162
        5     | trade 3 opens          | 2000   | 542    | 1458  | —
        6     | trade 1 TP +$20        | 2020   | 342    | 1678  | —
        7     | trade 4 signal         | 2020   | 342    | 1678  | 1678×10% ≈ 168

    Each new-position decision uses the LIVE availableBalance — Binance's own
    margin accounting, fetched fresh per signal. Manual deposits, withdrawals,
    TP/SL fills, unrealized PnL on still-open positions all flow through
    automatically because we re-query each time.

    The helper returns 0.0 cleanly when fully margined (size→0, guard rejects).
    """
    if client is None:
        return live_balance
    normalized = (source or "total").lower() if isinstance(source, str) else "total"
    if normalized == "total":
        return live_balance
    if normalized == "available":
        return float(client.get_available_margin())
    # Unknown value — defensive fallback
    log.warning(
        f"Unknown sizing_balance_source={source!r}, falling back to 'total'. "
        f"Valid values: 'total', 'available'."
    )
    return live_balance


@dataclass
class SafeCycleResult:
    """Güvenlik bilgilerini de içeren cycle sonucu."""
    symbol: str
    timeframe: str
    current_price: float
    htf_bias: str

    # Safety
    can_trade: bool
    breaker_state: str
    regime: str
    stale_data: bool
    warnings: list

    # Core analysis
    levels: list
    stacked_zones: list
    intent: object
    signals: list
    scenarios: list
    report_md: str
    actions_taken: list


class SafeOrchestrator:
    """
    Safety-first Efloud orchestrator.
    
    Kural: Herhangi bir güvenlik check'i fail ederse trading durur,
    analiz devam eder (watch-only mode).
    """

    def __init__(self, config: dict, state_dir: str = "./state",
                  permission_mgr=None, notification_mgr=None,
                  order_manager=None,
                  *,
                  freshness_check: bool = True,
                  persist: bool = True,
                  trade_journal: Optional[TradeJournal] = None,
                  setup_state_store: Optional["SetupStateStore"] = None,
                  breaker_state_sink: Optional[Callable[[dict], None]] = None):
        """
        permission_mgr: PermissionManager instance (opsiyonel)
        notification_mgr: NotificationManager instance (opsiyonel)
        order_manager: OrderManager instance — borsaya gerçek emir gönderir.
                       None ise sadece lifecycle (paper-trade / test mode).
        freshness_check: False ise validate_kline_freshness çağrılmaz (backtest mode).
        persist: False ise _persist_state disk'e yazmaz (backtest mode).
        trade_journal: TradeJournal instance — pozisyon entry/exit'lerini
                       trade_journal.jsonl'a yazar. None ise no-op
                       (backwards-compat, backtest/unit-test).
        setup_state_store: SMC v2 SetupStateStore instance for pullback-setup
                           state tracking. **Default None → fully inert** (v1
                           behavior unchanged). When passed, the orchestrator
                           advances pending candidates each tick. Used by the
                           PR #S6 feature flag dispatch to opt into v2.
        """
        self.config = config
        self.permission_mgr = permission_mgr
        self.notification_mgr = notification_mgr
        self.order_manager = order_manager
        self.trade_journal = trade_journal
        # SMC v2 SetupStateStore — None when v1 flag is active (inert default).
        # See PR #S2b + spec §4.3 for the advance/trigger/save data flow.
        self.setup_state_store = setup_state_store
        # Convenience reference to BinanceClient for sizing helpers (PR #24).
        # PR #24 introduced `self.client` references in _calc_size paths but
        # forgot to set the attribute in __init__, causing AttributeError on
        # every cycle that reached calc_position_size with a missing position.
        # Falls back to None when order_manager is None (paper-trade / unit tests).
        self.client = order_manager.client if order_manager is not None else None
        self.freshness_check = freshness_check
        self.persist = persist
        # Optional best-effort hook to mirror breaker state to an external store
        # (e.g. the Supabase breaker_state table). None → file StateStore only.
        # Invoked from _persist_state; must never raise into the trading cycle.
        self.breaker_state_sink = breaker_state_sink

        # Core engines
        sc = config["structure"]
        fib = config["fibonacci"]
        self.smc = SMCEngine(
            swing_lb=sc["swing_lookback"],
            ob_seq=sc["ob_sequential"],
            body_mode=sc["body_mode"],
            eq_thr=sc["eq_threshold_pct"] / 100,
            range_lb=sc["range_lookback"],
            ote_lo=fib["ote_lower"],
            ote_hi=fib["ote_upper"],
        )
        self.levels = LevelEngine(stacking_threshold_pct=0.5)
        self.intent = IntentEngine()
        # Per-symbol scenario planners — her sembolün kendi senaryo havuzu
        # Bu sözlük sembol başına ScenarioPlanner instance'ı tutar
        self._planners: dict = {}
        self.lifecycle = PositionLifecycle()
        self.reporter = ReportEngine()

        # Safety layers
        safety = config.get("safety", {})
        self.regime = RegimeDetector(
            adx_trending_threshold=safety.get("adx_trend_threshold", 25),
            adx_ranging_threshold=safety.get("adx_range_threshold", 20),
            volatile_atr_multiplier=safety.get("volatile_atr_mult", 2.5),
            allow_volatile_entries=safety.get("allow_volatile_entries", False),
        )
        self.breaker = CircuitBreaker(
            daily_loss_pct_limit=safety.get("daily_loss_limit_pct", 3.0),
            weekly_drawdown_pct_limit=safety.get("weekly_drawdown_limit_pct", 8.0),
            consecutive_loss_limit=safety.get("consecutive_loss_limit", 3),
            consecutive_loss_pause_minutes=safety.get("consecutive_pause_min", 120),
            starting_balance=safety.get("starting_balance", 10000),
            emergency_balance_threshold=safety.get("emergency_balance_threshold", None),
            reserve_balance=safety.get("reserve_balance", 0.0),
        )
        pause_config = load_pause_config(safety)
        self.pos_guard = PositionGuard(
            max_notional_pct_of_balance=safety.get("max_position_notional_pct", 20),
            max_total_exposure_multiplier=safety.get("max_total_exposure", 5.0),
            max_holding_hours=safety.get("max_holding_hours", 48),
            max_pyramid_adds=safety.get("max_pyramid_adds", 2),
            min_sl_distance_atr=safety.get("min_sl_atr", 0.5),
            max_sl_distance_atr=safety.get("max_sl_atr", 5.0),
            reserve_balance=safety.get("reserve_balance", 0.0),
            max_open_positions=self.config.get("risk", {}).get("max_open_positions", 999),
            reverse_min_profit_pct=safety.get("reverse_min_profit_pct", 0.2),
            pause_config=pause_config,
            hedge_mode=self.config.get("exchange", {}).get("hedge_mode", False),
        )
        orphan_cfg = load_orphan_protection_config(safety)
        self.orphan_protector = OrphanProtector(orphan_cfg, self.client) if self.client is not None else None
        if self.order_manager is not None and getattr(self.order_manager, "orphan_protector", None) is None:
            self.order_manager.orphan_protector = self.orphan_protector
        self.store = StateStore(state_dir)

        # Signal deduplication cache — {(symbol, direction, entry): timestamp}
        # Time-windowed: 1 saat sonra aynı signal yeniden açılabilir
        self._processed_signals: dict = {}

        # Recovery
        self._restore_state()

        # AI Sentiment State Registry Entegrasyonu (SMR Entegrasyon)
        self.sentiment_state = {}
        self.load_ai_sentiment()

        # Machine Learning Regime Auto-Training Pipeline Integration
        self.last_regime_training_time = None

        # Runtime Agent Team (canonical Part A.4 — additive advisory layer).
        # ``enabled: false`` (the default) is a no-op; ``gating: false`` keeps
        # the verdict advisory only. We construct eagerly so the team
        # surface is available to the API endpoints (``/api/ai/agents``,
        # ``/api/ai/post-mortem``) and the post-step 3.5 review call below.
        from engine.agents.team import AgentTeam
        self.agent_team = AgentTeam(
            config.get("agent_team", {}),
            state_dir=state_dir,
        )

        # Bounded executor for async review tasks
        import concurrent.futures
        import threading
        self._review_executor = concurrent.futures.ThreadPoolExecutor(max_workers=2)
        self._in_flight_reviews = set()
        self._in_flight_lock = threading.Lock()

    def _get_planner(self, symbol: str) -> ScenarioPlanner:
        """Sembol başına ScenarioPlanner — senaryolar karışmasın."""
        if symbol not in self._planners:
            self._planners[symbol] = ScenarioPlanner()
        return self._planners[symbol]

    def shutdown(self):
        """Shutdown the executor for background reviews."""
        try:
            self._review_executor.shutdown(wait=False)
        except Exception:
            pass

    def __del__(self):
        self.shutdown()

    def _restore_state(self):
        """Startup'ta önceki state'i yükle."""
        breaker_state = self.store.load("breaker")
        if breaker_state:
            try:
                # Full-fidelity restore: balance/peak/consec AND the OPEN/
                # TRIPPED/HALTED state + reason + timestamps. Restoring only the
                # counters (the old behavior) silently un-halted a HALTED breaker
                # on restart — incident 2026-05-14 (bot resumed trading and left
                # bare positions on Binance).
                self.breaker.restore_from_dict(breaker_state)
                log.info(f"♻️  Restored breaker state: {self.breaker.status.state.value}, "
                         f"balance=${self.breaker.current_balance:.2f}, "
                         f"consec_losses={self.breaker.consecutive_losses}")
            except Exception as e:
                log.warning(f"Could not restore breaker state: {e}")

        # Restore lifecycle positions so duplicate-direction guard is effective
        # after a restart. Skipping this caused the 2026-05-08 stacking bug:
        # bot opened FIL+RENDER, container restarted, lifecycle came up empty,
        # PositionGuard saw no existing positions, signal re-fired, OrderManager
        # placed a fresh SL+TP1+TP2 trio on top of the still-live Binance ones.
        from .lifecycle import Position as LifecyclePosition
        saved_positions = self.store.load("positions")
        if saved_positions:
            restored = []
            for d in saved_positions:
                if not isinstance(d, dict):
                    continue
                # Tolerate compact (legacy) dicts that lack entries/exits — they
                # cannot drive strategy logic but at minimum a synthetic single-Entry
                # restoration is enough for the guard's open-status check.
                if "entries" in d and isinstance(d["entries"], list):
                    try:
                        restored.append(LifecyclePosition.from_full_dict(d))
                        continue
                    except Exception as e:
                        log.warning(f"Failed to restore position from full dict: {e}")
                # Legacy compact dict fallback — synthesize a minimal viable Position
                # so duplicate-direction guard works (size + symbol + direction).
                try:
                    from .lifecycle import Entry as LifecycleEntry
                    size = float(d.get("remaining_size") or 0.0)
                    if size <= 0:
                        continue
                    avg = float(d.get("avg_entry") or 0.0)
                    pos = LifecyclePosition(
                        id=str(d.get("id", "")), symbol=str(d.get("symbol", "")),
                        direction=str(d.get("direction", "LONG")),
                        entries=[LifecycleEntry(
                            id="restored", price=avg, size=size,
                            timestamp=str(d.get("opened_at", "")), reason="initial",
                        )],
                        sl=float(d.get("sl") or 0.0),
                        tp1=float(d.get("tp1") or 0.0),
                        # tp2=None signals single-target mode (SMC v2). The
                        # `... or 0.0` pattern coerces None → 0.0, silently
                        # downgrading single-target Positions on restart. Use
                        # explicit None check so None survives the roundtrip.
                        tp2=float(d["tp2"]) if d.get("tp2") is not None else None,
                        tp1_hit=bool(d.get("tp1_hit", False)),
                        scenario_id=d.get("scenario_id"),
                        opened_at=str(d.get("opened_at", "")),
                    )
                    restored.append(pos)
                except Exception as e:
                    log.warning(f"Failed to restore legacy compact position: {e}")
            self.lifecycle.positions = restored
            log.info(
                f"♻️  Restored {len(restored)} lifecycle position(s): "
                f"{[(p.symbol, p.direction, p.is_open) for p in restored]}"
            )

        # Restore _processed_signals so a mid-cycle restart cannot re-open the
        # same signal twice. Disk format: list of [key_tuple_as_list, timestamp].
        # See SOL double-open incident, 2026-05-08 10:14 → 10:18 UTC.
        saved_sigs = self.store.load("processed_signals")
        if saved_sigs:
            try:
                self._processed_signals = {
                    tuple(entry[0]): float(entry[1])
                    for entry in saved_sigs
                    if isinstance(entry, (list, tuple)) and len(entry) == 2
                }
                log.info(
                    f"♻️  Restored {len(self._processed_signals)} processed signal(s) from disk"
                )
            except Exception as e:
                log.warning(f"Could not restore processed_signals: {e}")
                self._processed_signals = {}

    # A3: the sentiment loop refreshes every ~4h; treat a registry older than
    # that (+15m grace) as stale and revert to NEUTRAL, so an old RISK_ON/OFF
    # cannot keep injecting a ±5 confluence bias after a restart or a stalled loop.
    _SENTIMENT_MAX_AGE_SEC = 4 * 3600 + 900

    def load_ai_sentiment(self):
        """Yapay zeka makro duygu durumunu local registry'den yukler."""
        try:
            registry_path = Path(self.store.dir) / "ai_sentiment_registry.json"
            if registry_path.exists():
                with open(registry_path, encoding="utf-8") as f:
                    state = json.load(f)
                if self._sentiment_is_stale(state):
                    log.warning("AI sentiment registry stale — reverting to NEUTRAL")
                else:
                    self.sentiment_state = state
                    log.info(f"♻️  Loaded AI sentiment state: {state.get('macro_sentiment', 'NEUTRAL')}")
                    return
        except Exception as e:
            log.warning(f"Could not load AI sentiment state: {e}")

        # Fallback default neutral (load failure OR stale registry)
        self.sentiment_state = {
            "macro_sentiment": "NEUTRAL",
            "confidence_score": 1.0,
            "fear_and_greed": 50.0,
            "bitcoin_trend": "NEUTRAL",
            "reasoning": "Fallback default (load failure or stale registry)."
        }

    def _sentiment_is_stale(self, state: dict) -> bool:
        """A3 freshness guard. True when ``last_updated`` is older than the
        refresh window. Lenient on a missing/unparseable timestamp — legacy
        registries load as-is (real ones always stamp ``last_updated``)."""
        ts = state.get("last_updated")
        if not ts:
            return False
        try:
            dt = datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
        except (ValueError, TypeError):
            return False
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        age = (datetime.now(timezone.utc) - dt).total_seconds()
        return age > self._SENTIMENT_MAX_AGE_SEC

    @staticmethod
    def _htf_slope_pct(df_htf, lookback: int = 20) -> float:
        """A4: signed % change of HTF close over the last ``lookback`` bars — the
        RegimeAgent's directional-strength input. The orchestrator previously
        never supplied it, so the agent saw the field as absent (phantom)."""
        try:
            closes = df_htf["close"]
            if len(closes) <= lookback:
                return 0.0
            prior = float(closes.iloc[-1 - lookback])
            if prior == 0:
                return 0.0
            return (float(closes.iloc[-1]) - prior) / prior * 100.0
        except Exception:
            return 0.0

    def _estimate_size_notional_pct(self, balance, entry: float, sl: float) -> float:
        """F1: estimate the position notional as % of balance using the SAME
        sizer the open step uses, so the RiskReviewer agent sees a real notional
        (not a hardcoded 0.0 → its notional-cap rule could never fire). Returns
        0.0 when balance/entry are unavailable."""
        if not balance or float(balance) <= 0 or entry <= 0:
            return 0.0
        try:
            from risk import calc_position_size
            risk_cfg = self.config.get("risk", {})
            lev = self.config.get("exchange", {}).get("leverage", 1)
            max_notional = self.config.get("safety", {}).get("max_position_notional_pct", 3.0)
            size = calc_position_size(
                float(balance), risk_cfg.get("risk_per_trade_pct", 1.0),
                entry, sl, lev, max_notional_pct=max_notional,
            )
            return (size * entry) / float(balance) * 100.0
        except Exception:
            return 0.0

    def _persist_state(self):
        """State'i diske yaz."""
        if not self.persist:
            return
        breaker_dict = self.breaker.to_dict()
        self.store.save("breaker", breaker_dict)
        # Best-effort mirror to the external store (DB). Disk is authoritative;
        # a sink failure must never break persistence or the cycle.
        if self.breaker_state_sink is not None:
            try:
                self.breaker_state_sink(breaker_dict)
            except Exception as e:
                log.warning(f"breaker_state_sink failed (ignored): {e}")
        # Use lossless to_full_dict so a restart can rebuild lifecycle.positions
        # with full entries/exits — the compact to_dict() is for UI snapshots
        # and loses the data that PositionGuard needs to enforce duplicate-direction.
        self.store.save("positions",
                         [p.to_full_dict() for p in self.lifecycle.positions])
        # Tüm sembollerin aktif senaryolarını (symbol bilgisiyle birlikte) kaydet
        all_active = []
        for sym, planner in self._planners.items():
            for s in planner.active_scenarios():
                d = s.to_dict()
                d["symbol"] = sym
                all_active.append(d)
        self.store.save("scenarios", all_active)

        # _processed_signals — JSON-friendly form: list of [key_list, ts].
        # Tuples are not JSON-native; we serialize as lists and reconstruct on load.
        try:
            self.store.save(
                "processed_signals",
                [[list(k), ts] for k, ts in self._processed_signals.items()],
            )
        except Exception as e:
            log.warning(f"Could not persist processed_signals: {e}")

    # ── Trade journal hooks ───────────────────────────────────────────────

    def _journal_record_entry(
        self,
        pos: Position,
        agent_review: Optional[dict] = None,
        signal_entry_price: float = 0.0,
        actual_fill_price: float = 0.0,
        zone_mid: float = 0.0,
        ts_signal: Optional[str] = None,
        ts_fill: Optional[str] = None,
    ) -> None:
        """Record a freshly-opened position to the trade journal with telemetry.

        No-op when self.trade_journal is None (backwards-compat for backtest
        and unit-test paths that don't wire a journal).
        """
        if self.trade_journal is None:
            return

        entries = getattr(pos, "entries", None)
        if entries:
            entry = entries[0]
            entry_timestamp = entry.timestamp
            entry_price = entry.price
            position_size = entry.size
        else:
            entry_timestamp = getattr(pos, "opened_at", None) or datetime.utcnow().isoformat()
            entry_price = getattr(pos, "entry", 0.0)
            position_size = getattr(pos, "size", 0.0)

        if actual_fill_price == 0.0:
            actual_fill_price = entry_price
        if signal_entry_price == 0.0:
            signal_entry_price = entry_price

        # Calculate signed slippage_pct (LONG: (fill-signal)/signal*100, SHORT: (signal-fill)/signal*100; +=adverse)
        slippage_val = 0.0
        if signal_entry_price > 0.0:
            if pos.direction == "LONG":
                slippage_val = ((actual_fill_price - signal_entry_price) / signal_entry_price) * 100.0
            else:
                slippage_val = ((signal_entry_price - actual_fill_price) / signal_entry_price) * 100.0

        # Calculate latency_ms
        latency_val = 0.0
        if ts_signal and ts_fill:
            t_sig = None
            t_fil = None
            try:
                sig_str = ts_signal
                if sig_str.endswith('Z'):
                    sig_str = sig_str[:-1] + '+00:00'
                t_sig = datetime.fromisoformat(sig_str)
            except Exception:
                pass
            try:
                fil_str = ts_fill
                if fil_str.endswith('Z'):
                    fil_str = fil_str[:-1] + '+00:00'
                t_fil = datetime.fromisoformat(fil_str)
            except Exception:
                pass
            if t_sig and t_fil:
                latency_val = (t_fil - t_sig).total_seconds() * 1000.0

        trade_id = getattr(pos, "id", None) or getattr(pos, "order_id", "unknown_id")
        initial_sl = getattr(pos, "initial_sl", None)
        if initial_sl is None:
            initial_sl = getattr(pos, "sl", 0.0)
        scenario_id = getattr(pos, "scenario_id", None)

        snap = TradeSnapshot(
            trade_id=trade_id,
            symbol=pos.symbol,
            direction=pos.direction,
            timeframe="",
            entry_timestamp=entry_timestamp,
            entry_price=entry_price,
            sl_initial=initial_sl,
            tp1_initial=pos.tp1,
            tp2_initial=pos.tp2,
            position_size=position_size,
            htf_bias="",
            intent_score_entry=0,
            intent_label_entry="",
            confluence_score=0,
            scenario_name=scenario_id,
            agent_review=agent_review,
            # Telemetry fields
            signal_entry_price=signal_entry_price,
            actual_fill_price=actual_fill_price,
            slippage_pct=slippage_val,
            zone_mid=zone_mid,
            ts_signal=ts_signal,
            ts_fill=ts_fill,
            latency_ms=latency_val,
        )
        try:
            self.trade_journal.record_entry(snap)
        except Exception as e:
            log.warning(f"trade_journal.record_entry failed for {trade_id}: {e}")

    def _run_agent_review_async(
        self,
        pos: Position,
        confluence: int,
        htf_bias: str,
        df_htf: Optional[pd.DataFrame],
        adx: float,
        rr: float,
        size_notional_pct: float,
    ) -> None:
        """Run the AgentTeam review in a background thread and update the journal."""
        if self.agent_team is None or not self.agent_team.cfg.get("enabled", False):
            return

        # V2 async review: df_htf=None, adx=0.0 -> degraded RegimeAgent context.
        # Note: V2 async reviews use partial context as they are advisory-only.

        try:
            # Defensive attribute access: V1/v2-paper use lifecycle Position, live-v2 uses exchange Position.
            entry_price = getattr(pos, "avg_entry_price", None)
            if entry_price is None:
                entry_price = getattr(pos, "entry", 0.0)

            trade_id = getattr(pos, "id", None) or getattr(pos, "order_id", "unknown_id")

            # Thread-safe in-flight review deduplication
            with self._in_flight_lock:
                if trade_id in self._in_flight_reviews:
                    log.info(f"🤖 [AgentTeam] Review for {pos.symbol} (trade_id={trade_id}) already in flight — skip submit.")
                    return
                self._in_flight_reviews.add(trade_id)

            htf_slope = self._htf_slope_pct(df_htf) if df_htf is not None else 0.0

            ctx = {
                "symbol": pos.symbol,
                "direction": pos.direction,
                "entry": float(entry_price),
                "sl": float(pos.sl),
                "tp1": float(pos.tp1),
                "confluence": int(confluence),
                "htf_bias": htf_bias,
                "htf_slope_pct": htf_slope,
                "adx": float(adx),
                "rr": float(rr),
                "size_notional_pct": size_notional_pct,
            }

            def task():
                try:
                    log.info(f"🤖 [AgentTeam] Starting async review for {pos.symbol} {pos.direction} (trade_id={trade_id})...")
                    verdict = self.agent_team.review_trade(ctx)
                    log.info(
                        f"🤖 [AgentTeam] Async review finished for {pos.symbol}: "
                        f"team_verdict={verdict.get('team_verdict')} score={verdict.get('score', 0.0):.2f}"
                    )
                    if self.trade_journal:
                        self.trade_journal.update_agent_review(trade_id, verdict)
                except Exception as e:
                    log.warning(f"Error in async AgentTeam review execution: {e!r}")
                finally:
                    with self._in_flight_lock:
                        self._in_flight_reviews.discard(trade_id)

            self._review_executor.submit(task)
        except Exception as e:
            log.warning(f"Error submitting async AgentTeam review: {e!r}")


    def _journal_record_exit(self, pos: Position, exit_price: float,
                              reason: str) -> None:
        """Record a closed position to the trade journal.

        Must be called AFTER lifecycle.close_position has appended the
        Exit — realized_pnl is read from pos.realized_pnl (sum of exits).
        No-op when self.trade_journal is None. bars_held is 0 in this PR;
        per-bar bar-count tracking is a follow-up. MAE/MFE pass through
        from pos.mae_pct / pos.mfe_pct populated by update_excursion()
        each cycle.
        """
        if self.trade_journal is None:
            return
        try:
            self.trade_journal.record_exit(
                trade_id=pos.id,
                exit_price=exit_price,
                exit_reason=reason,
                realized_pnl=pos.realized_pnl,
                bars_held=0,
                mfe_pct=pos.mfe_pct,
                mae_pct=pos.mae_pct,
            )
        except Exception as e:
            log.warning(f"trade_journal.record_exit failed for {pos.id}: {e}")

    def _live_opposite_position_exists(self, symbol: str, direction: str) -> bool:
        """True if a position for (symbol, direction) is live on the exchange NOW.

        Guards the reverse path against a lifecycle-vs-order_manager desync — a
        position the order_manager no longer tracks but is still open on Binance.
        Fails SAFE: on any fetch error, assume it MAY be live (return True) so the
        caller aborts the reverse rather than risk an uncontrolled auto-flip.
        """
        client = getattr(self.order_manager, "client", None)
        if client is None:
            return False  # dry-run / no exchange client → original behavior
        try:
            from exchange import _strip_contract_suffix
            for p in (client.get_open_positions() or []):
                if (_strip_contract_suffix(p.get("symbol", "")) == symbol
                        and str(p.get("side", "")).upper() == direction
                        and float(p.get("contracts", 0) or 0) > 0):
                    return True
            return False
        except Exception as e:
            log.warning(
                f"[{symbol}] reverse desync check failed: {e} — assuming position "
                f"may be live (aborting reverse to be safe)"
            )
            return True

    def _handle_reverse(self, opposite_pos, symbol: str, current_price: float) -> bool:
        """Close the opposite-direction position so a reverse-direction signal
        can open cleanly afterwards.

        Caller invariant: reconcile and run_cycle must not interleave —
        the bot runs a single event loop, so this _handle_reverse executes
        atomically against reconcile()'s self.positions mutation.

        Returns True if the close path completed (caller may proceed to open
        the new direction). False means exchange close failed — caller must
        abort the reverse; _fallback_close already cancels the opposite's
        TP/SL orders so no orphan SL/TP remains on Binance even when the
        close itself raises mid-flight (the cancel block runs before the
        market close call).
        """
        log.info(
            f"🔄 [{symbol}] REVERSE: closing {opposite_pos.direction} "
            f"{opposite_pos.id} @ {current_price:.4f}"
        )
        exchange_close_ran = False
        if self.order_manager is not None:
            exchange_pos = next(
                (p for p in self.order_manager.positions
                 if p.symbol == symbol and p.direction == opposite_pos.direction),
                None,
            )
            if exchange_pos is not None:
                try:
                    self.order_manager._fallback_close(
                        exchange_pos, current_price, "REVERSE"
                    )
                    exchange_close_ran = True
                except Exception as e:
                    log.error(
                        f"⛔ [{symbol}] REVERSE exchange close failed: {e}",
                        exc_info=True,
                    )
                    if self.notification_mgr is not None:
                        try:
                            self.notification_mgr.alert(
                                "CRITICAL",
                                f"REVERSE close failed for {symbol}: {e}. "
                                f"Manual intervention required.",
                            )
                        except Exception:
                            pass
                    return False
            elif self._live_opposite_position_exists(symbol, opposite_pos.direction):
                # order_manager does not track this position, but it IS still live
                # on the exchange (lifecycle-vs-order_manager desync: restart with
                # empty order_manager state, manual injection, partial reconcile).
                # Proceeding would open the reverse side and — under hedge-off /
                # ISOLATED — trigger an uncontrolled Binance auto-flip of the live
                # position with no bot SL/TP, leaving orphan algo orders. Abort the
                # reverse instead of dropping logical state on a live position.
                log.error(
                    f"⛔ [{symbol}] REVERSE aborted: {opposite_pos.direction} position "
                    f"is live on the exchange but untracked by order_manager (desync) "
                    f"— refusing to auto-flip."
                )
                if self.notification_mgr is not None:
                    try:
                        self.notification_mgr.alert(
                            "CRITICAL",
                            f"REVERSE aborted for {symbol}: live {opposite_pos.direction} "
                            f"position untracked by order_manager (desync). Manual "
                            f"intervention required.",
                        )
                    except Exception:
                        pass
                return False

        self.lifecycle.close_position(opposite_pos, current_price, "REVERSE")
        # Journal-write avoidance: when exchange_close_ran is True, the
        # OrderManager path already wrote a TradeSnapshot via its own
        # _journal_record_close (keyed on exchange_pos.order_id). The
        # orchestrator-side _journal_record_exit would key on opposite_pos.id
        # — a DIFFERENT trade_id, so the rows would NOT collide, but they
        # would describe the same REVERSE event twice from two perspectives.
        # Skip the orchestrator write here to keep one row per close event;
        # only fall back when no exchange path ran (dry-run or unmatched
        # exchange-side position).
        if not exchange_close_ran:
            self._journal_record_exit(
                opposite_pos, exit_price=current_price, reason="REVERSE"
            )
        return True

    def _force_close_max_hold(self, pos, current_price: float) -> bool:
        """Force-close a position past max holding time, EXCHANGE leg first.

        A logical-only close (the old STEP-5 behavior) left the real Binance
        position open and invisible to the duplicate-direction guard → same-symbol
        same-direction STACKING, plus phantom breaker PnL recorded at a price the
        position never exited at. Mirrors _handle_reverse: market-close + cancel
        siblings on the exchange first; on exchange-close failure KEEP the logical
        position (return False) so we never drop tracking while it is still live.

        Returns True if the logical close ran, False if the exchange close failed
        and the logical close was skipped.
        """
        exchange_close_ran = False
        if self.order_manager is not None:
            exchange_pos = next(
                (p for p in self.order_manager.positions
                 if p.symbol == pos.symbol and p.direction == pos.direction),
                None,
            )
            if exchange_pos is not None:
                try:
                    self.order_manager._fallback_close(
                        exchange_pos, current_price, "MAX_HOLD"
                    )
                    exchange_close_ran = True
                except Exception as e:
                    log.error(
                        f"⛔ [{pos.symbol}] MAX_HOLD exchange close failed: {e} — "
                        f"keeping logical position (still live on exchange)",
                        exc_info=True,
                    )
                    if self.notification_mgr is not None:
                        try:
                            self.notification_mgr.alert(
                                "CRITICAL",
                                f"MAX_HOLD close failed for {pos.symbol}: {e}. "
                                f"Manual intervention required.",
                            )
                        except Exception:
                            pass
                    return False

        self.lifecycle.close_position(pos, current_price, "MANUAL")
        # When the exchange path ran, OrderManager._fallback_close already wrote a
        # close TradeSnapshot; avoid a duplicate orchestrator-side row (mirror
        # _handle_reverse).
        if not exchange_close_ran:
            self._journal_record_exit(pos, exit_price=current_price, reason="MANUAL")
        return True

    def check_and_train_regime_model(self, symbol: str, df: pd.DataFrame):
        """Her 24 saatte bir, BTC/USDT veya ETH/USDT üzerinden ML modelini otomatik eğitir."""
        import datetime
        now_utc = datetime.datetime.now(datetime.timezone.utc)
        if self.last_regime_training_time is None or (now_utc - self.last_regime_training_time).total_seconds() > 86400:
            if symbol in ["BTC/USDT", "ETH/USDT"] and len(df) >= 100:
                try:
                    log.info(f"Starting Daily Automated Regime ML model retraining on {symbol}...")
                    from engine.regimes.train import run_auto_train
                    res = run_auto_train(df, weights_filename=str(self.regime.weights_path))
                    if res["success"]:
                        log.info(f"Regime ML model retrained successfully! Samples: {res['samples']}, Loss: {res['final_loss']:.4f}")
                        self.last_regime_training_time = now_utc
                        # Reload weights in detector
                        self.regime._load_ml_model()
                    else:
                        log.warning(f"Regime ML auto-train skipped: {res.get('reason')}")
                except Exception as e:
                    log.error(f"Error during automated regime ML training: {e}")

    def run_cycle(
        self,
        symbol: str,
        df_htf: pd.DataFrame,
        df_mtf: pd.DataFrame,
        df_entry: pd.DataFrame,
        df_daily: Optional[pd.DataFrame] = None,
        balance: Optional[float] = None,
        now: Optional[datetime] = None,
    ) -> SafeCycleResult:
        """Safety check'li tam analiz cycle'ı."""
        # Yapay zeka makro duygu durumunu en güncel haliyle yükle
        self.load_ai_sentiment()

        # Arka planda ML model eğitim kontrolünü yap
        self.check_and_train_regime_model(symbol, df_entry)

        warnings = []
        actions = []
        tf = self.config["timeframes"]
        risk_cfg = self.config["risk"]

        # ═══ STEP 0: Data Validation ═══
        stale = False
        for name, df, tfname in [
            ("HTF", df_htf, tf["htf"]),
            ("MTF", df_mtf, tf["mtf"]),
            ("Entry", df_entry, tf["entry"]),
        ]:
            try:
                validate_kline_integrity(df)
                if self.freshness_check:
                    validate_kline_freshness(df, tfname, tolerance_factor=2.5)
            except (StaleDataError, ValueError) as e:
                warnings.append(f"{name} data issue: {e}")
                log.warning(f"⚠️  {name} ({tfname}): {e}")
                stale = True

        if stale:
            log.warning("📛 Stale/invalid data detected — analysis only, NO TRADING")

        current_price = float(df_entry["close"].iloc[-1])
        bar_high = float(df_entry["high"].iloc[-1])
        bar_low = float(df_entry["low"].iloc[-1])

        # SMC v2 setup state advance — opt-in, inert when store is None.
        # Must run BEFORE breaker check so EXPIRE transitions get recorded
        # even on no-trade ticks (operator observability).
        if self.setup_state_store is not None:
            current_bar_ts = int(df_entry.index[-1].timestamp() * 1000)
            self._advance_setup_state_tick(
                symbol=symbol,
                current_price=current_price,
                current_bar_ts=current_bar_ts,
                df_15m=df_entry,
            )

            # SMC v2 trigger phase: detect new CHoCH → emit SetupCandidates.
            # Per spec §4.3 step 3. Runs AFTER advance (existing candidates
            # progress first) and BEFORE save (new candidates persisted).
            #
            # Inputs derived from SMC engine analyze() result and ltf.structure().
            # For PR #S3c-1 we compute them inline here. Future PR may
            # refactor to share with the v1 signals path.
            htf_analysis = self.smc.analyze(df_htf)
            ltf_swings_h, ltf_swings_l = self.smc.swings(df_entry)
            ltf_brks = self.smc.structure(df_entry, ltf_swings_h, ltf_swings_l)

            # Build htf_bars from df_htf rows (ordinal axis for swing_anchor).
            # HtfBar dataclass hoisted to engine.smc_v2.triggers to keep
            # run_cycle hot-path clean (avoid re-defining the class each tick).
            from engine.smc_v2.triggers import HtfBar

            htf_bars = [
                HtfBar(ordinal=i, high=float(row["high"]), low=float(row["low"]))
                for i, (_, row) in enumerate(df_htf.iterrows())
            ]

            # Recency cutoff: only consider LTF breaks in last N bars
            recency = self.config.get("risk", {}).get("recency_bars", 40)
            ltf_trigger_idx_min = max(0, len(df_entry) - 1 - recency)

            # OTE band: from htf_analysis if available, else degenerate
            ote_obj = htf_analysis.get("ote")
            if ote_obj is not None:
                ote_low, ote_high = min(ote_obj.bot, ote_obj.top), max(ote_obj.bot, ote_obj.top)
            else:
                ote_low, ote_high = 0.0, 0.0

            self._emit_setup_candidates(
                symbol=symbol,
                htf_bias=htf_analysis.get("trend", "UNDEF"),
                ltf_structure_breaks=ltf_brks,
                htf_swings={
                    "swing_highs": htf_analysis.get("swing_highs", []),
                    "swing_lows": htf_analysis.get("swing_lows", []),
                },
                htf_bars=htf_bars,
                htf_fvgs=htf_analysis.get("active_fvgs", []),
                ote_band=(ote_low, ote_high),
                ltf_trigger_idx_min=ltf_trigger_idx_min,
            )

        # ═══ STEP 0: Per-bar MAE/MFE tracking ═══
        # Update excursion for every open position in this symbol before any
        # downstream decision (breaker, regime, close, open). MAE/MFE flow
        # into TradeJournal at close-time, enabling Phase 0 to separate H2
        # (SL too tight: MAE ≤ sl_distance) from H3 (price ran far: MAE >>).
        for _pos in self.lifecycle.open_positions(symbol):
            _pos.update_excursion(bar_high, bar_low)

        # ═══ STEP 1: Circuit Breaker ═══
        # Sync breaker's current_balance with live exchange equity BEFORE check.
        # Without this, breaker drifts (record_trade is realized-only, ignores
        # unrealized PnL and external wallet changes like manual transfers).
        if balance is not None:
            self.breaker.sync_balance(balance)
        # `now` is sim-time in backtest, None in live (uses wall-clock).
        breaker_status = self.breaker.check(now=now)
        if not breaker_status.can_trade:
            log.warning(f"🚨 Breaker {breaker_status.state.value}: {breaker_status.reason}")
            warnings.append(f"Breaker {breaker_status.state.value}: {breaker_status.reason}")

        # ═══ STEP 2: Regime Detection ═══
        regime_analysis = self.regime.analyze(df_entry, df_htf)
        log.info(f"📊 Regime: {regime_analysis.regime} ({regime_analysis.confidence}%) | "
                 f"ADX={regime_analysis.adx:.1f} BBW={regime_analysis.bb_width:.2f} "
                 f"ATR={regime_analysis.atr_ratio:.1f}x")

        # Volatilite per-symbol regime ile filtreleniyor (regime=VOLATILE → can_open_new_position=False).
        # Global breaker volatilite-trip'lemiyor: tek sembolün ATR spike'ı tüm portföyü kilitlememeli.

        # Aşırı volatilite — mevcut pozisyonlarda stop sıkılaştır
        if regime_analysis.should_tighten_stops:
            for pos in self.lifecycle.open_positions(symbol):
                if not pos.sl_moved_to_be and pos.tp1_hit:
                    # SL'yi daha agresif yere çek
                    old_sl = pos.sl
                    pos.sl = pos.avg_entry_price * (1.005 if pos.direction == "LONG" else 0.995)
                    log.info(f"🔒 Tightened SL for {pos.id}: {old_sl:.2f} → {pos.sl:.2f} "
                             f"(regime={regime_analysis.regime})")
                    actions.append(f"Tightened SL on {pos.id}")

        # ═══ STEP 3: Level & SMC analysis (her zaman yap, watch-only için de) ═══
        all_levels = self.levels.extract_all(
            df_daily=df_daily if df_daily is not None else df_htf,
            df_current=df_entry,
            range_lookback=self.config["structure"]["range_lookback"],
        )
        stacked = self.levels.detect_stacked_zones(all_levels)

        htf_analysis = self.smc.analyze(df_htf)
        htf_bias = htf_analysis["trend"]
        rng = htf_analysis["range"]

        intent_score = self.intent.analyze(df_entry)

        signals = generate_signals(
            self.smc, df_htf, df_mtf, df_entry,
            min_confluence=risk_cfg["min_confluence"],
            min_rr=risk_cfg["min_rr"],
            fib_ext=self.config["fibonacci"]["ext_tp2"],
            recency_bars=risk_cfg.get("recency_bars", 40),
            df_daily=df_daily,
            daily_filter_strict=risk_cfg.get("daily_filter_strict", False),
            symbol=symbol,
            symbol_confluence_overrides=risk_cfg.get("symbol_confluence_overrides"),
            levels=all_levels,
            ai_sentiment=self.sentiment_state,
        )

        # ═══ STEP 4: Scenario Planning (per-symbol) ═══
        planner = self._get_planner(symbol)
        if not planner.active_scenarios() and htf_bias != "UNDEF":
            above, below = self.levels.get_nearest_levels(current_price, all_levels)
            planner.plan_three_scenarios(
                current_price=current_price,
                htf_bias=htf_bias,
                nearest_support=below[0].price if below else current_price * 0.98,
                nearest_resistance=above[0].price if above else current_price * 1.02,
                stacked_zones=stacked,
                range_low=rng.lo, range_high=rng.hi,
            )
            actions.append(f"[{symbol}] Planned {len(planner.scenarios)} scenarios")

        triggered = planner.check_triggers(current_price)
        planner.invalidate_scenarios(current_price)

        # ═══ STEP 5: Position Lifecycle Updates ═══
        price_map = {symbol: current_price}

        def weakness_check(pos):
            bias = "BULL" if pos.direction == "LONG" else "BEAR"
            return self.intent.check_weakness(df_entry, bias)

        # Trade öncesi mevcut pozisyonları güncelle (SL/TP/weakness)
        prev_open_count = len(self.lifecycle.open_positions())
        self.lifecycle.on_tick(price_map, intent_checker=weakness_check)
        new_open_count = len(self.lifecycle.open_positions())

        # Kapanan trade'ler varsa breaker'a bildir
        for p in self.lifecycle.positions:
            if not p.is_open and p.closed_at and \
               not getattr(p, "_reported_to_breaker", False):
                self.breaker.record_trade(p.realized_pnl)
                p._reported_to_breaker = True
                actions.append(f"Recorded PnL ${p.realized_pnl:.2f} to breaker")

        # Orphan hedge cleanup
        orphans = cleanup_orphan_hedges(self.lifecycle.positions, log)
        for o in orphans:
            warnings.append(f"Orphan hedge {o.id} — consider closing")

        # Max holding time check
        for pos in self.lifecycle.open_positions(symbol):
            hold_check = self.pos_guard.check_holding_time(pos)
            if not hold_check.allowed:
                log.warning(f"⏰ Force-closing {pos.id}: {hold_check.reason}")
                # Close the EXCHANGE leg before the logical one — a logical-only
                # close leaves the live Binance position untracked → stacking +
                # phantom PnL. Keep logical state if the exchange close fails.
                if self._force_close_max_hold(pos, current_price):
                    actions.append(f"Force-closed {pos.id} (max holding time)")
                else:
                    warnings.append(
                        f"⚠️ MAX_HOLD exchange close failed for {pos.symbol} — "
                        f"position still live, manual intervention required"
                    )
            warnings.extend(hold_check.warnings)

        # ═══ STEP 6: Yeni Trade Decision ═══
        # C4: a failed balance fetch on a LIVE cycle must NOT fabricate a $10k
        # balance and size new entries against it (see actual_balance fallback
        # below). Treat unavailable balance like stale data → existing positions
        # were already managed in STEP 5, but open NO new entries this cycle.
        # Dry-run/backtest pass an explicit balance, so None there is exempt.
        balance_unavailable = (
            balance is None and not self.config["operation"].get("dry_run", False)
        )
        if balance_unavailable:
            warnings.append(
                "Balance unavailable (fetch failed) — skipping new entries this cycle"
            )
        can_trade = (
            breaker_status.can_trade
            and not stale
            and not balance_unavailable
            and regime_analysis.can_open_new_position
            and not self.config["operation"].get("watch_only", False)
        )

        if not can_trade:
            reasons = []
            if not breaker_status.can_trade:
                reasons.append(f"breaker={breaker_status.state.value}")
            if stale:
                reasons.append("stale_data")
            if not regime_analysis.can_open_new_position:
                reasons.append(f"regime={regime_analysis.regime}")
            log.info(f"🚫 Trading disabled: {', '.join(reasons)}")

        elif signals:
            latest = signals[-1]
            # === Runtime Agent Team pre-review (canonical A4) ===
            _agent_veto = False
            if self.agent_team and self.agent_team.cfg.get("gating", False):
                # Run review trade SYNCHRONOUSLY pre-trade and veto on "REJECT"
                rr = float(latest.rr1) if latest.rr1 else 0.0
                actual_balance = balance if balance is not None else 10000.0
                size_notional_pct = self._estimate_size_notional_pct(actual_balance, latest.entry, latest.sl)
                htf_slope = self._htf_slope_pct(df_htf) if df_htf is not None else 0.0
                ctx = {
                    "symbol": symbol,
                    "direction": latest.direction,
                    "entry": float(latest.entry),
                    "sl": float(latest.sl),
                    "tp1": float(latest.tp1),
                    "confluence": int(latest.confluence),
                    "htf_bias": htf_bias,
                    "htf_slope_pct": htf_slope,
                    "adx": float(regime_analysis.adx) if regime_analysis else 0.0,
                    "rr": float(rr),
                    "size_notional_pct": size_notional_pct,
                }
                try:
                    review = self.agent_team.review_trade(ctx)
                    latest.meta["agent_review"] = review
                    latest.meta["risk_review_was_notional_blind"] = review.get("risk_review_was_notional_blind", False)
                    if review.get("team_verdict") == "REJECT":
                        _agent_veto = True
                        log.warning(f"🚫 [AgentTeam] Signal vetoed by agent team verdict REJECT")
                except Exception as e:
                    log.warning(f"Error in synchronous AgentTeam gating review: {e!r}")

            if _agent_veto:
                actions.append(f"[{symbol}] Vetoed by agent team")
            else:

                # Time-windowed dedup: aynı signal 1 saat içinde iki kez açılmasın
                # Ama 1 saat sonra aynı sinyal yine üretilirse (ikinci CHoCH) açabilir
                import time as _time
                now_ts = _time.time()
                sig_key = (symbol, latest.direction, round(latest.entry, 2))

                # Eski kayıtları temizle (>1 saat)
                self._processed_signals = {
                    k: ts for k, ts in self._processed_signals.items()
                    if now_ts - ts < 3600
                } if isinstance(self._processed_signals, dict) else {}

                if sig_key in self._processed_signals:
                    age_min = (now_ts - self._processed_signals[sig_key]) / 60
                    log.info(f"🔁 [{symbol}] Signal already processed {age_min:.0f}min ago — skipping")
                else:
                    self._processed_signals[sig_key] = now_ts
                    # Persist dedup cache immediately so a mid-cycle restart can't
                    # re-open the same signal (SOL double-open, 2026-05-08).
                    self._persist_state()

                    # Sembol tradeable mi? (read-only ise notification gönder, trade etme)
                    is_tradeable = True
                    if self.permission_mgr is not None:
                        is_tradeable = self.permission_mgr.is_tradeable(symbol)

                    if not is_tradeable:
                        # Read-only sembol → manuel trader'a bildir
                        if self.notification_mgr:
                            self.notification_mgr.signal_readonly(
                                symbol=symbol, direction=latest.direction,
                                entry=latest.entry, sl=latest.sl,
                                tp1=latest.tp1, tp2=latest.tp2,
                                confluence=latest.confluence,
                                reasons=latest.reasons,
                            )
                        actions.append(f"[READONLY] Signal {latest.direction} @ {latest.entry:.2f} (notify only)")

                    else:
                        # Tradeable → normal akış: pozisyon aç
                        actual_balance = balance if balance is not None else 10000.0

                        # Opt-in: reverse-from-risk position sizing (cherry-picked v2.2.0)
                        if risk_cfg.get("position_size_calculation") == "reverse_from_risk":
                            from engine.risk.custom_calculator import CustomRiskCalculator
                            calc = CustomRiskCalculator(
                                max_loss_usdt=risk_cfg["max_loss_per_trade_usdt"],
                                leverage=self.config["exchange"].get("leverage", 1),
                                target_stop_pct=risk_cfg["target_stop_distance_pct"] / 100.0,
                            )
                            # calculate_position_size returns MARGIN; convert to
                            # notional (× leverage) before /entry, else the position
                            # is leverage-x too small (5x under-risked at lev=5).
                            size = calc.calculate_contract_size(actual_balance, latest.entry)
                        else:
                            from risk import calc_position_size
                            max_notional = self.config["safety"].get("max_position_notional_pct", 3.0)
                            # Choose sizing balance: 'total' (default) or 'available'
                            sizing_source = risk_cfg.get("sizing_balance_source", "total")
                            sizing_bal = _sizing_balance(
                                self.client, sizing_source, actual_balance
                            )
                            size = calc_position_size(
                                sizing_bal, risk_cfg["risk_per_trade_pct"],
                                latest.entry, latest.sl,
                                self.config["exchange"].get("leverage", 1),
                                max_notional_pct=max_notional,
                            )
                            if sizing_source == "available" and sizing_bal < actual_balance:
                                log.info(
                                    f"sizing: source=available balance=${sizing_bal:.2f} "
                                    f"(vs total=${actual_balance:.2f}, "
                                    f"delta=${actual_balance-sizing_bal:.2f} locked)"
                                )

                        atr = self.intent._atr(df_entry, 14)
                        guard_check = self.pos_guard.can_open_position(
                            balance=actual_balance,
                            entry=latest.entry, size=size, sl=latest.sl, atr=atr,
                            direction=latest.direction, symbol=symbol,
                            existing_positions=self.lifecycle.positions,
                            leverage=self.config["exchange"].get("leverage", 1),
                        )

                        # Reverse-on-profit branch: an opposite-direction position
                        # blocks can_open_position. Re-evaluate with the live price
                        # — if currently profitable beyond the buffer threshold,
                        # close the existing side and let the open flow continue.
                        reversed_from: Optional[str] = None
                        if (not guard_check.allowed
                            and guard_check.reason.startswith("OPPOSITE_DIRECTION_EXISTS")):
                            opposite = next(
                                (p for p in self.lifecycle.positions
                                 if p.is_open and p.symbol == symbol
                                 and p.direction != latest.direction
                                 and p.scenario_id is None),
                                None,
                            )
                            if opposite is None:
                                log.warning(
                                    f"[{symbol}] OPPOSITE_DIRECTION_EXISTS but no "
                                    f"matching open position — race; rejecting."
                                )
                            else:
                                reverse_check = self.pos_guard.can_reverse_position(
                                    opposite, current_price
                                )
                                if not reverse_check.allowed:
                                    log.info(
                                        f"🚫 [{symbol}] Reverse rejected: "
                                        f"{reverse_check.reason}"
                                    )
                                    warnings.append(
                                        f"Reverse blocked: {reverse_check.reason}"
                                    )
                                else:
                                    log.info(
                                        f"🔄 [{symbol}] Reverse approved: "
                                        f"{reverse_check.reason}"
                                    )
                                    if self._handle_reverse(opposite, symbol, current_price):
                                        reversed_from = opposite.direction
                                        actions.append(
                                            f"Reversed {opposite.direction} → "
                                            f"{latest.direction} ({reverse_check.reason})"
                                        )
                                        # Re-evaluate the guard now that opposite is gone.
                                        guard_check = self.pos_guard.can_open_position(
                                            balance=actual_balance,
                                            entry=latest.entry, size=size, sl=latest.sl,
                                            atr=atr,
                                            direction=latest.direction, symbol=symbol,
                                            existing_positions=self.lifecycle.positions,
                                            leverage=self.config["exchange"].get("leverage", 1),
                                        )
                                    else:
                                        warnings.append(
                                            f"Reverse close failed for {symbol} — "
                                            f"open aborted"
                                        )
                                        # Drop the dedup entry so the next cycle can retry.
                                        # Persist immediately: a SIGKILL between here and
                                        # the cycle's natural _persist_state would leave
                                        # the cache still claiming this signal was processed,
                                        # blocking the retry on restart.
                                        self._processed_signals.pop(sig_key, None)
                                        self._persist_state()

                        if not guard_check.allowed:
                            log.warning(f"🚫 Position blocked: {guard_check.reason}")
                            warnings.append(f"Signal rejected: {guard_check.reason}")
                        else:
                            pause_signal = type("PauseSignal", (), {
                                "symbol": symbol,
                                "side": latest.direction.lower(),
                            })()
                            pause_decision = self.pos_guard.is_new_entry_allowed(pause_signal)
                            if not pause_decision.allowed:
                                log.warning(
                                    f"🚫 Position blocked: {pause_decision.reason} "
                                    f"source={pause_decision.source}"
                                )
                                warnings.append(f"Signal rejected: {pause_decision.reason}")
                                # Pause is operator-driven; surface it in actions/telemetry.
                                # Routine risk-math rejections stay warnings-only.
                                actions.append(f"Signal rejected: {pause_decision.reason}")
                            else:
                                # ── 0) Trace ID for log correlation across orchestrator → DB ──
                                trace_id = new_trace_id()
                                set_trace_id(trace_id)
                                log.info(
                                    "signal_promoted_to_trade",
                                    extra={"symbol": symbol, "direction": latest.direction,
                                           "confluence": latest.confluence},
                                )

                                # ── 1) Borsaya gerçek emir gönder (varsa) ──
                                exchange_ok = True
                                if self.order_manager is not None:
                                    try:
                                        # Phase 3.2: build confluence_details for DB warehouse
                                        _conf_details = {
                                            "score": latest.confluence,
                                            "reasons": getattr(latest, "reasons", []),
                                            "htf_bias": htf_bias,
                                            "regime": regime_analysis.regime,
                                            "adx": float(regime_analysis.adx),
                                            "atr_ratio": float(regime_analysis.atr_ratio),
                                        } if latest is not None else None
                                        exchange_pos = self.order_manager.open_position(
                                            symbol, latest.direction, size,
                                            latest.entry, latest.sl, latest.tp1, latest.tp2,
                                            trace_id=trace_id,
                                            atr_value=float(atr) if atr is not None else None,
                                            confluence_details=_conf_details,
                                        )
                                    except Exception as e:
                                        log.error(f"⛔ [{symbol}] Exchange order failed: {e}", exc_info=True)
                                        exchange_pos = None

                                    if exchange_pos is None:
                                        log.warning(
                                            f"🚫 [{symbol}] Exchange order failed — "
                                            f"local position NOT opened (no logical state mismatch)"
                                        )
                                        if reversed_from is not None:
                                            # Reverse close succeeded but open failed —
                                            # the symbol is intentionally flat. Trader
                                            # must know they're sitting on no exposure
                                            # so they can decide whether to retry manually.
                                            flat_msg = (
                                                f"Reverse close succeeded but open failed "
                                                f"for {symbol} — symbol flat, awaiting next signal"
                                            )
                                            warnings.append(flat_msg)
                                            if self.notification_mgr is not None:
                                                try:
                                                    self.notification_mgr.alert("WARNING", flat_msg)
                                                except Exception:
                                                    pass
                                        else:
                                            warnings.append(
                                                f"Order failed for {symbol}: exchange rejected"
                                            )
                                        exchange_ok = False

                                # ── 2) Logical state'e ekle (sadece exchange başarılıysa) ──
                                if exchange_ok:
                                    pos = self.lifecycle.open_position(
                                        symbol, latest.direction, latest.entry, size,
                                        latest.sl, latest.tp1, latest.tp2
                                    )
                                    # Canonical A7: pass the AgentTeam verdict
                                    # (attached to the signal in STEP 3.5) so
                                    # the journal row carries the team's call.
                                    self._journal_record_entry(
                                        pos,
                                        agent_review=(latest.meta.get("agent_review")
                                                      if isinstance(latest.meta, dict)
                                                      else None),
                                        signal_entry_price=latest.entry,
                                        actual_fill_price=getattr(exchange_pos, "entry", latest.entry) if exchange_pos else latest.entry,
                                        zone_mid=latest.entry,
                                        ts_signal=getattr(latest, "timestamp", None) or getattr(latest, "ts", None),
                                        ts_fill=getattr(exchange_pos, "opened_at", None) or pos.opened_at,
                                    )
                                    self._run_agent_review_async(
                                        pos=pos,
                                        confluence=latest.confluence,
                                        htf_bias=htf_bias,
                                        df_htf=df_htf,
                                        adx=float(regime_analysis.adx) if regime_analysis else 0.0,
                                        rr=float(latest.rr1) if latest.rr1 else 0.0,
                                        size_notional_pct=self._estimate_size_notional_pct(actual_balance, latest.entry, latest.sl),
                                    )
                                    log.info(f"✅ [{symbol}] Opened {latest.direction} @ {latest.entry:.4f} "
                                             f"size={size:.6f} SL={latest.sl:.4f} TP1={latest.tp1:.4f} "
                                             f"TP2={latest.tp2:.4f} Conf={latest.confluence}")
                                    if self.notification_mgr:
                                        self.notification_mgr.position_opened(
                                            symbol, latest.direction, latest.entry,
                                            size, latest.sl, latest.tp1, latest.confluence
                                        )
                                    actions.append(f"Opened {latest.direction} @ {latest.entry:.2f} "
                                                   f"(size={size:.4f})")
                                    warnings.extend(guard_check.warnings)

        # ═══ STEP 7: Scenario-based Piramit ═══
        if can_trade:
            for scen in triggered:
                if scen.kind != "invalidation":
                    continue
                existing = self.lifecycle.same_direction_open(symbol, scen.direction)
                if not existing:
                    continue

                bias_check = "BULL" if scen.direction == "LONG" else "BEAR"
                if not self.intent.check_confirmation(df_entry, bias_check, min_score=50):
                    continue

                from risk import calc_position_size
                balance_now = balance if balance else 10000.0
                mid = (scen.entry_zone_top + scen.entry_zone_bottom) / 2
                max_notional = self.config["safety"].get("max_position_notional_pct", 3.0)
                # Choose sizing balance: 'total' (default) or 'available'
                sizing_source = risk_cfg.get("sizing_balance_source", "total")
                sizing_bal = _sizing_balance(
                    self.client, sizing_source, balance_now
                )
                add_size = calc_position_size(
                    sizing_bal, risk_cfg["risk_per_trade_pct"] * 0.5,
                    mid, scen.sl, self.config["exchange"].get("leverage", 1),
                    max_notional_pct=max_notional,
                )

                # Add guard first so pause_new_entries does not mask real rejection reasons.
                add_check = self.pos_guard.can_add_to_position(existing, add_size, current_price)
                if not add_check.allowed:
                    warnings.append(f"Add rejected: {add_check.reason}")
                    continue

                pause_pyramid_decision = self.pos_guard.is_new_entry_allowed(
                    type("PauseSignal", (), {
                        "symbol": symbol,
                        "side": existing.direction.lower(),
                        "is_pyramid": True,
                    })()
                )
                if not pause_pyramid_decision.allowed:
                    warnings.append(f"Add rejected: {pause_pyramid_decision.reason}")
                    continue

                self.lifecycle.add_to_position(existing, mid, add_size, "scenario_add")
                actions.append(f"Added to {existing.id} via scenario {scen.id}")
                warnings.extend(add_check.warnings)

        # ═══ STEP 8: State Persistence ═══
        try:
            self._persist_state()
        except Exception as e:
            log.error(f"State persistence failed: {e}")

        # ═══ STEP 9: Report Generation ═══
        report_md = self.reporter.generate(
            symbol=symbol, timeframe=tf["entry"],
            current_price=current_price, htf_bias=htf_bias,
            levels=all_levels, stacked_zones=stacked,
            intent=intent_score, signals=signals,
            scenarios=planner.active_scenarios(),
            positions=self.lifecycle.positions,
            range_info=rng,
        )

        # Safety summary'yi rapora ekle
        safety_section = self._build_safety_section(breaker_status, regime_analysis,
                                                       stale, warnings)
        report_md = report_md.replace("## Öneri", safety_section + "\n## Öneri")

        # SMC v2 — persist setup state if wired (gated, inert when None).
        # Save errors logged but do NOT abort the cycle — persistence failure
        # must not break trading.
        #
        # MAINTENANCE NOTE: this save() MUST remain ABOVE the return below.
        # Future early-return branches added above this point would silently
        # skip persistence and lose a tick's state changes. If you add a new
        # early-exit branch above, also call self.setup_state_store.save()
        # within the same gated try/except in that branch.
        if self.setup_state_store is not None:
            try:
                self.setup_state_store.save()
            except Exception as e:
                log.error(f"setup_state save failed (continuing cycle): {e}")

        return SafeCycleResult(
            symbol=symbol, timeframe=tf["entry"],
            current_price=current_price, htf_bias=htf_bias,
            can_trade=can_trade,
            breaker_state=breaker_status.state.value,
            regime=regime_analysis.regime,
            stale_data=stale,
            warnings=warnings,
            levels=all_levels, stacked_zones=stacked,
            intent=intent_score, signals=signals,
            scenarios=planner.active_scenarios(),
            report_md=report_md, actions_taken=actions,
        )

    # ─────────────────────────────────────────────────────────────
    # SMC v2 scaffolding (inert default, opt-in via setup_state_store)
    # ─────────────────────────────────────────────────────────────

    def confirm_entry(
        self,
        df_15m,
        zone: "ZoneSpec",
        direction: str,
        since_ts: int,
    ) -> tuple:
        """LTF entry confirmation for SMC v2 setups.

        Thin proxy to `engine.smc_v2.confirmation.confirm_entry` (spec §4.1).
        Detects bearish engulfing (SHORT) or bullish engulfing (LONG) inside
        the pullback zone, with close inside the zone, after `since_ts`.

        Returns: (True, entry_price) on first confirmation; (False, None) else.

        Wired in PR #S3b. Previously a placeholder returning (False, None)
        from PR #S2b — the real implementation now lives in
        engine/smc_v2/confirmation.py (PR #S3a / #68).
        """
        # Local import to keep the orchestrator module import-light when
        # v2 is not active. Matches the existing pattern in
        # _advance_setup_state_tick.
        from engine.smc_v2.confirmation import confirm_entry as _confirm
        return _confirm(
            df_15m=df_15m, zone=zone, direction=direction, since_ts=since_ts,
        )

    def _advance_setup_state_tick(
        self,
        symbol: str,
        current_price: float,
        current_bar_ts: int,
        pullback_timeout_bars: int = 8,
        df_15m=None,
    ) -> None:
        """Advance pending SMC v2 setup candidates for `symbol` by one tick.

        Per spec §4.3 step 2 (advance phase only — trigger phase is PR #S3c):
          For each pending candidate matching symbol:
            1. bars_waited += 1
            2. If bars_waited > pullback_timeout_bars → state = EXPIRED
            3. Elif state == AWAITING_PULLBACK and price ∈ zone → state = IN_ZONE
            4. If state == IN_ZONE → call confirm_entry; if True → state = CONFIRMED

        Inert when `self.setup_state_store is None` — short-circuits with no
        side effects. This is the load-bearing invariant for v1 safety.

        Args:
            symbol: trading pair
            current_price: latest LTF (15m) close
            current_bar_ts: latest LTF bar's ms-epoch timestamp
            pullback_timeout_bars: max bars to wait for pullback (default 8 per spec §4.3)
            df_15m: optional LTF DataFrame for confirmation lookup. Required
                for IN_ZONE → CONFIRMED transition; if None, the
                confirm_entry call is SKIPPED (state stays IN_ZONE).
                run_cycle always passes df_entry; test paths exercising
                only the state machine may omit it.

        Other-symbol candidates are untouched (operation is scoped to `symbol`).
        Terminal states (CONFIRMED, EXPIRED) are skipped — they wait for the
        next save() call to be pruned.
        """
        # Inert default — no v1 behavior change
        if self.setup_state_store is None:
            return

        smc_v2_cfg = self.config.get("smc_v2", {})
        require_confirmation = smc_v2_cfg.get("require_confirmation", True)
        effective_pullback_timeout_bars = smc_v2_cfg.get("pullback_timeout_bars", pullback_timeout_bars)

        # Local import to avoid module-level circular dependency on smc_v2
        from engine.smc_v2.zones import is_price_in_zone
        from engine.smc_v2.setup_state import PERSISTED_STATES

        for cand in self.setup_state_store.candidates:
            if cand.symbol != symbol:
                continue
            if cand.state not in PERSISTED_STATES:
                # CONFIRMED or EXPIRED — terminal, skip
                continue

            cand.bars_waited += 1

            if cand.bars_waited > effective_pullback_timeout_bars:
                cand.state = "EXPIRED"
                continue

            if cand.state == "AWAITING_PULLBACK" and is_price_in_zone(
                current_price, cand.target_zone
            ):
                if not require_confirmation:
                    cand.state = "CONFIRMED"
                    clamped_entry_price = min(max(current_price, cand.target_zone.low), cand.target_zone.high)
                    self._place_v2_entry_order(
                        cand,
                        current_price=current_price,
                        entry_price=clamped_entry_price,
                    )
                    continue
                else:
                    cand.state = "IN_ZONE"

            if cand.state == "IN_ZONE":
                if not require_confirmation:
                    if is_price_in_zone(current_price, cand.target_zone):
                        cand.state = "CONFIRMED"
                        clamped_entry_price = min(max(current_price, cand.target_zone.low), cand.target_zone.high)
                        self._place_v2_entry_order(
                            cand,
                            current_price=current_price,
                            entry_price=clamped_entry_price,
                        )
                        continue
                    else:
                        # Price has left the zone, do NOT confirm/enter, let it expire on timeout
                        continue
                # Skip confirmation when df_15m not provided (state-machine-
                # only test paths). Real run_cycle always passes df_entry.
                if df_15m is None:
                    continue
                confirmed, entry_px = self.confirm_entry(
                    df_15m=df_15m,
                    zone=cand.target_zone,
                    direction=cand.direction,
                    since_ts=cand.trigger_bar_ts,
                )
                if confirmed:
                    cand.state = "CONFIRMED"
                    # PR #S3c-2: place entry order if order_manager is wired.
                    # Inert when self.order_manager is None (test/paper).
                    # All safety gates (dry_run, mainnet, REJECT, size)
                    # enforced inside _place_v2_entry_order + OrderManager.
                    self._place_v2_entry_order(
                        cand,
                        current_price=current_price,
                        entry_price=entry_px,
                    )

    def _emit_setup_candidates(
        self,
        symbol: str,
        htf_bias: str,
        ltf_structure_breaks: list,
        htf_swings: dict,
        htf_bars: list,
        htf_fvgs: list,
        ote_band: tuple,
        ltf_trigger_idx_min: int,
    ) -> None:
        """Trigger phase: detect new CHoCH events and emit SetupCandidates.

        Per spec §4.3 step 3. Calls engine.smc_v2.triggers.generate_setup_candidates
        and appends each candidate to self.setup_state_store via store.add()
        (which enforces per-symbol cap; over-cap candidates silently dropped).

        Inert when self.setup_state_store is None — short-circuits.
        """
        if self.setup_state_store is None:
            return

        # Local import to avoid circular dep with smc_v2 package
        from engine.smc_v2.triggers import generate_setup_candidates

        new_candidates = generate_setup_candidates(
            symbol=symbol,
            htf_bias=htf_bias,
            ltf_structure_breaks=ltf_structure_breaks,
            htf_swings=htf_swings,
            htf_bars=htf_bars,
            htf_fvgs=htf_fvgs,
            ote_band=ote_band,
            ltf_trigger_idx_min=ltf_trigger_idx_min,
        )
        for cand in new_candidates:
            # add() returns False if per-symbol cap reached — silently dropped
            # (matches spec §6 setup_cap rejection counter; orchestrator
            # could log this in a future patch if operator visibility wanted)
            self.setup_state_store.add(cand)

    def _place_v2_entry_order(
        self,
        cand,
        current_price: float,
        entry_price: float,
    ):
        """Place entry order for a CONFIRMED SetupCandidate.

        Per spec §5: computes SL via calc_sl, TP via calc_tp_targets,
        size via risk.calc_position_size with v1-parity args (leverage +
        max_notional_pct), explicit pos_guard.can_open_position and
        breaker gates, then OrderManager.open_position.

        Safety gates (full parity with v1 signals.py path):
        - order_manager is None → skip (test/paper mode)
        - breaker.check.can_trade is False → skip (HALTED/TRIPPED)
        - pos_guard.can_open_position is False → skip (notional / exposure /
          holding-hours / pyramid / SL ATR distance / max-open / opposite-direction)
        - pos_guard.is_new_entry_allowed is False → skip (pause guard)
        - dry_run enforced inside OrderManager.open_position
        - mainnet_guard enforced inside BinanceClient
        - SLTooFarError / InsufficientTPDistanceError from calculators → setup rejected
        - size <= 0 → skip

        Returns the new Position (or None on rejection).

        DELIBERATE SIMPLIFICATIONS for PR #S3c-2 (follow-up PRs):
        - ATR proxy: max(entry*0.01, zone_width). Real ATR threading is
          follow-up. Effect: larger ATR → wider SL (not safer for trader,
          but harder for setup to be accepted via max_sl_atr clamp).
        - Empty htf_swings/htf_fvgs/eq_levels → RR_PROJECTION TP fallback.
          Real HTF data threading is follow-up.
        - Reverse-on-profit branch (v1 has it) NOT replicated here;
          opposite-direction setups will be rejected by pos_guard like v1.
        """

        # Symbol whitelist gate (PR #S6): only fire for symbols explicitly
        # opted-in via engine.smc_v2_symbols. ["*"] = all; [] (default) = none.
        # First gate so non-whitelisted symbols don't incur cost of breaker /
        # tp_calc / sizing. v2 candidate state machine still runs upstream
        # (consumes the setup); only execution is gated.
        engine_cfg = self.config.get("engine", {})
        whitelist_raw = engine_cfg.get("smc_v2_symbols", [])
        # Defensive: tolerate operator YAML typo (string instead of list) by
        # rejecting non-list values. Per risk-ops review feedback — substring
        # `in` semantics on a string would otherwise produce surprise matches.
        if not isinstance(whitelist_raw, list):
            log.warning(
                f"[v2 reject] {cand.symbol}: engine.smc_v2_symbols must be a list, "
                f"got {type(whitelist_raw).__name__}={whitelist_raw!r}"
            )
            return None
        if "*" not in whitelist_raw and cand.symbol not in whitelist_raw:
            log.info(f"[v2 reject] {cand.symbol}: not in smc_v2_symbols whitelist")
            return None

        # Breaker gate (MUST match v1 — breaker.HALTED must block v2 too)
        try:
            breaker_status = self.breaker.check(now=None)
            if not breaker_status.can_trade:
                log.info(f"[v2 reject] {cand.symbol}: breaker {breaker_status.state.value}")
                return None
        except Exception as e:
            log.warning(f"[v2 reject] {cand.symbol}: breaker check failed ({e})")
            return None

        from engine.smc_v2.sl_calc import calc_sl
        from engine.smc_v2.tp_calc import calc_tp_targets
        from engine.smc_v2.exceptions import SLTooFarError, InsufficientTPDistanceError
        from types import SimpleNamespace

        safety_cfg = self.config.get("safety", {})
        risk_cfg = self.config.get("risk", {})
        exchange_cfg = self.config.get("exchange", {})

        # ATR proxy — see DELIBERATE SIMPLIFICATIONS in docstring.
        atr_15m = max(entry_price * 0.01,
                      abs(cand.target_zone.high - cand.target_zone.low))

        try:
            sl = calc_sl(
                direction=cand.direction,
                entry_price=entry_price,
                zone=cand.target_zone,
                htf_swing_anchor=cand.htf_swing_anchor,
                atr_15m=atr_15m,
                config=SimpleNamespace(
                    sl_atr_buffer=safety_cfg.get("sl_atr_buffer", 0.5),
                    min_sl_atr=safety_cfg.get("min_sl_atr", 0.5),
                    max_sl_atr=safety_cfg.get("max_sl_atr", 5.0),
                ),
            )
        except SLTooFarError as e:
            log.info(f"[v2 reject] {cand.symbol}: sl_too_far ({e})")
            return None

        try:
            tp1, tp2, tp_tags = calc_tp_targets(
                direction=cand.direction,
                entry_price=entry_price,
                sl_price=sl,
                htf_swings={"swing_highs": [], "swing_lows": []},
                htf_fvgs=[],
                eq_levels=[],
                config=SimpleNamespace(
                    min_rr=risk_cfg.get("min_rr", 1.8),
                    fib_ext=self.config.get("fibonacci", {}).get("ext_tp2", 1.618),
                ),
            )
        except InsufficientTPDistanceError as e:
            log.info(f"[v2 reject] {cand.symbol}: tp1_too_close ({e})")
            return None

        # tp2=None signals single-target mode (spec §4.2). Lifecycle + exchange
        # support shipped in PR #S5 / #S5.5 / #S5.6: OrderManager skips TP2
        # placement and gives TP1 full size; partial_close TP1 branch full-closes;
        # _move_sl_to_breakeven cancels orphan SL via _cancel_position_siblings.
        # PR #S6.5 removed the early rejection here. tp2=None flows through.

        # Position size — v1 parity: pass leverage + max_notional_pct
        # (calc_position_size respects both caps; ignoring them would
        # produce strictly-larger positions than v1 would on the same setup)
        try:
            from risk import calc_position_size
            leverage = exchange_cfg.get("leverage", 1)
            max_notional = safety_cfg.get("max_position_notional_pct")
            if self.order_manager is not None and self.order_manager.client is not None:
                balance = self.order_manager.client.get_balance()
            else:
                balance = self.breaker.current_balance
            size = calc_position_size(
                balance=balance,
                risk_pct=risk_cfg.get("risk_per_trade_pct", 0.75),
                entry=entry_price,
                sl=sl,
                leverage=leverage,
                max_notional_pct=max_notional,
            )
        except (TypeError, ValueError, ZeroDivisionError, AttributeError) as e:
            log.warning(f"[v2 reject] {cand.symbol}: sizing failed ({e})")
            return None

        if size <= 0:
            log.info(f"[v2 reject] {cand.symbol}: size <= 0 ({size})")
            return None

        # Position guard (MUST match v1 — notional/exposure/holding/pyramid/
        # SL-ATR/max-open/opposite-direction enforcement)
        try:
            guard_check = self.pos_guard.can_open_position(
                balance=balance,
                entry=entry_price,
                size=size,
                sl=sl,
                atr=atr_15m,
                direction=cand.direction,
                symbol=cand.symbol,
                existing_positions=self.lifecycle.positions,
                leverage=exchange_cfg.get("leverage", 1),
            )
            if not guard_check.allowed:
                log.info(f"[v2 reject] {cand.symbol}: pos_guard ({guard_check.reason})")
                return None
        except Exception as e:
            log.warning(f"[v2 reject] {cand.symbol}: pos_guard check failed ({e})")
            return None

        # Pause guard (MUST match v1 — operator-toggled new-entry pause).
        # PositionGuard.is_new_entry_allowed needs a signal-like object with
        # `symbol`, `side`, `is_pyramid` attributes (SimpleNamespace works).
        try:
            pause_signal = SimpleNamespace(
                symbol=cand.symbol,
                side="buy" if cand.direction == "LONG" else "sell",
                is_pyramid=False,
            )
            pause_decision = self.pos_guard.is_new_entry_allowed(pause_signal)
            if not pause_decision.allowed:
                log.info(f"[v2 reject] {cand.symbol}: pause_guard (new entries paused)")
                return None
        except Exception as e:
            log.warning(f"[v2 reject] {cand.symbol}: pause check failed ({e})")
            return None

        tp2_log = f"{tp2:.4f}" if tp2 is not None else "NONE"
        log.info(
            f"[v2] {cand.direction} {cand.symbol} entry={entry_price:.4f} "
            f"sl={sl:.4f} tp1={tp1:.4f} tp2={tp2_log} size={size:.6f} "
            f"(zone={cand.target_zone.source}, tp1={tp_tags.get('tp1_source')}, "
            f"tp2={tp_tags.get('tp2_source')})"
        )

        # SMC v2 telemetry (PR #S5) — derive from candidate + tp_calc output.
        # ZoneSpec.source is "HTF_FVG" or "OTE"; map to entry_setup_source values
        # defined in spec §6 (FVG_PULLBACK / OTE_RETRACE).
        zone_source = cand.target_zone.source
        if zone_source == "HTF_FVG":
            entry_setup_source = "FVG_PULLBACK"
        elif zone_source == "OTE":
            entry_setup_source = "OTE_RETRACE"
        else:
            entry_setup_source = None  # forward-compat for unknown ZoneSpec sources

        # Shadow mode gate (PR #S6): smc_v2_shadow=true → log the would-be
        # signal to logs/smc_v2_shadow.log and return None instead of placing.
        # All safety gates above still execute — operator sees rejections in
        # main log; shadow log only captures ACCEPTED-but-not-executed signals.
        if engine_cfg.get("smc_v2_shadow", False):
            self._log_shadow_signal(
                cand=cand, entry_price=entry_price, sl=sl, tp1=tp1, tp2=tp2,
                size=size, tp_tags=tp_tags,
                entry_setup_source=entry_setup_source,
                reason="SHADOW_MODE",
            )
            return None

        if self.order_manager is None:
            # Paper-trade / backtest mode: open position in local lifecycle state directly
            pos = self.lifecycle.open_position(
                symbol=cand.symbol,
                direction=cand.direction,
                entry_price=entry_price,
                size=size,
                sl=sl,
                tp1=tp1,
                tp2=tp2,
            )
            log.info(f"✅ [v2 paper] [{cand.symbol}] Opened {cand.direction} @ {entry_price:.4f} "
                     f"size={size:.6f} SL={sl:.4f} TP1={tp1:.4f} TP2={tp2_log}")
        else:
            # C7: the live-price re-validation for the v2 CONFIRMED→order path is the
            # OrderManager entry-drift guard inside open_position — it re-reads the
            # live price and rejects if it has drifted past max_entry_drift_pct from
            # this confirmed `entry` (or is already past TP1). Combined with C1
            # (closed-bar confirmation), the v2 entry cannot repaint into a
            # stale-price order. See test_entry_order_placement TestV2EntryDriftGuard.
            pos = self.order_manager.open_position(
                symbol=cand.symbol,
                direction=cand.direction,
                size=size,
                entry=entry_price,
                sl=sl,
                tp1=tp1,
                tp2=tp2,
                entry_setup_source=entry_setup_source,
                tp1_target_type=tp_tags.get("tp1_source"),
                tp2_target_type=tp_tags.get("tp2_source"),
                bars_to_pullback=cand.bars_waited,
                atr_value=float(atr_15m),
            )

        if pos is not None:
            # Plumb telemetry for V2 entry
            z_mid = 0.0
            if getattr(cand, "target_zone", None):
                z_mid = (cand.target_zone.low + cand.target_zone.high) / 2.0

            ts_sig = None
            if getattr(cand, "trigger_bar_ts", None):
                try:
                    ts_sig = datetime.fromtimestamp(cand.trigger_bar_ts / 1000, tz=timezone.utc).isoformat()
                except Exception:
                    pass

            act_fill = getattr(pos, "avg_entry_price", None)
            if act_fill is None:
                act_fill = getattr(pos, "entry", entry_price)

            self._journal_record_entry(
                pos,
                agent_review=None,
                signal_entry_price=entry_price,
                actual_fill_price=act_fill,
                zone_mid=z_mid,
                ts_signal=ts_sig,
                ts_fill=pos.opened_at,
            )

            rr = abs(tp1 - entry_price) / abs(entry_price - sl) if entry_price != sl else 0.0
            size_notional_pct = (size * entry_price) / balance * 100.0 if balance > 0 else 0.0
            self._run_agent_review_async(
                pos=pos,
                confluence=cand.confluence_score,
                htf_bias=cand.htf_bias,
                df_htf=None,
                adx=0.0,
                rr=rr,
                size_notional_pct=size_notional_pct,
            )

        return pos

    def _log_shadow_signal(self, *, cand, entry_price, sl, tp1, tp2, size,
                            tp_tags, entry_setup_source, reason: str) -> None:
        """Append one JSON line to logs/smc_v2_shadow.log (PR #S6).

        Best-effort: I/O failures logged at WARNING but never raised — must
        not affect tick loop or order flow.
        """
        log_dir = Path("logs")
        try:
            log_dir.mkdir(parents=True, exist_ok=True)
        except OSError as e:
            log.warning(f"[shadow] could not create logs/ dir: {e}")
            return
        payload = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "symbol": cand.symbol,
            "direction": cand.direction,
            "entry": float(entry_price),
            "sl": float(sl),
            "tp1": float(tp1),
            "tp2": float(tp2) if tp2 is not None else None,
            "size": float(size),
            "entry_setup_source": entry_setup_source,
            "tp1_target_type": tp_tags.get("tp1_source"),
            "tp2_target_type": tp_tags.get("tp2_source"),
            "bars_to_pullback": int(cand.bars_waited),
            "confluence_score": int(cand.confluence_score),
            "would_execute": False,
            "reason": reason,
        }
        try:
            with (log_dir / "smc_v2_shadow.log").open("a", encoding="utf-8") as f:
                f.write(json.dumps(payload) + "\n")
        except OSError as e:
            log.warning(f"[shadow] write failed: {e}")

    @staticmethod
    def _build_safety_section(breaker, regime, stale, warnings) -> str:
        lines = ["## Güvenlik Durumu", ""]

        state_icon = {"OPEN": "🟢", "TRIPPED": "🟡", "HALTED": "🔴"}.get(
            breaker.state.value, "⚪"
        )
        lines.append(f"- Circuit Breaker: {state_icon} **{breaker.state.value}**")
        if breaker.reason:
            lines.append(f"  - Reason: {breaker.reason}")
        if breaker.metrics:
            for k, v in breaker.metrics.items():
                lines.append(f"  - {k}: {v}")

        regime_icon = {
            "TRENDING": "📈", "RANGING": "↔️", "VOLATILE": "⚡",
            "REVERSAL": "🔄", "LOW_LIQUIDITY": "💧", "UNKNOWN": "❓"
        }.get(regime.regime, "•")
        lines.append(f"- Market Regime: {regime_icon} **{regime.regime}** "
                     f"({regime.confidence}% confidence)")
        lines.append(f"  - ADX: {regime.adx:.1f} | BBW: {regime.bb_width:.2f} | "
                     f"ATR: {regime.atr_ratio:.1f}x")

        if stale:
            lines.append("- ⚠️ **Stale data detected — analysis only**")

        if warnings:
            lines.append("- Warnings:")
            for w in warnings[:5]:
                lines.append(f"  - {w}")

        lines.append("")
        return "\n".join(lines)
