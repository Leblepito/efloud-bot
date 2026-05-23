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

import pandas as pd
import logging
from datetime import datetime
from typing import Optional, TYPE_CHECKING
from dataclasses import dataclass

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
                  setup_state_store: Optional["SetupStateStore"] = None):
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

    def _get_planner(self, symbol: str) -> ScenarioPlanner:
        """Sembol başına ScenarioPlanner — senaryolar karışmasın."""
        if symbol not in self._planners:
            self._planners[symbol] = ScenarioPlanner()
        return self._planners[symbol]

    def _restore_state(self):
        """Startup'ta önceki state'i yükle."""
        breaker_state = self.store.load("breaker")
        if breaker_state:
            try:
                self.breaker.current_balance = breaker_state.get("current_balance",
                                                                   self.breaker.current_balance)
                self.breaker.peak_balance = breaker_state.get("peak_balance",
                                                                 self.breaker.peak_balance)
                self.breaker.consecutive_losses = breaker_state.get("consecutive_losses", 0)
                log.info(f"♻️  Restored breaker state: balance=${self.breaker.current_balance:.2f}, "
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
                        tp2=float(d.get("tp2") or 0.0),
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

    def _persist_state(self):
        """State'i diske yaz."""
        if not self.persist:
            return
        self.store.save("breaker", self.breaker.to_dict())
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

    def _journal_record_entry(self, pos: Position) -> None:
        """Record a freshly-opened position to the trade journal.

        No-op when self.trade_journal is None (backwards-compat for backtest
        and unit-test paths that don't wire a journal). Snapshot enrichment
        (htf_bias, intent_score, confluence) is intentionally minimal here;
        a follow-up PR will feed those from the signal context. The
        minimum-viable snapshot is enough to make Phase 0 evidence
        extraction return journal_rows > 0.
        """
        if self.trade_journal is None:
            return
        if not pos.entries:
            return
        entry = pos.entries[0]
        snap = TradeSnapshot(
            trade_id=pos.id,
            symbol=pos.symbol,
            direction=pos.direction,
            timeframe="",
            entry_timestamp=entry.timestamp,
            entry_price=entry.price,
            sl_initial=pos.initial_sl,
            tp1_initial=pos.tp1,
            tp2_initial=pos.tp2,
            position_size=entry.size,
            htf_bias="",
            intent_score_entry=0,
            intent_label_entry="",
            confluence_score=0,
            scenario_name=pos.scenario_id,
        )
        try:
            self.trade_journal.record_entry(snap)
        except Exception as e:
            log.warning(f"trade_journal.record_entry failed for {pos.id}: {e}")

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
                                f"REVERSE close failed for {symbol}: {e}. "
                                f"Manual intervention required."
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
                self.lifecycle.close_position(pos, current_price, "MANUAL")
                self._journal_record_exit(pos, exit_price=current_price, reason="MANUAL")
                actions.append(f"Force-closed {pos.id} (max holding time)")
            warnings.extend(hold_check.warnings)

        # ═══ STEP 6: Yeni Trade Decision ═══
        can_trade = (
            breaker_status.can_trade
            and not stale
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
                        notional = calc.calculate_position_size(actual_balance)
                        # Convert notional (USDT) → contract size (asset units)
                        size = notional / latest.entry if latest.entry > 0 else 0.0
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
                                    exchange_pos = self.order_manager.open_position(
                                        symbol, latest.direction, size,
                                        latest.entry, latest.sl, latest.tp1, latest.tp2,
                                        trace_id=trace_id,
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
                                                self.notification_mgr.alert(flat_msg)
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
                                self._journal_record_entry(pos)
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
        """LTF entry confirmation for SMC v2 setups — placeholder.

        Spec §4.1 confirmation.py: look at 15m bars since `since_ts` that are
        inside `zone`; return (True, entry_price) when a counter-direction
        CHoCH or engulfing close confirms; else (False, None).

        **PR #S2b ships the stub returning (False, None).**
        Real implementation lands in PR #S3 (`engine/smc_v2/confirmation.py`).
        The stub exists so `_advance_setup_state_tick` can call it without
        AttributeError in tests.
        """
        return (False, None)

    def _advance_setup_state_tick(
        self,
        symbol: str,
        current_price: float,
        current_bar_ts: int,
        pullback_timeout_bars: int = 8,
    ) -> None:
        """Advance pending SMC v2 setup candidates for `symbol` by one tick.

        Per spec §4.3 step 2 (advance phase only — trigger phase is PR #S3):
          For each pending candidate matching symbol:
            1. bars_waited += 1
            2. If bars_waited > pullback_timeout_bars → state = EXPIRED
            3. Elif state == AWAITING_PULLBACK and price ∈ zone → state = IN_ZONE
            4. If state == IN_ZONE → call confirm_entry; if True → state = CONFIRMED
               (PR #S2b stub returns False; real impl in PR #S3)

        Inert when `self.setup_state_store is None` — short-circuits with no
        side effects. This is the load-bearing invariant for v1 safety.

        Other-symbol candidates are untouched (operation is scoped to `symbol`).
        Terminal states (CONFIRMED, EXPIRED) are skipped — they wait for the
        next save() call to be pruned.
        """
        # Inert default — no v1 behavior change
        if self.setup_state_store is None:
            return

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

            if cand.bars_waited > pullback_timeout_bars:
                cand.state = "EXPIRED"
                continue

            if cand.state == "AWAITING_PULLBACK" and is_price_in_zone(
                current_price, cand.target_zone
            ):
                cand.state = "IN_ZONE"

            if cand.state == "IN_ZONE":
                # confirm_entry stub returns (False, None) in PR #S2b
                # Real impl in PR #S3 uses df_15m to detect LTF CHoCH/engulfing
                confirmed, entry_px = self.confirm_entry(
                    df_15m=None,  # PR #S3 will pass the real DataFrame
                    zone=cand.target_zone,
                    direction=cand.direction,
                    since_ts=cand.trigger_bar_ts,
                )
                if confirmed:
                    cand.state = "CONFIRMED"
                    # Entry order placement also lands in PR #S3
                    # (signals.py → OrderManager.open_position dispatch)

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
