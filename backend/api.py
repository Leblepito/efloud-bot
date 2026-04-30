"""REST API endpoints.

All endpoints under /api. /api/login is public; rest require auth.
"""
from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel

from backend.auth import login as auth_login, logout as auth_logout, require_auth
from backend.bot_runner import runner
from backend.db import db

log = logging.getLogger("efloud.api")

router = APIRouter(prefix="/api")


class LoginBody(BaseModel):
    password: str


@router.post("/login")
async def login(body: LoginBody, request: Request, response: Response) -> dict:
    if auth_login(request, response, body.password):
        return {"ok": True}
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid password"
    )


@router.post("/logout", dependencies=[Depends(require_auth)])
async def logout(response: Response) -> dict:
    auth_logout(response)
    return {"ok": True}


@router.get("/status", dependencies=[Depends(require_auth)])
async def status_endpoint() -> dict:
    return runner.status_snapshot()


@router.get("/positions", dependencies=[Depends(require_auth)])
async def positions() -> list[dict]:
    if not runner.order_mgr or not runner.client:
        return []
    out = []
    for p in runner.order_mgr.positions:
        try:
            cur_price = runner.client.get_price(p.symbol)
        except Exception:
            cur_price = p.entry
        is_long = p.direction == "LONG"
        unrealized = ((cur_price - p.entry) / p.entry * 100) if is_long else \
                     ((p.entry - cur_price) / p.entry * 100)
        out.append({
            "symbol": p.symbol,
            "direction": p.direction,
            "entry": p.entry,
            "sl": p.sl,
            "tp1": p.tp1,
            "tp2": p.tp2,
            "size": p.size,
            "current_price": cur_price,
            "unrealized_pct": round(unrealized, 3),
            "tp1_hit": p.tp1_hit,
            "opened_at": p.opened_at,
        })
    return out


@router.get("/history", dependencies=[Depends(require_auth)])
async def history(limit: int = 50) -> list[dict]:
    return await db.fetch_recent_trades(limit=min(limit, 500))


@router.get("/equity", dependencies=[Depends(require_auth)])
async def equity(days: int = 7) -> list[dict]:
    return await db.fetch_equity_history(days=min(max(days, 1), 90))


@router.post("/kill-switch", dependencies=[Depends(require_auth)])
async def kill_switch() -> dict:
    if not runner.order_mgr:
        raise HTTPException(status_code=503, detail="Bot not running")
    closed = runner.order_mgr.kill_switch()
    # Trip the breaker so bot doesn't open new positions
    if runner.orch:
        try:
            runner.orch.breaker._halt("Manual kill switch (frontend)")
        except Exception:
            pass
    await db.log_audit("kill_switch_activated", {"closed_positions": closed})
    return {"ok": True, "closed": closed}


@router.get("/config", dependencies=[Depends(require_auth)])
async def config() -> dict:
    if not runner.cfg:
        return {}
    cfg = runner.cfg
    return {
        "config_path": runner.status_snapshot()["config_path"],
        "exchange": {
            "testnet": cfg.get("exchange", {}).get("testnet"),
            "leverage": cfg.get("exchange", {}).get("leverage"),
            "margin_mode": cfg.get("exchange", {}).get("margin_mode"),
            "market_type": cfg.get("exchange", {}).get("market_type"),
        },
        "operation": {
            "dry_run": cfg.get("operation", {}).get("dry_run"),
            "check_interval_sec": cfg.get("operation", {}).get("check_interval_sec"),
        },
        "risk": {
            "risk_per_trade_pct": cfg.get("risk", {}).get("risk_per_trade_pct"),
            "max_open_positions": cfg.get("risk", {}).get("max_open_positions"),
            "min_rr": cfg.get("risk", {}).get("min_rr"),
            "min_confluence": cfg.get("risk", {}).get("min_confluence"),
            "position_size_calculation": cfg.get("risk", {}).get("position_size_calculation", "legacy"),
        },
        "safety": {
            "daily_loss_limit_pct": cfg.get("safety", {}).get("daily_loss_limit_pct"),
            "weekly_drawdown_limit_pct": cfg.get("safety", {}).get("weekly_drawdown_limit_pct"),
            "starting_balance": cfg.get("safety", {}).get("starting_balance"),
            "emergency_balance_threshold": cfg.get("safety", {}).get("emergency_balance_threshold"),
        },
        "symbols": cfg.get("symbols", {}).get("fixed_core", []),
    }
