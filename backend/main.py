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
from backend.ws import websocket_handler
from main import load_dotenv  # reuse parent project's .env loader

# Load .env (prefer system env over .env values)
load_dotenv()

logging.basicConfig(
    level=os.environ.get("LOG_LEVEL", "INFO"),
    format="%(asctime)s | %(name)-22s | %(levelname)-5s | %(message)s",
)
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
    if os.environ.get("EFLOUD_AUTOSTART", "1") == "1":
        try:
            await runner.start()
        except Exception as e:
            log.error(f"Bot runner startup failed: {e}", exc_info=True)
    else:
        log.info("Autostart disabled (EFLOUD_AUTOSTART=0) — start bot via /api/bot/start")

    yield
    # Shutdown
    log.info("🔴 App shutdown")
    await runner.stop()
    await db.close()


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


@app.websocket("/ws")
async def ws_endpoint(websocket: WebSocket):
    await websocket_handler(websocket)


@app.get("/healthz")
async def healthz() -> dict:
    """Liveness probe (Railway / uptime monitoring). No auth."""
    return {
        "status": "ok",
        "bot_running": runner.running and not runner.stopped,
        "subscribers": __import__("backend.events", fromlist=["bus"]).bus.subscriber_count,
    }


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
