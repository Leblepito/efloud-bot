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
    """Live positions fetched directly from Binance, enriched with bot metadata if tracked."""
    if not runner.client or not runner.order_mgr:
        return []
    try:
        # Fetch actual live positions on Binance
        bn_positions = runner.client.get_open_positions()
    except Exception as e:
        log.warning(f"Failed to fetch live positions from Binance: {e}")
        # Fallback to empty if exchange is temporarily unreachable
        bn_positions = []

    out = []
    # Strip CCXT contract notation for comparisons: 'FIL/USDT:USDT' -> 'FIL/USDT'
    from exchange import _strip_contract_suffix

    # Create a lookup map of local bot positions
    local_pos_map = {
        _strip_contract_suffix(p.symbol): p for p in runner.order_mgr.positions
    }

    # If we successfully fetched live positions, use them as the primary source of truth
    if bn_positions:
        for bp in bn_positions:
            ccxt_symbol = bp.get("symbol", "")
            base_symbol = _strip_contract_suffix(ccxt_symbol)
            
            contracts = float(bp.get("contracts", 0))
            entry_price = float(bp.get("entryPrice", 0) or 0)
            mark_price = float(bp.get("markPrice", 0) or 0)
            side = str(bp.get("side", "")).upper()  # "LONG" or "SHORT"
            if side == "LONG":
                direction = "LONG"
            elif side == "SHORT":
                direction = "SHORT"
            else:
                direction = "LONG" if contracts > 0 else "SHORT"
                
            # Check if this is tracked locally by the bot
            local_pos = local_pos_map.get(base_symbol)
            
            if local_pos:
                sl = local_pos.sl
                tp1 = local_pos.tp1
                tp2 = local_pos.tp2
                tp1_hit = local_pos.tp1_hit
                opened_at = local_pos.opened_at
            else:
                # Untracked/Orphan position on the exchange (manual position)
                sl = 0.0
                tp1 = 0.0
                tp2 = None
                tp1_hit = False
                opened_at = "" # Will show as blank/untracked

            # Calculate live unrealized PnL percentage
            if entry_price > 0:
                is_long = direction == "LONG"
                unrealized = ((mark_price - entry_price) / entry_price * 100) if is_long else \
                             ((entry_price - mark_price) / entry_price * 100)
            else:
                unrealized = 0.0

            out.append({
                "symbol": base_symbol,
                "direction": direction,
                "entry": entry_price,
                "sl": sl,
                "tp1": tp1,
                "tp2": tp2 if tp2 is not None else 0.0,
                "size": contracts,
                "current_price": mark_price,
                "unrealized_pct": round(unrealized, 3),
                "tp1_hit": tp1_hit,
                "opened_at": opened_at,
            })
    else:
        # Fallback to local positions list if exchange is temporarily unreachable (graceful degradation)
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
                "tp2": p.tp2 if p.tp2 is not None else 0.0,
                "size": p.size,
                "current_price": cur_price,
                "unrealized_pct": round(unrealized, 3),
                "tp1_hit": p.tp1_hit,
                "opened_at": p.opened_at,
            })
    return out


@router.get("/orders", dependencies=[Depends(require_auth)])
async def orders() -> list[dict]:
    """Open orders on Binance (limit / TP / SL) — live fetch.

    Returns [] when bot client is not initialized (worker hasn't started).
    Returns [] on CCXT error and logs a warning so the dashboard stays
    functional through transient exchange/network issues.
    """
    if not runner.client:
        return []
    try:
        raw = runner.client.exchange.fetch_open_orders()
    except Exception as e:
        log.warning(f"Open orders fetch failed: {e}")
        return []
    out: list[dict] = []
    for o in raw:
        info = o.get("info") or {}
        out.append({
            "id": str(o.get("id", "")),
            "symbol": o.get("symbol", ""),
            "type": (o.get("type") or info.get("type") or "").lower(),
            "side": (o.get("side") or info.get("side") or "").lower(),
            "price": o.get("price"),
            "stop_price": o.get("stopPrice") or info.get("stopPrice"),
            "amount": o.get("amount"),
            "filled": o.get("filled"),
            "remaining": o.get("remaining"),
            "reduce_only": bool(o.get("reduceOnly") or info.get("reduceOnly") or False),
            "status": o.get("status", ""),
            "timestamp": o.get("timestamp"),
        })
    return out


@router.get("/history", dependencies=[Depends(require_auth)])
async def history(limit: int = 50) -> list[dict]:
    return await db.fetch_recent_trades(limit=min(limit, 500))


@router.get("/equity", dependencies=[Depends(require_auth)])
async def equity(days: int = 7) -> list[dict]:
    return await db.fetch_equity_history(days=min(max(days, 1), 90))


@router.get("/ai/sentiment", dependencies=[Depends(require_auth)])
async def ai_sentiment() -> dict:
    """Yapay zeka makro duygu durumunu local registry'den yukler."""
    import json
    from pathlib import Path
    try:
        registry_path = Path("./state/ai_sentiment_registry.json")
        if registry_path.exists():
            with open(registry_path, encoding="utf-8") as f:
                return json.load(f)
    except Exception:
        pass
    return {
        "macro_sentiment": "NEUTRAL",
        "confidence_score": 1.0,
        "fear_and_greed": 50.0,
        "bitcoin_trend": "NEUTRAL",
        "reasoning": "Duygu durumu verisi yuklenemedi (fallback)."
    }


@router.post("/bot/start", dependencies=[Depends(require_auth)])
async def bot_start() -> dict:
    if runner.running and not runner.stopped:
        return {"ok": True, "already_running": True, "running": True}
    await runner.start()
    return {
        "ok": True,
        "running": runner.running and not runner.stopped,
        "last_error": runner.last_error,
    }


@router.post("/bot/stop", dependencies=[Depends(require_auth)])
async def bot_stop() -> dict:
    await runner.stop()
    return {"ok": True, "running": False}


@router.post("/bot/restart", dependencies=[Depends(require_auth)])
async def bot_restart() -> dict:
    await runner.restart()
    return {
        "ok": True,
        "running": runner.running and not runner.stopped,
        "last_error": runner.last_error,
    }


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


@router.post("/breaker/reset", dependencies=[Depends(require_auth)])
async def breaker_reset(reason: str = "manual via dashboard") -> dict:
    """Manually reset the circuit breaker (clears HALTED/TRIPPED state).

    HALTED requires manual reset by design — operator must acknowledge that the
    triggering condition (emergency balance, weekly DD) has been investigated
    before resuming. Does NOT bypass breaker re-trip on next cycle if conditions
    still apply.
    """
    if not runner.orch:
        raise HTTPException(status_code=503, detail="Bot not running")
    prior_state = runner.orch.breaker.status.state.value
    prior_reason = runner.orch.breaker.status.reason
    runner.orch.breaker.manual_reset(reason)
    await db.log_audit(
        "breaker_reset",
        {"prior_state": prior_state, "prior_reason": prior_reason, "reset_reason": reason},
    )
    return {
        "ok": True,
        "prior_state": prior_state,
        "prior_reason": prior_reason,
        "current_state": runner.orch.breaker.status.state.value,
    }


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
