"""FastAPI app — single-process model.

Lifespan:
- Startup: load .env, connect DB pool, start bot worker
- Shutdown: stop bot worker, close DB pool
"""
from __future__ import annotations

import logging
import os
import sys
from contextlib import asynccontextmanager
from pathlib import Path

# Make project root importable
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from fastapi import FastAPI, WebSocket
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from backend.api import router as api_router
from backend.bot_runner import runner
from backend.db import db
from backend.healthz import health_router, configure as configure_healthz
from backend.ws import websocket_handler
from main import load_dotenv  # reuse parent project's .env loader

# Load .env (prefer system env over .env values)
load_dotenv()

if os.environ.get("EFLOUD_LOGGING_FORMAT", "").lower() == "json":
    from utils.logging import configure_json_logging
    _level = getattr(logging, os.environ.get("LOG_LEVEL", "INFO").upper(), logging.INFO)
    configure_json_logging(level=_level)
else:
    logging.basicConfig(
        level=os.environ.get("LOG_LEVEL", "INFO"),
        format="%(asctime)s | %(name)-22s | %(levelname)-5s | %(message)s",
    )

# R-13 (2026-07-18): overseer/alerter'ın taill'lediği log DOSYASI backend
# yolunda hiç yazılmıyordu (yukarıdaki iki dal da stdout-only) — compose'taki
# EFLOUD_LOG_FILE'ın okuyanı vardı, yazanı yoktu. Env set ise dosyaya HER
# ZAMAN JSON yazan rotating handler eklenir (stdout formatı değişmez);
# env yoksa davranış birebir eski (default-OFF).
_log_file = os.environ.get("EFLOUD_LOG_FILE", "").strip()
if _log_file:
    try:
        from utils.logging import attach_json_file_handler
        attach_json_file_handler(_log_file)
    except Exception as _e:  # dosya açılamazsa app yine ayağa kalkmalı
        logging.getLogger("efloud.app").error(
            f"EFLOUD_LOG_FILE handler kurulamadı ({_log_file}): {_e}")

