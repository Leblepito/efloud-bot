"""Async bot worker — wraps the synchronous SafeOrchestrator cycle in asyncio.

Runs in the SAME process as FastAPI app (single-process Railway deployment).
On startup: loads config + creates SafeOrchestrator + BinanceClient + OrderManager.
Loop: every check_interval_sec, run reconcile() + run_cycle() in a thread executor
(ccxt is sync). Publishes events to events.bus for WebSocket clients.
"""
from __future__ import annotations

import asyncio
import logging
import os
from pathlib import Path
from typing import Optional

import yaml

from backend.audit.journal import AuditEngine
from backend.db import db
from backend.events import bus
from backend.notifications import TelegramNotifier
from engine import SafeOrchestrator
from engine.journal import TradeJournal
from engine.notifications import NotificationManager
from engine.permissions import PermissionManager
from engine.safety import MainnetGuard, OrphanProtector, load_orphan_protection_config
from engine.universe import SymbolUniverse
from exchange import BinanceClient, OrderManager, Position
from main import resolve_credentials, validate_config

log = logging.getLogger("efloud.runner")

# F3.6: must resolve to a real file. The previous default pointed at a micro
# config under the configs/ root that does not exist there (the file lives under
# configs/archive/), so an unset EFLOUD_CONFIG_PATH made start() silently refuse
# with "config not found". Default to the documented production config that
# deploy/.env.production actually sets. Prod always sets EFLOUD_CONFIG_PATH
# explicitly + AUTOSTART=0, so this is a fallback, not an auto-trade trigger.
CONFIG_PATH_DEFAULT = "configs/config.phase2_1k.yaml"


def _enforce_margin_setup(client, tradeable, margin_mode, leverage, hedge_mode):
    """Apply margin mode + leverage per symbol, then position mode globally.

    Returns (ok, error_message). PR A: margin-mode failure is FATAL (returns
    False) — ISOLATED must be a real guarantee, not best-effort. set_margin_mode
    already treats the benign -4046 'no need to change' as success internally, so
    a raised exception here is a genuine failure that must abort startup rather
    than silently run half-crossed. Leverage failure is non-fatal (set_leverage
    swallows internally). Position-mode failure aborts (pre-existing behavior).
    """
    for sym in tradeable:
        try:
            # set_margin_mode returns False on a genuine failure (it only RAISES
            # on the unexpected). It treats benign -4046 'no need to change' as
            # True internally, so a False here is a real ISOLATED-apply failure
            # that must abort — not just a swallowed exception.
            if not client.set_margin_mode(sym, margin_mode):
                return False, f"Margin mode setup failed for {sym} (set_margin_mode returned False)"
        except Exception as e:
            return False, f"Margin mode setup failed for {sym}: {e}"
        try:
            client.set_leverage(sym, leverage)
        except Exception as e:
            log.warning(f"Leverage setup warning for {sym}: {e}")
    try:
        if not client.set_position_mode(dual_side=hedge_mode):
            return False, (
                "Position mode setup failed! Binance rejected the change. "
                "Ensure NO open positions and NO open orders on the entire "
                "Futures account, then restart."
            )
    except Exception as e:
        return False, f"Position mode setup failed with exception: {e}"
    return True, ""


