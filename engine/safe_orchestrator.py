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
from typing import Optional
from dataclasses import dataclass

from .smc import SMCEngine
from .levels import LevelEngine
from .intent import IntentEngine
from .signals import generate_signals
from .scenarios import ScenarioPlanner
from .lifecycle import PositionLifecycle
from .report import ReportEngine
from .regimes import RegimeDetector, RegimeAnalysis
from .safety import (
    CircuitBreaker, StateStore, PositionGuard,
    validate_kline_freshness, validate_kline_integrity,
    StaleDataError, cleanup_orphan_hedges
)

log = logging.getLogger("efloud.safe_orch")


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
                  permission_mgr=None, notification_mgr=None):
        """
        permission_mgr: PermissionManager instance (opsiyonel)
        notification_mgr: NotificationManager instance (opsiyonel)
        """
        self.config = config
        self.permission_mgr = permission_mgr
        self.notification_mgr = notification_mgr

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
        self.pos_guard = PositionGuard(
            max_notional_pct_of_balance=safety.get("max_position_notional_pct", 20),
            max_total_exposure_multiplier=safety.get("max_total_exposure", 5.0),
            max_holding_hours=safety.get("max_holding_hours", 48),
            max_pyramid_adds=safety.get("max_pyramid_adds", 2),
            min_sl_distance_atr=safety.get("min_sl_atr", 0.5),
            max_sl_distance_atr=safety.get("max_sl_atr", 5.0),
            reserve_balance=safety.get("reserve_balance", 0.0),
        )
        self.store = StateStore(state_dir)

        # Signal deduplication cache — {(symbol, direction, entry): timestamp}
        # Time-windowed: 1 saat sonra aynı signal yeniden açılabilir
        self._processed_signals: dict = {}

        # ═══ Task 5: Custom Risk Calculator Integration ═══
        risk_config = config.get('risk', {})
        if risk_config.get('position_size_calculation') == 'reverse_from_risk':
            from .risk.custom_calculator import CustomRiskCalculator  # Lazy import
            self.risk_calculator = CustomRiskCalculator(
                max_loss_usdt=risk_config.get('max_loss_per_trade_usdt', 20.0),
                leverage=config.get('exchange', {}).get('leverage', 3),
                target_stop_pct=risk_config.get('target_stop_distance_pct', 10.0) / 100.0
            )
            self.using_custom_risk = True
            log.info("✅ Using CustomRiskCalculator for position sizing")
        else:
            self.using_custom_risk = False
            log.info("Using legacy risk calculation")

        # Initialize managers (will be setup with client later)
        self.permission_manager = None
        self.notification_manager = None

        # Recovery
        self._restore_state()

    def _get_planner(self, symbol: str) -> ScenarioPlanner:
        """Sembol başına ScenarioPlanner — senaryolar karışmasın."""
        if symbol not in self._planners:
            self._planners[symbol] = ScenarioPlanner()
        return self._planners[symbol]

    def _setup_permission_manager(self, client):
        """Setup permission manager with exchange client"""
        if not self.permission_manager:
            from .permissions import PermissionManager  # Lazy import
            self.permission_manager = PermissionManager(client)
            symbols = self.config.get('symbols', {}).get('fixed_core', [])
            self.symbol_permissions = self.permission_manager.detect_all(symbols)
            tradeable_count = len([p for p in self.symbol_permissions.values() if p.tradeable])
            readonly_count = len(self.symbol_permissions) - tradeable_count
            log.info(f"Permission detection complete: {tradeable_count} tradeable, {readonly_count} readonly")

        # Initialize notification manager if not already done
        if not self.notification_manager:
            from .notifications import NotificationManager  # Lazy import
            self.notification_manager = NotificationManager()

    def get_symbol_permissions(self, symbols: list | None = None) -> dict:
        """Get current symbol permissions"""
        if not self.permission_manager:
            log.warning("Permission manager not initialized")
            return {}

        stored_permissions = getattr(self, 'symbol_permissions', {})
        if symbols:
            # Return subset of existing permissions for requested symbols
            return {sym: stored_permissions.get(sym) for sym in symbols if sym in stored_permissions}
        return stored_permissions

    def calculate_position_size(self, symbol: str, available_balance: float) -> float:
        """Calculate position size using custom risk calculator"""
        if not self.using_custom_risk:
            # Fall back to legacy calculation
            return self._legacy_position_size_calculation(symbol, available_balance)

        return self.risk_calculator.calculate_position_size(available_balance)

    def validate_trade_risk(self, symbol: str, position_size: float, current_price: float, stop_price: float) -> dict:
        """Validate trade meets risk requirements"""
        if not self.using_custom_risk:
            return {'valid': True, 'legacy_mode': True}

        return self.risk_calculator.validate_risk_parameters(position_size, current_price, stop_price)

    def send_readonly_signal(self, symbol: str, signal_data: dict):
        """Send notification for read-only symbols"""
        if self.notification_manager:
            self.notification_manager.signal_readonly(
                symbol=symbol,
                direction=signal_data.get('direction', 'N/A'),
                entry=signal_data.get('entry_price', 0.0),
                sl=signal_data.get('sl', 0.0),
                tp1=signal_data.get('tp1', 0.0),
                tp2=signal_data.get('tp2', 0.0),
                confluence=signal_data.get('confidence', 0),
                reasons=signal_data.get('reasons', [])
            )
        else:
            log.warning(f"Notification manager not available for {symbol} signal")

    def _legacy_position_size_calculation(self, symbol: str, available_balance: float) -> float:
        """Legacy position sizing for backwards compatibility"""
        risk_pct = self.config.get('risk', {}).get('risk_per_trade_pct', 0.75)
        return available_balance * (risk_pct / 100.0)

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

        # Position reconciliation log için
        saved_positions = self.store.load("positions")
        if saved_positions:
            log.info(f"♻️  Found {len(saved_positions)} saved positions — "
                     f"reconcile with exchange recommended")

    def _persist_state(self):
        """State'i diske yaz."""
        self.store.save("breaker", self.breaker.to_dict())
        self.store.save("positions",
                         [p.to_dict() for p in self.lifecycle.positions])
        # Tüm sembollerin aktif senaryolarını (symbol bilgisiyle birlikte) kaydet
        all_active = []
        for sym, planner in self._planners.items():
            for s in planner.active_scenarios():
                d = s.to_dict()
                d["symbol"] = sym
                all_active.append(d)
        self.store.save("scenarios", all_active)

    def run_cycle(
        self,
        symbol: str,
        df_htf: pd.DataFrame,
        df_mtf: pd.DataFrame,
        df_entry: pd.DataFrame,
        df_daily: Optional[pd.DataFrame] = None,
        balance: Optional[float] = None,
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
                validate_kline_freshness(df, tfname, tolerance_factor=2.5)
            except (StaleDataError, ValueError) as e:
                warnings.append(f"{name} data issue: {e}")
                log.warning(f"⚠️  {name} ({tfname}): {e}")
                stale = True

        if stale:
            log.warning("📛 Stale/invalid data detected — analysis only, NO TRADING")

        current_price = float(df_entry["close"].iloc[-1])

        # ═══ STEP 1: Circuit Breaker ═══
        breaker_status = self.breaker.check()
        if not breaker_status.can_trade:
            log.warning(f"🚨 Breaker {breaker_status.state.value}: {breaker_status.reason}")
            warnings.append(f"Breaker {breaker_status.state.value}: {breaker_status.reason}")

        # ═══ STEP 2: Regime Detection ═══
        regime_analysis = self.regime.analyze(df_entry, df_htf)
        log.info(f"📊 Regime: {regime_analysis.regime} ({regime_analysis.confidence}%) | "
                 f"ADX={regime_analysis.adx:.1f} BBW={regime_analysis.bb_width:.2f} "
                 f"ATR={regime_analysis.atr_ratio:.1f}x")

        # Volatilite circuit breaker
        if regime_analysis.atr_ratio > 3.0:
            if self.breaker.check_volatility(regime_analysis.atr_ratio):
                pass  # normal
            else:
                warnings.append("Volatility spike — trading halted 30 min")

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

                    from risk import calc_position_size
                    max_notional = self.config["safety"].get("max_position_notional_pct", 3.0)
                    size = calc_position_size(
                        actual_balance, risk_cfg["risk_per_trade_pct"],
                        latest.entry, latest.sl,
                        self.config["exchange"].get("leverage", 1),
                        max_notional_pct=max_notional,
                    )

                    atr = self.intent._atr(df_entry, 14)
                    guard_check = self.pos_guard.can_open_position(
                        balance=actual_balance,
                        entry=latest.entry, size=size, sl=latest.sl, atr=atr,
                        direction=latest.direction, symbol=symbol,
                        existing_positions=self.lifecycle.positions,
                        leverage=self.config["exchange"].get("leverage", 1),
                    )

                    if guard_check.allowed:
                        pos = self.lifecycle.open_position(
                            symbol, latest.direction, latest.entry, size,
                            latest.sl, latest.tp1, latest.tp2
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
                    else:
                        log.warning(f"🚫 Position blocked: {guard_check.reason}")
                        warnings.append(f"Signal rejected: {guard_check.reason}")

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
                add_size = calc_position_size(
                    balance_now, risk_cfg["risk_per_trade_pct"] * 0.5,
                    mid, scen.sl, self.config["exchange"].get("leverage", 1),
                    max_notional_pct=max_notional,
                )

                # Add guard
                add_check = self.pos_guard.can_add_to_position(existing, add_size, current_price)
                if add_check.allowed:
                    self.lifecycle.add_to_position(existing, mid, add_size, "scenario_add")
                    actions.append(f"Added to {existing.id} via scenario {scen.id}")
                    warnings.extend(add_check.warnings)
                else:
                    warnings.append(f"Add rejected: {add_check.reason}")

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
