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

from backend.db import db
from backend.events import bus
from backend.notifications import TelegramNotifier
from engine import SafeOrchestrator
from engine.notifications import NotificationManager
from engine.permissions import PermissionManager
from engine.safety import MainnetGuard
from engine.universe import SymbolUniverse
from exchange import BinanceClient, OrderManager, Position
from main import resolve_credentials, validate_config

log = logging.getLogger("efloud.runner")

CONFIG_PATH_DEFAULT = "configs/config.phase2_micro.yaml"


class BotRunner:
    def __init__(self) -> None:
        self.task: Optional[asyncio.Task] = None
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
        self.cycle_count = 0
        self.last_cycle_at: Optional[str] = None
        self.last_cycle_duration_ms: int = 0
        self.running = False
        self.stopped = False
        self.last_error: Optional[str] = None

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

        # Leverage + margin mode setup
        if ex_cfg["market_type"] == "futures" and api_key and not self.cfg["operation"].get("dry_run", True):
            margin_mode = ex_cfg.get("margin_mode", "ISOLATED").upper()
            tradeable = (permission_mgr.get_tradeable_symbols() if permission_mgr else symbols)
            for sym in tradeable:
                try:
                    self.client.set_margin_mode(sym, margin_mode)
                    self.client.set_leverage(sym, ex_cfg.get("leverage", 3))
                except Exception as e:
                    log.warning(f"Setup failed for {sym}: {e}")

        notif_mgr = NotificationManager(channels=["log"])  # WS push üzerinden ayrıca yapılır
        state_dir = self.cfg["operation"].get("state_dir", "./state")

        # OrderManager FIRST — orchestrator'a inject edilecek.
        # state_dir same as orchestrator's so restart restores order_mgr.positions
        # (prevents duplicate SL+TP1+TP2 stacking on Binance — 2026-05-08 bug).
        self.order_mgr = OrderManager(
            self.client, dry_run=self.cfg["operation"]["dry_run"],
            on_position_change=self._on_position_change,
            state_dir=state_dir,
        )

        self.orch = SafeOrchestrator(
            self.cfg, state_dir=state_dir,
            permission_mgr=permission_mgr, notification_mgr=notif_mgr,
            order_manager=self.order_mgr,  # ← borsaya gerçek emir göndermek için
        )

        # Capture the running loop so executor-thread callbacks can schedule DB writes
        self.loop = asyncio.get_running_loop()

        # Spawn the worker task
        self.task = asyncio.create_task(self._run_loop(), name="bot_runner")
        self.running = True
        log.info("🚀 Bot runner started")
        bus.publish("bot_started", config_path=cfg_path)
        await db.log_audit("bot_started", {"config_path": cfg_path})

    async def stop(self) -> None:
        self.stopped = True
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
                    ),
                    self.loop,
                )
        except Exception as e:
            log.warning(f"DB persist failed: {e}")

    async def _persist_close(self, pos: Position) -> None:
        """Async DB write for reconciled closes (already emitted in OrderManager)."""
        pnl_pct = ((pos.exit_price - pos.entry) / pos.entry * 100) if pos.direction == "LONG" else \
                  ((pos.entry - pos.exit_price) / pos.entry * 100)
        await db.record_trade_close(
            symbol=pos.symbol, exit_price=pos.exit_price,
            pnl_usdt=pos.pnl_usdt, pnl_pct=pnl_pct, reason=pos.exit_reason,
            trace_id=getattr(pos, "trace_id", None),
        )

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


# Module singleton
runner = BotRunner()