log = logging.getLogger("efloud.app")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    log.info("🟢 App startup")
    await db.connect()

    # Optional auto-migration (run pending SQL migrations against DATABASE_URL)
    if os.environ.get("EFLOUD_AUTO_MIGRATE", "0") == "1":
        try:
            from backend.migrate import run_pending
            await run_pending()
        except Exception as e:
            log.error(f"Auto-migrate failed: {e}", exc_info=True)

    # Autostart bot — opt-out via EFLOUD_AUTOSTART=0 (Railway: manual control)
    # _autostart_failed is read by _trading_started() below: a start that was
    # ASKED for and then blew up is a fault autoheal can genuinely retry, unlike
    # "operator hasn't pressed Start yet". Mutable dict because the getter is a
    # closure defined further down and must observe later writes.
    _autostart_failed = {"v": False}
    if os.environ.get("EFLOUD_AUTOSTART", "1") == "1":
        try:
            await runner.start()
        except Exception as e:
            _autostart_failed["v"] = True
            log.error(f"Bot runner startup failed: {e}", exc_info=True)
    else:
        log.info("Autostart disabled (EFLOUD_AUTOSTART=0) — start bot via /api/bot/start")

    # Start publishing worker (processes approved drafts → X/Instagram/YouTube)
    try:
        from backend.social.publishing_worker import start_worker
        await start_worker()
        log.info("✅ Publishing worker started")
    except Exception as e:
        log.error(f"Publishing worker startup failed: {e}", exc_info=True)

    # === Aşama 2 Step 2 healthz wiring (ORDER MATTERS) ===
    # Step 1: ensure `runner` is constructed and has runtime_state
    #         (BotRunner.__init__ from Task 3.1 creates runner.runtime_state eagerly).
    assert runner.runtime_state is not None, "BotRunner did not initialize runtime_state"

    # Step 2: configure the healthz router with concrete dependencies.
    def _breaker_halted() -> bool:
        try:
            from engine.safety.breaker import BreakerState
            if runner.orch is None:
                return False  # bot idle (not yet started); breaker can't be HALTED yet
            return runner.orch.breaker.status.state == BreakerState.HALTED
        except Exception:
            return False

    def _trading_started() -> bool:
        """Is the trading loop meant to be running right now?

        False in exactly two situations, both of them deliberate: the container
        came up with EFLOUD_AUTOSTART=0 and nobody has pressed Start yet, or the
        operator pressed Stop. Neither is fixable by restarting the container,
        so healthz answers 200 "suspended" and autoheal stands down.

        NOT False when the bot dies mid-run: BotRunner sets `running` True at the
        end of a successful start and clears it only inside stop(); _run_loop's
        except clause records fatal_exception_state and keeps looping without
        touching the flag. A crashed bot therefore still reports True here, still
        has a stale tick, and still gets its 503 + autoheal restart.

        NOT False either when autostart was requested and raised. There
        `running` and `stopped` are both still at their constructor value False,
        which is indistinguishable from "never asked to start" — so the explicit
        _autostart_failed flag carries that case, and a boot-time transient
        (exchange unreachable, DB not up yet) keeps its old 503 + retry path.
        """
        try:
            if bool(runner.stopped):
                return False  # operator pressed Stop — deliberate
            if bool(runner.running):
                return True
            # running=False, stopped=False → start never completed.
            return bool(_autostart_failed["v"])
        except Exception:
            return True  # fail-safe: unknown state must not disarm autoheal

    configure_healthz(runner.runtime_state, _breaker_halted, _trading_started)

    # Step 3: Aşama 2 Step 2 crash-loop counter
    rs = runner.runtime_state
    snap = rs.snapshot()
    if snap["fatal_exception_state"]:
        rs.increment_crash()
        log.warning(
            "💥 Previous run exited with fatal_exception_state=True; "
            f"crash_count now {rs.snapshot()['crash_count']}"
        )
    else:
        rs.reset_crash_count()

    # Step 4: yield to FastAPI for request serving (existing `yield` line follows).
    yield
    # Shutdown
    log.info("🔴 App shutdown")
    await runner.stop()
    await db.close()

    # Stop publishing worker
    try:
        from backend.social.publishing_worker import stop_worker
        await stop_worker()
        log.info("✅ Publishing worker stopped")
    except Exception as e:
        log.error(f"Publishing worker shutdown failed: {e}", exc_info=True)


app = FastAPI(
    title="Efloud Bot Backend",
    description="FastAPI gateway for Efloud SMC trading bot",
    version="2.2.0",
    lifespan=lifespan,
)

# CORS — frontend Vercel domain
allowed_origins = os.environ.get("ALLOWED_ORIGINS", "http://localhost:3000").split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in allowed_origins if o.strip()],
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)

app.include_router(api_router)
app.include_router(health_router)


@app.websocket("/ws")
async def ws_endpoint(websocket: WebSocket):
    await websocket_handler(websocket)


# ─────────────────────────────────────────────────────────────────
# Static frontend (single-service deploy: FastAPI serves Next.js export)
#
# Build process: `cd frontend && npm run build` produces `frontend/out/`
# (Next.js static export — HTML + JS chunks). FastAPI mounts it at /.
# REST routes (/api/*), WS (/ws), /healthz are registered above and take
# priority over the static mount because FastAPI matches routes top-down.
# ─────────────────────────────────────────────────────────────────

FRONTEND_OUT = PROJECT_ROOT / "frontend" / "out"

if FRONTEND_OUT.exists():
    log.info(f"📂 Mounting static frontend from {FRONTEND_OUT}")
    # Next.js exported with trailingSlash:true so /login → out/login/index.html.
    # StaticFiles(html=True) auto-resolves directory + index.html.
    app.mount("/", StaticFiles(directory=str(FRONTEND_OUT), html=True), name="frontend")
else:
    log.warning(f"⚠️  Frontend bundle not found at {FRONTEND_OUT} — only API endpoints active")

    @app.get("/")
    async def _api_only_root() -> dict:
        return {"service": "efloud-bot-backend", "version": "2.2.0", "ui": "/docs"}