class BotRunner:
    def __init__(self) -> None:
        self.task: Optional[asyncio.Task] = None
        self.sentiment_task: Optional[asyncio.Task] = None
        self.loop: Optional[asyncio.AbstractEventLoop] = None  # captured at startup for cross-thread DB writes
        self.cfg: dict = {}
        self.client: Optional[BinanceClient] = None
        self.orch: Optional[SafeOrchestrator] = None
        self.order_mgr: Optional[OrderManager] = None
        self.universe: Optional[SymbolUniverse] = None
        # Telegram notifier — env-gated, no-op when EFLOUD_TELEGRAM_TOKEN/
        # CHAT_ID are not set. Constructed once at runner init so that
        # subsequent env edits don't change behavior mid-run (predictable).
        self.notifier: TelegramNotifier = TelegramNotifier()
        # Audit engine — scores closed trades; uses backend.db pool when ready.
        # Lazy-bound to db.pool in start() because pool is created in main.py
        # before BotRunner.start(). Always-present sentinel so downstream code
        # never has None-check on the attr; the engine itself no-ops on None pool.
        self.audit_engine: AuditEngine = AuditEngine(pool=None)
        self.cycle_count = 0
        self.last_cycle_at: Optional[str] = None
        self.last_cycle_duration_ms: int = 0
        self.running = False
        self.stopped = False
        self.last_error: Optional[str] = None
        self.pubsub_task: Optional[asyncio.Task] = None  # Phase 3.1 Pub/Sub consumer

        # Healthz / crash-loop runtime state (Aşama 2 Step 2)
        from engine.safety.runtime_state import RuntimeState
        state_dir = (
            self.cfg.get("operation", {}).get("state_dir") if self.cfg else None
        ) or os.environ.get("EFLOUD_STATE_DIR", "./state")
        self.runtime_state = RuntimeState(state_dir=state_dir)

    # ─────────────────────────────────────────────────────────────
    # Lifecycle
    # ─────────────────────────────────────────────────────────────

    async def start(self) -> None:
        # Aşama 2 Step 3: crash-loop suspension guard.
        # If recent crashes have crossed the threshold, do NOT spin up the
        # trading task. The FastAPI app stays alive so /healthz can return
        # status:"suspended", which Step 4's alerter and Step 5's daily-report
        # turn into a CRITICAL escalation. Operator intervenes manually
        # (see docs/runbooks/crash-loop-recovery.md).
        if self.runtime_state.is_in_crash_loop():
            log.critical(
                "⛔ CRASH LOOP DETECTED: %s crashes in last %s min — trading loop SUSPENDED. "
                "See docs/runbooks/crash-loop-recovery.md to recover.",
                self.runtime_state.snapshot()["crash_count"],
                30,
            )
            return  # Bot stays alive (FastAPI + healthz); no trading task created.

        # Idempotent: zaten running iken tekrar çağrılırsa hiçbir şey yapma
        if self.running and not self.stopped:
            log.info("start() ignored — runner already running")
            return

        # Yeni başlatma denemesi → stop flag ve eski hatayı temizle
        self.stopped = False
        self.last_error = None

        cfg_path = os.environ.get("EFLOUD_CONFIG_PATH", CONFIG_PATH_DEFAULT)
        log.info(f"Loading config: {cfg_path}")

        if not Path(cfg_path).exists():
            msg = f"Config not found: {cfg_path}"
            log.error(f"{msg} — bot will not start")
            self.last_error = msg
            return

        self.cfg = yaml.safe_load(Path(cfg_path).read_text(encoding="utf-8"))
        # Resolve trade-horizon profile in place (parity with main.load_config) —
        # daemon path must not silently read a stale/unresolved timeframe chain.
        from data.timeframes import resolve_timeframes
        try:
            resolve_timeframes(self.cfg)
        except ValueError as e:
            log.error(f"⛔ Timeframe profile resolution failed: {e}")
            self.last_error = f"Timeframe profile resolution failed: {e}"
            return

        try:
            validate_config(self.cfg)
        except ValueError as e:
            log.error(f"⛔ Config validation failed: {e}")
            self.last_error = f"Config validation failed: {e}"
            return

        # Mainnet Guard (non-interactive in worker mode)
        if not MainnetGuard.check(
            testnet=self.cfg["exchange"]["testnet"],
            dry_run=self.cfg["operation"]["dry_run"],
            interactive=False,
        ):
            log.error("Mainnet guard blocked startup")
            self.last_error = "Mainnet guard blocked startup (set EFLOUD_ALLOW_MAINNET=1)"
            return

        api_key, api_secret = resolve_credentials(self.cfg)
        if not self.cfg["operation"]["dry_run"] and (not api_key or not api_secret):
            log.error("Live mode requires BINANCE_API_KEY and BINANCE_API_SECRET")
            self.last_error = "Live mode requires BINANCE_API_KEY and BINANCE_API_SECRET"
            return

        ex_cfg = self.cfg["exchange"]
        self.client = BinanceClient(
            api_key=api_key, api_secret=api_secret,
            testnet=ex_cfg["testnet"], market_type=ex_cfg["market_type"],
        )

        self.universe = SymbolUniverse(self.cfg, client=self.client)
        symbols = self.universe.resolve(force_refresh=True)
        log.info(f"📡 Watchlist ({len(symbols)}): {', '.join(symbols)}")

        # Permission detection (live mode only)
        permission_mgr = None
        if api_key and not self.cfg["operation"].get("dry_run", True):
            try:
                permission_mgr = PermissionManager(self.client)
                ex = ex_cfg
                est_pos = self.cfg["safety"].get("starting_balance", 1000) * \
                          (self.cfg["safety"].get("max_position_notional_pct", 3.0) / 100) * \
                          ex.get("leverage", 3)
                permission_mgr.detect_all(symbols, estimated_notional=est_pos)
            except Exception as e:
                log.warning(f"Permission detection failed: {e}")

        # Leverage + margin mode setup (PR A: margin failure now aborts startup)
        if ex_cfg["market_type"] == "futures" and api_key and not self.cfg["operation"].get("dry_run", True):
            margin_mode = ex_cfg.get("margin_mode", "ISOLATED").upper()
            tradeable = (permission_mgr.get_tradeable_symbols() if permission_mgr else symbols)
            hedge_mode = ex_cfg.get("hedge_mode", False)
            ok, err = _enforce_margin_setup(
                self.client, tradeable, margin_mode,
                ex_cfg.get("leverage", 3), hedge_mode,
            )
            if not ok:
                log.error(f"⛔ {err}")
                self.last_error = err
                return

        notif_mgr = NotificationManager(channels=["log"])  # WS push üzerinden ayrıca yapılır
        state_dir = self.cfg["operation"].get("state_dir", "./state")

        orphan_cfg = load_orphan_protection_config(self.cfg.get("safety", {}))
        orphan_protector = OrphanProtector(orphan_cfg, self.client)

        # Shared TradeJournal so OrderManager (TP1/TP2/SL/RECONCILED closes)
        # and SafeOrchestrator (manual force-close + entry hooks) write to
        # the same JSONL file. State volume already mounts state_dir on the
        # VPS.
        trade_journal = TradeJournal(str(Path(state_dir) / "trade_journal.jsonl"))

        # OrderManager FIRST — orchestrator'a inject edilecek.
        # state_dir same as orchestrator's so restart restores order_mgr.positions
        # (prevents duplicate SL+TP1+TP2 stacking on Binance — 2026-05-08 bug).
        self.order_mgr = OrderManager(
            self.client, dry_run=self.cfg["operation"]["dry_run"],
            on_position_change=self._on_position_change,
            state_dir=state_dir,
            orphan_protector=orphan_protector,
            trade_journal=trade_journal,
            hedge_mode=self.cfg.get("exchange", {}).get("hedge_mode", False),
            max_entry_drift_pct=self.cfg.get("safety", {}).get("max_entry_drift_pct", 0.0),
        )

        # PR C — periodic PnL audit sweep config.
        _safety = self.cfg.get("safety", {})
        self.order_mgr.enable_pnl_audit = bool(_safety.get("enable_pnl_audit", True))
        self.order_mgr.pnl_audit_every_cycles = int(_safety.get("pnl_audit_every_cycles", 20))

        # PR B — post-placement SL/TP verification config.
        self.order_mgr.enable_post_placement_verify = bool(_safety.get("enable_post_placement_verify", True))
        self.order_mgr.verify_delay_sec = float(_safety.get("verify_delay_sec", 2.5))
        self.order_mgr.verify_max_attempts = int(_safety.get("verify_max_attempts", 3))
        self.order_mgr.rollback_on_sl_failure = bool(_safety.get("rollback_on_sl_failure", True))

        # PR #S6 wiring (hotfix): instantiate SetupStateStore when smc_version=v2.
        # Inert default (smc_version=v1 or engine block absent): setup_state_store=None
        # → all v2 hooks short-circuit per PR #67 contract.
        # Without this, FastAPI mode (production) never activated v2 regardless of
        # config.yaml flags — CLI-only main.py had the wiring but bot_runner did not.
        from main import _build_setup_state_store
        setup_state_store = _build_setup_state_store(self.cfg, state_dir)
        if setup_state_store is not None:
            log.info(
                "🟢 SMC v2 active: SetupStateStore initialized (max_pending_per_symbol=%d)",
                setup_state_store.max_pending_per_symbol,
            )
        else:
            log.info("SMC v2 inert (smc_version=v1 or engine block absent)")

        self.orch = SafeOrchestrator(
            self.cfg, state_dir=state_dir,
            permission_mgr=permission_mgr, notification_mgr=notif_mgr,
            order_manager=self.order_mgr,  # ← borsaya gerçek emir göndermek için
            trade_journal=trade_journal,
            setup_state_store=setup_state_store,
            breaker_state_sink=self._mirror_breaker_to_db,  # best-effort DB mirror
        )

        # Capture the running loop so executor-thread callbacks can schedule DB writes
        self.loop = asyncio.get_running_loop()

        # DB-mirror HALT fallback: the file StateStore (restored in the
        # orchestrator ctor above) is primary. But on a box where the state
        # volume was lost (VPS rebuild, 2026-05-15), the file is gone — so if the
        # breaker came up OPEN yet the Supabase breaker_state mirror says HALTED,
        # honor the operator-acknowledged HALT instead of silently resuming.
        try:
            if self.orch.breaker.status.state.value == "OPEN":
                db_row = await db.load_breaker_state()
                if db_row and db_row.get("halted"):
                    self.orch.breaker.restore_from_db_row(db_row)
                    log.warning(
                        "⛔ Breaker restored to HALTED from DB mirror (file state "
                        "absent): %s", self.orch.breaker.status.reason,
                    )
        except Exception as e:
            log.warning(f"DB-mirror breaker fallback skipped: {e}")

        # Bind audit engine to the live DB pool now that backend.db is connected.
        # Pool may still be None in degraded mode (no DATABASE_URL); engine no-ops.
        self.audit_engine = AuditEngine(pool=db.pool)

        # Spawn the worker task
        self.task = asyncio.create_task(self._run_loop(), name="bot_runner")
        self.sentiment_task = asyncio.create_task(self._run_sentiment_loop(), name="sentiment_worker")
        self.running = True
        log.info("🚀 Bot runner started")
        bus.publish("bot_started", config_path=cfg_path)
        await db.log_audit("bot_started", {"config_path": cfg_path})

        # Phase 3.1: Start Pub/Sub consumer task (graceful no-op if not configured)
        try:
            from backend.pubsub_consumer import PubSubConsumer
            self._pubsub_consumer = PubSubConsumer(
                cfg=self.cfg,
                orchestrator=self.orch,
                order_manager=self.order_mgr,
            )
            self.pubsub_task = asyncio.create_task(
                self._pubsub_consumer.run(), name="pubsub_consumer"
            )
            log.info("📡 Pub/Sub consumer task launched")
        except Exception as e:
            log.warning(f"Pub/Sub consumer failed to start (non-critical): {e}")

    async def stop(self) -> None:
        self.stopped = True
        # Phase 3.1: stop Pub/Sub consumer
        if self.pubsub_task and not self.pubsub_task.done():
            try:
                self._pubsub_consumer.stop()
                await asyncio.wait_for(self.pubsub_task, timeout=5.0)
            except (asyncio.CancelledError, asyncio.TimeoutError):
                self.pubsub_task.cancel()
            except Exception as e:
                log.warning(f"Pub/Sub consumer stop error: {e}")
        if self.sentiment_task and not self.sentiment_task.done():
            self.sentiment_task.cancel()
            try:
                await self.sentiment_task
            except asyncio.CancelledError:
                pass
        if self.task and not self.task.done():
            self.task.cancel()
            try:
                await self.task
            except asyncio.CancelledError:
                pass
        self.running = False
        log.info("🛑 Bot runner stopped")
        bus.publish("bot_stopped")
        await db.log_audit("bot_stopped", {})

    async def restart(self) -> None:
        """Stop + start sequence. Useful when config changes externally."""
        await self.stop()
        await self.start()

    # ─────────────────────────────────────────────────────────────
    # Main loop
    # ─────────────────────────────────────────────────────────────

    async def _run_loop(self) -> None:
        interval = self.cfg["operation"]["check_interval_sec"]
        log.info(f"Loop interval: {interval}s")

        loop = asyncio.get_running_loop()

        while not self.stopped:
            t0 = loop.time()
            self.cycle_count += 1
            try:
                bus.publish("cycle_start", cycle_n=self.cycle_count)

                # Reconcile first (sync ccxt — run in thread)
                if self.order_mgr and not self.cfg["operation"]["dry_run"]:
                    closed = await loop.run_in_executor(None, self.order_mgr.reconcile)
                    self.runtime_state.update_exchange_ping()    # NEW — exchange is reachable
                    for pos in closed:
                        await self._persist_close(pos)

                # Run scan cycle
                await loop.run_in_executor(None, self._scan_universe)

                duration_ms = int((loop.time() - t0) * 1000)
                self.last_cycle_duration_ms = duration_ms
                self.last_cycle_at = self._now_iso()
                self.runtime_state.update_loop_tick()        # NEW — Aşama 2 Step 2
                bus.publish(
                    "cycle_end",
                    cycle_n=self.cycle_count,
                    duration_ms=duration_ms,
                    open_positions=len(self.order_mgr.positions) if self.order_mgr else 0,
                )

            except asyncio.CancelledError:
                raise
            except Exception as e:
                log.error(f"Cycle error: {e}", exc_info=True)
                bus.publish("error", message=str(e))
                self.runtime_state.set_fatal_exception()    # NEW — sticky flag for healthz

            # Sleep until next cycle (cancellable)
            elapsed = loop.time() - t0
            sleep_for = max(0.0, interval - elapsed)
            try:
                await asyncio.sleep(sleep_for)
            except asyncio.CancelledError:
                raise

    def _scan_universe(self) -> None:
        """Sync part — runs in executor thread."""
        if not self.universe or not self.orch or not self.order_mgr or not self.client:
            return

        symbols = self.universe.resolve()
        tf = self.cfg["timeframes"]
        limit = tf.get("kline_limit", 500)

        for sym in symbols:
            try:
                df_htf = self.client.fetch_ohlcv(sym, tf["htf"], limit)
                df_mtf = self.client.fetch_ohlcv(sym, tf["mtf"], limit)
                df_entry = self.client.fetch_ohlcv(sym, tf["entry"], limit)
                df_daily = None
                try:
                    df_daily = self.client.fetch_ohlcv(sym, "1d", 100)
                except Exception:
                    pass

                balance = None
                if not self.cfg["operation"]["dry_run"]:
                    try:
                        balance = self.client.get_balance()
                    except Exception:
                        pass

                result = self.orch.run_cycle(
                    symbol=sym,
                    df_htf=df_htf, df_mtf=df_mtf, df_entry=df_entry,
                    df_daily=df_daily, balance=balance,
                )

                # Periyodik equity snapshot — son sembolde tut (cross-thread schedule)
                if balance is not None and sym == symbols[-1] and self.loop:
                    asyncio.run_coroutine_threadsafe(
                        db.record_equity_snapshot(
                            balance=balance,
                            open_positions_count=len(self.order_mgr.positions),
                        ),
                        self.loop,
                    )

            except Exception as e:
                log.error(f"[{sym}] cycle failed: {e}")

    # ─────────────────────────────────────────────────────────────
    # Event handlers
    # ─────────────────────────────────────────────────────────────

    def _mirror_breaker_to_db(self, breaker_dict: dict) -> None:
        """Sync sink wired into SafeOrchestrator._persist_state — schedules a
        best-effort UPSERT of the breaker summary into Supabase breaker_state.

        Cross-thread safe (run_coroutine_threadsafe), fire-and-forget, and fully
        guarded: a missing pool/loop or any failure is swallowed so it can never
        perturb the trading cycle. Disk StateStore remains authoritative.
        """
        if not self.loop or not db.pool:
            return
        try:
            asyncio.run_coroutine_threadsafe(
                db.upsert_breaker_state(breaker_dict), self.loop,
            )
        except Exception as e:
            log.warning(f"_mirror_breaker_to_db schedule failed (ignored): {e}")

    def _on_position_change(self, event_type: str, pos: Position) -> None:
        """Sync callback from OrderManager — bridge to async event bus + DB.

        Also fires Telegram notifications (best-effort, fire-and-forget) so
        the operator gets immediate visibility without polling. Notifier calls
        swallow exceptions internally; a failed Telegram POST will NEVER
        propagate back into the trading loop. See backend/notifications/__init__.py
        for the contract.
        """
        payload = {
            "symbol": pos.symbol,
            "direction": pos.direction,
            "entry": pos.entry,
            "exit": pos.exit_price or None,
            "sl": pos.sl,
            "tp1": pos.tp1,
            "tp2": pos.tp2,
            "size": pos.size,
            "pnl_usdt": pos.pnl_usdt or None,
            "exit_reason": pos.exit_reason or None,
            "opened_at": pos.opened_at,
            "closed_at": pos.closed_at or None,
        }
        bus.publish(event_type, **payload)

        # Telegram notifications — wrapped in try so any unexpected formatting
        # bug cannot break DB persistence below.
        try:
            if event_type == "position_opened":
                self.notifier.notify_position_opened(
                    symbol=pos.symbol, direction=pos.direction,
                    entry=pos.entry, sl=pos.sl, tp1=pos.tp1, tp2=pos.tp2,
                    size=pos.size,
                )
            elif event_type == "tp1_hit":
                self.notifier.notify_tp1_hit(
                    symbol=pos.symbol, direction=pos.direction, entry=pos.entry,
                )
            elif event_type == "position_closed":
                self.notifier.notify_position_closed(
                    symbol=pos.symbol, direction=pos.direction,
                    entry=pos.entry, exit_price=pos.exit_price or 0.0,
                    pnl_usdt=pos.pnl_usdt or 0.0,
                    exit_reason=pos.exit_reason or "UNKNOWN",
                    size=pos.size,
                )
            elif event_type == "position_rolled_back":
                # PR B — post-placement verify force-closed the entry because SL
                # could not be confirmed. Surface it as a close alert so the
                # operator sees the forced flatten immediately (not just in logs).
                self.notifier.notify_position_closed(
                    symbol=pos.symbol, direction=pos.direction,
                    entry=pos.entry, exit_price=pos.exit_price or 0.0,
                    pnl_usdt=pos.pnl_usdt or 0.0,
                    exit_reason="VERIFY_ROLLBACK (SL unconfirmed)",
                    size=pos.size,
                )
        except Exception as e:
            log.warning(f"Telegram notification dispatch failed: {e}")

        # Persist to DB (best-effort, fire-and-forget cross-thread)
        if not self.loop:
            return  # Test env or pre-startup — skip persistence
        try:
            if event_type == "position_opened":
                asyncio.run_coroutine_threadsafe(
                    db.record_trade_open(
                        symbol=pos.symbol, direction=pos.direction,
                        entry=pos.entry, sl=pos.sl, tp1=pos.tp1, tp2=pos.tp2,
                        size=pos.size, binance_order_id=pos.order_id or None,
                        trace_id=getattr(pos, "trace_id", None),
                        bar_ts_ms=getattr(pos, "bar_ts_ms", None),
                        # SMC v2 telemetry (PR #S5) — defensive getattr so legacy
                        # in-flight Position instances at deploy-time still
                        # serialize cleanly; v1 callers pass None throughout.
                        entry_setup_source=getattr(pos, "entry_setup_source", None),
                        tp1_target_type=getattr(pos, "tp1_target_type", None),
                        tp2_target_type=getattr(pos, "tp2_target_type", None),
                        bars_to_pullback=getattr(pos, "bars_to_pullback", None),
                        # Phase 3.2 warehouse telemetry — market-state at entry
                        initial_sl=getattr(pos, "sl", None),
                        adx_value=getattr(pos, "adx_value", None),
                        atr_value=getattr(pos, "atr_value", None),
                        funding_rate=getattr(pos, "funding_rate", None),
                        confluence_details=getattr(pos, "confluence_details", None),
                    ),
                    self.loop,
                )
            elif event_type == "position_closed":
                pnl_pct = ((pos.exit_price - pos.entry) / pos.entry * 100) if pos.direction == "LONG" else \
                          ((pos.entry - pos.exit_price) / pos.entry * 100)
                asyncio.run_coroutine_threadsafe(
                    db.record_trade_close(
                        symbol=pos.symbol, exit_price=pos.exit_price,
                        pnl_usdt=pos.pnl_usdt, pnl_pct=pnl_pct,
                        reason=pos.exit_reason,
                        trace_id=getattr(pos, "trace_id", None),
                        mae_pct=getattr(pos, "mae_pct", None),
                        mfe_pct=getattr(pos, "mfe_pct", None),
                    ),
                    self.loop,
                )
                # Audit dispatch — fire-and-forget, runs AFTER record_trade_close.
                # Delays 2s to let the DB row commit before audit's tier-1
                # trace_id query runs. Engine itself never raises.
                asyncio.run_coroutine_threadsafe(
                    self._audit_after_delay(pos),
                    self.loop,
                )
        except Exception as e:
            log.warning(f"DB persist failed: {e}")

    async def _audit_after_delay(self, pos: Position) -> None:
        """Run audit AFTER record_trade_close commits.

        Delay is small (2s) — enough for the prior `record_trade_close`
        coroutine to flush its INSERT, not enough to materially delay anything.

        AuditEngine.score_closed_trade itself never raises, so this wrapper
        is mostly a sequencing primitive.
        """
        try:
            await asyncio.sleep(2.0)
            await self.audit_engine.score_closed_trade(pos)
        except Exception as e:
            log.warning(f"Audit dispatch failed for {pos.symbol}: {e}")

    def _sync_reconciled_close_to_logical(self, pos: Position) -> None:
        """Exchange-side reconcile kapanışını mantıksal lifecycle + breaker'a
        idempotent senkronize et.

        Neden: reconcile() borsadaki TP/SL fill'lerini yakalar ama bu kapanışlar
        CircuitBreaker'ın daily/consecutive-loss sayaçlarına akmıyordu (breaker
        sadece lifecycle-kapanışlarını görüyordu). Bu, gerçek SL serilerinde
        breaker'ı kör bırakıyordu (Y2 bulgusu).

        Idempotent: dedup tamamen LOGICAL pozisyonun _reported_to_breaker
        flag'i üzerinden yürür — STEP5 (safe_orchestrator:741-746) ile PAYLAŞILAN
        tek doğruluk kaynağı. record_trade ve flag, açık logical eşleşmesi
        bulunan blokun İÇİNDE yaşar; aksi halde STEP5'in zaten kapatıp saydığı
        bir kapanış reconcile tarafından İKİNCİ kez sayılırdı (cross-path
        double-count — Y2 düzeltmesini bozar, breaker'ı erken trip ettirir).

        Döngü sırası (reconcile ÖNCE, sonra STEP5) bunu doğru + kayıpsız kılar:
        reconcile logical'ı hâlâ AÇIK görür → bir kez kaydeder + logical'ı
        flag'ler → STEP5 sonradan flag'i görüp atlar.
        """
        if self.orch is None:
            return
        try:
            logical = self.orch.lifecycle.same_direction_open(pos.symbol, pos.direction)
            if logical is not None and not getattr(logical, "_reported_to_breaker", False):
                self.orch.lifecycle.close_position(logical, pos.exit_price, pos.exit_reason)
                self.orch._journal_record_exit(logical, pos.exit_price, pos.exit_reason)
                self.orch.breaker.record_trade(pos.pnl_usdt)
                logical._reported_to_breaker = True
                log.info(
                    f"Reconcile→breaker sync: {pos.symbol} {pos.direction} "
                    f"pnl=${pos.pnl_usdt:.2f} reason={pos.exit_reason}"
                )
            # else: açık logical eşleşme yok → ya STEP5 zaten kapatıp saydı
            # (logical flag set; same_direction_open kapalı pos için None döner),
            # ya da bot-takipli bir trade hiç değildi (orphan/manual). Her iki
            # durumda da breaker'a KAYDETME — cross-path double-count'u önler.
        except Exception as e:
            log.warning(f"Reconcile→breaker sync failed for {pos.symbol}: {e}")

    async def _persist_close(self, pos: Position) -> None:
        """Async DB write for reconciled closes (already emitted in OrderManager)."""
        pnl_pct = ((pos.exit_price - pos.entry) / pos.entry * 100) if pos.direction == "LONG" else \
                  ((pos.entry - pos.exit_price) / pos.entry * 100)
        await db.record_trade_close(
            symbol=pos.symbol, exit_price=pos.exit_price,
            pnl_usdt=pos.pnl_usdt, pnl_pct=pnl_pct, reason=pos.exit_reason,
            trace_id=getattr(pos, "trace_id", None),
            mae_pct=getattr(pos, "mae_pct", None),
            mfe_pct=getattr(pos, "mfe_pct", None),
        )
        # Task 2: exchange-side kapanışı breaker'a idempotent bildir (Y2 fix)
        self._sync_reconciled_close_to_logical(pos)

    # ─────────────────────────────────────────────────────────────
    # Public API for /api endpoints
    # ─────────────────────────────────────────────────────────────

    def status_snapshot(self) -> dict:
        breaker = "UNKNOWN"
        if self.orch:
            try:
                breaker = self.orch.breaker.status.state.value
            except Exception:
                pass
        return {
            "running": self.running and not self.stopped,
            "cycle_count": self.cycle_count,
            "last_cycle_at": self.last_cycle_at,
            "last_cycle_duration_ms": self.last_cycle_duration_ms,
            "breaker_state": breaker,
            "open_positions": len(self.order_mgr.positions) if self.order_mgr else 0,
            "config_path": os.environ.get("EFLOUD_CONFIG_PATH", CONFIG_PATH_DEFAULT),
            "testnet": self.cfg.get("exchange", {}).get("testnet", True) if self.cfg else True,
            "dry_run": self.cfg.get("operation", {}).get("dry_run", True) if self.cfg else True,
            "last_error": self.last_error,
        }

    @staticmethod
    def _now_iso() -> str:
        from datetime import datetime, timezone
        return datetime.now(timezone.utc).isoformat()

    async def _run_sentiment_loop(self) -> None:
        """Periodically calls Gemini AI macro sentiment analyzer every 4 hours."""
        from engine.ai.sentiment import fetch_and_save_sentiment
        
        # Give some initial delay on startup so it doesn't block the main trading thread startup
        await asyncio.sleep(5.0)
        
        while not self.stopped:
            api_key = os.environ.get("GEMINI_API_KEY") or self.cfg.get("gemini", {}).get("api_key")
            if not api_key:
                log.warning("⚠️ GEMINI_API_KEY not configured. Skipping periodic sentiment analysis update.")
            else:
                try:
                    log.info("♻️ Triggering Gemini AI macro sentiment analysis...")
                    res = await fetch_and_save_sentiment(api_key=api_key)
                    log.info(f"✅ AI Sentiment updated: {res.get('macro_sentiment', 'NEUTRAL')} (FGI: {res.get('fear_and_greed', 50)})")
                    # reload orchestrator's sentiment state in real time!
                    if self.orch:
                        self.orch.load_ai_sentiment()
                except Exception as e:
                    log.error(f"❌ Error updating Gemini AI sentiment: {e}", exc_info=True)
            
            # Wait 4 hours (14400 seconds), checking every 10 seconds for stopped flag
            for _ in range(1440):
                if self.stopped:
                    break
                await asyncio.sleep(10)


# Module singleton
runner = BotRunner()
