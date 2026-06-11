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

    # Create a lookup map of local bot positions by symbol and direction
    local_pos_map = {
        (_strip_contract_suffix(p.symbol), p.direction): p for p in runner.order_mgr.positions
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
                
            # Check if this is tracked locally by the bot by symbol and direction
            local_pos = local_pos_map.get((base_symbol, direction))
            
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

            # Calculate live unrealized PnL percentage and USDT value
            if entry_price > 0:
                is_long = direction == "LONG"
                unrealized = ((mark_price - entry_price) / entry_price * 100) if is_long else \
                             ((entry_price - mark_price) / entry_price * 100)
                unrealized_usdt = (contracts * (mark_price - entry_price)) if is_long else \
                                  (contracts * (entry_price - mark_price))
            else:
                unrealized = 0.0
                unrealized_usdt = 0.0

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
                "unrealized_usdt": round(unrealized_usdt, 2),
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
            unrealized_usdt = (p.size * (cur_price - p.entry)) if is_long else \
                              (p.size * (p.entry - cur_price))
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
                "unrealized_usdt": round(unrealized_usdt, 2),
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


def read_journal_history(journal_path: str, limit: int = 100) -> list[dict]:
    """Read closed trades from trade_journal.jsonl, newest first.

    DB-less fallback for /history and /equity. A trade is 'closed' when it has
    an exit_timestamp. Returns [] when the file is absent or unreadable — never
    raises into the request handler.
    """
    import json as _json
    import os as _os
    if not journal_path or not _os.path.exists(journal_path):
        return []
    rows: list[dict] = []
    try:
        with open(journal_path, "r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = _json.loads(line)
                except _json.JSONDecodeError:
                    continue
                if obj.get("exit_timestamp"):
                    mapped = dict(obj)
                    mapped.update({
                        "id": obj.get("trade_id"),
                        "entry": obj.get("entry_price"),
                        "exit": obj.get("exit_price"),
                        "sl": obj.get("sl_initial"),
                        "tp1": obj.get("tp1_initial"),
                        "tp2": obj.get("tp2_initial"),
                        "size": obj.get("position_size"),
                        "pnl_usdt": obj.get("realized_pnl"),
                        "pnl_pct": obj.get("realized_pnl_pct"),
                        "reason": obj.get("exit_reason"),
                        "opened_at": obj.get("entry_timestamp"),
                        "closed_at": obj.get("exit_timestamp"),
                        "confluence": obj.get("confluence_score"),
                        "mae_pct": obj.get("max_adverse_excursion_pct"),
                        "mfe_pct": obj.get("max_favorable_excursion_pct"),
                        "initial_sl": obj.get("sl_initial"),
                    })
                    rows.append(mapped)
    except OSError:
        return []
    rows.sort(key=lambda r: r.get("exit_timestamp", ""), reverse=True)
    return rows[:limit]


def _journal_path() -> str:
    import os as _os
    return _os.environ.get("EFLOUD_TRADE_JOURNAL", "./state/trade_journal.jsonl")


@router.get("/history", dependencies=[Depends(require_auth)])
async def history(limit: int = 50) -> list[dict]:
    trades = await db.fetch_recent_trades(limit=min(limit, 500))
    if not trades:
        trades = read_journal_history(_journal_path(), limit=min(limit, 500))
    return trades


@router.get("/equity", dependencies=[Depends(require_auth)])
async def equity(days: int = 7) -> list[dict]:
    series = await db.fetch_equity_history(days=min(max(days, 1), 90))
    if not series:
        # Derive a cumulative-PnL curve from reconciled journal closes.
        rows = list(reversed(read_journal_history(_journal_path(), limit=1000)))
        cum = 0.0
        series = []
        for r in rows:
            cum += float(r.get("realized_pnl", 0) or 0)
            series.append({"t": r.get("exit_timestamp"), "equity": cum})
    return series


@router.get("/reports/monthly", dependencies=[Depends(require_auth)])
async def reports_monthly(window_days: int = 30) -> dict:
    """Aylık statement (T-013) — operatör-only İÇ tüketim, journal-first.

    Müşteri-yüzlü yayın T-012/T-014 statik snapshot yolundan yapılır; bu
    endpoint hiçbir zaman public'e açılmaz (UR-003 pini).
    """
    from datetime import datetime, timezone as _tz

    from ops.daily_report.monthly import (
        MAX_WINDOW_DAYS,
        build_monthly_statement,
        read_journal_closed_trades,
    )

    days = min(max(window_days, 1), MAX_WINDOW_DAYS)
    now_utc = datetime.now(_tz.utc)
    trades = read_journal_closed_trades(_journal_path(), now_utc, days)
    return build_monthly_statement(trades, now_utc, days)


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
    halt_persisted = False
    if runner.orch:
        try:
            runner.orch.breaker._halt("Manual kill switch (frontend)")
            # Persist the HALT immediately. _halt() only mutates in-memory status;
            # without this a restart inside the ~30s cycle window (autoheal /
            # redeploy / crash) reloads the stale pre-kill-switch breaker from disk
            # (typically OPEN) and the bot resumes trading, defeating the emergency
            # stop. Mirror the /breaker/reset hardening: disk is authoritative on
            # restore (and survives DB-less prod); the DB mirror is best-effort.
            runner.orch._persist_state()
            await db.upsert_breaker_state(runner.orch.breaker.to_dict())
            halt_persisted = True
        except Exception as e:
            # Positions are already closed; a persist failure must not 500 the
            # emergency stop. Surface it loudly for ops AND in the response so the
            # operator knows the HALT is in-memory only (must not restart before
            # investigating disk).
            log.error(f"kill-switch: breaker HALT persist failed: {e}", exc_info=True)
    await db.log_audit(
        "kill_switch_activated",
        {"closed_positions": closed, "halt_persisted": halt_persisted},
    )
    return {"ok": True, "closed": closed, "persisted": halt_persisted}


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
    # Mirror the now-OPEN state to the DB immediately (best-effort). manual_reset
    # happens outside the trading cycle, so without this the breaker_state mirror
    # would stay HALTED until the next ~30s cycle — and a restart-with-file-loss
    # inside that window would re-apply the stale HALT from the mirror fallback.
    await db.upsert_breaker_state(runner.orch.breaker.to_dict())
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


@router.get("/social/feeds", dependencies=[Depends(require_auth)])
async def social_feeds() -> dict:
    """X (Twitter) ve Telegram gönderilerini test edilebilir helper üzerinden döner."""
    from backend.social.feeds import fetch_social_feeds

    return await fetch_social_feeds()


@router.get("/social/doctrine", dependencies=[Depends(require_auth)])
async def social_doctrine() -> list[dict]:
    """Research-only parsed social doctrine snapshots."""
    from backend.social.reports import build_social_research_snapshot

    return build_social_research_snapshot()["doctrine"]


@router.get("/social/hypotheses", dependencies=[Depends(require_auth)])
async def social_hypotheses() -> list[dict]:
    """Research-only strategy hypotheses derived from parsed social doctrine."""
    from backend.social.reports import build_social_research_snapshot

    return build_social_research_snapshot()["hypotheses"]


@router.get("/social/research-snapshot", dependencies=[Depends(require_auth)])
async def social_research_snapshot() -> dict:
    """Combined social learning snapshot for dashboard Learning Center."""
    from backend.social.reports import build_social_research_snapshot

    return build_social_research_snapshot()


@router.get("/market/funding-rates", dependencies=[Depends(require_auth)])
async def funding_rates() -> list[dict]:
    """Takip listesindeki veya temel coinlerin anlık fonlama oranlarını çeker."""
    symbols = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "TRXUSDT", "XRPUSDT"]
    if runner.universe:
        try:
            resolved = runner.universe.resolve()
            if resolved:
                symbols = [s.replace("/", "").replace(":", "") for s in resolved]
        except Exception:
            pass
            
    import httpx
    funding_rates = []
    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            response = await client.get("https://fapi.binance.com/fapi/v1/premiumIndex")
            if response.status_code == 200:
                premium_data = response.json()
                symbol_set = {sym.replace("/", "").replace(":", "").upper() for sym in symbols}
                for pd in premium_data:
                    sym = pd.get("symbol", "").upper()
                    if sym in symbol_set:
                        funding_rates.append({
                            "symbol": sym,
                            "funding_rate": float(pd.get("lastFundingRate", 0)),
                            "mark_price": float(pd.get("markPrice", 0)),
                            "index_price": float(pd.get("indexPrice", 0)),
                            "next_funding_time": int(pd.get("nextFundingTime", 0))
                        })
    except Exception as e:
        log.warning(f"Failed to fetch live funding rates: {e}")
        
    # Fallback to defaults if empty
    if not funding_rates:
        funding_rates = [
            {"symbol": "BTCUSDT", "funding_rate": 0.0001, "mark_price": 95200.0, "index_price": 95180.0, "next_funding_time": 0},
            {"symbol": "ETHUSDT", "funding_rate": 0.00015, "mark_price": 2520.0, "index_price": 2519.0, "next_funding_time": 0},
            {"symbol": "SOLUSDT", "funding_rate": 0.00022, "mark_price": 142.5, "index_price": 142.4, "next_funding_time": 0},
            {"symbol": "TRXUSDT", "funding_rate": -0.00005, "mark_price": 0.12, "index_price": 0.12, "next_funding_time": 0},
            {"symbol": "XRPUSDT", "funding_rate": 0.0001, "mark_price": 0.58, "index_price": 0.58, "next_funding_time": 0}
        ]
    return funding_rates


@router.get("/market/open-interest", dependencies=[Depends(require_auth)])
async def open_interest(symbol: str = "BTCUSDT") -> dict:
    """Coinglass stili Open Interest geçmişini ve kaldıraç yönünü (leverage trend) çeker."""
    import httpx
    
    clean_symbol = symbol.replace("/", "").replace(":", "").upper()
    if not clean_symbol.endswith("USDT"):
        clean_symbol += "USDT"
        
    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            # 1. Open Interest geçmişini çek (5m period, 30 adet)
            res_oi = await client.get(
                f"https://fapi.binance.com/futures/data/openInterestHist?symbol={clean_symbol}&period=5m&limit=30"
            )
            # 2. Fiyat geçmişini çek (kline 5m, 30 adet)
            res_price = await client.get(
                f"https://fapi.binance.com/fapi/v1/klines?symbol={clean_symbol}&interval=5m&limit=30"
            )
            
            if res_oi.status_code == 200 and res_price.status_code == 200:
                oi_data = res_oi.json()
                price_data = res_price.json()
                
                history = []
                for i in range(min(len(oi_data), len(price_data))):
                    o = oi_data[i]
                    p = price_data[i]
                    history.append({
                        "timestamp": int(o.get("timestamp", 0)),
                        "open_interest": float(o.get("sumOpenInterest", 0)),
                        "open_interest_value": float(o.get("sumOpenInterestValue", 0)),
                        "price": float(p[4])  # close price
                    })
                
                # Trend yönünü hesapla (Price change % vs. Open Interest change % son 5 periyotta)
                trend = "NEUTRAL"
                trend_desc = "Fiyat ve Kaldıraç Dengede"
                trend_color = "zinc"
                
                if len(history) >= 5:
                    current = history[-1]
                    past = history[-5]
                    
                    price_change = (current["price"] - past["price"]) / past["price"] * 100
                    oi_change = (current["open_interest"] - past["open_interest"]) / past["open_interest"] * 100
                    
                    if price_change > 0.05 and oi_change > 0.5:
                        trend = "LONG_BUILDUP"
                        trend_desc = "Güçlü Alıcı Kaldıracı (Long Yığılması)"
                        trend_color = "emerald"
                    elif price_change < -0.05 and oi_change > 0.5:
                        trend = "SHORT_BUILDUP"
                        trend_desc = "Güçlü Satıcı Kaldıracı (Short Yığılması)"
                        trend_color = "rose"
                    elif price_change > 0.05 and oi_change < -0.5:
                        trend = "SHORT_COVERING"
                        trend_desc = "Short Sıkışması / Kapanışı (Yukarı Tepki)"
                        trend_color = "cyan"
                    elif price_change < -0.05 and oi_change < -0.5:
                        trend = "LONG_LIQUIDATION"
                        trend_desc = "Long Tasfiyesi / Kapanışı (Aşağı Çözülüm)"
                        trend_color = "blue"
                
                return {
                    "symbol": clean_symbol,
                    "history": history,
                    "trend": trend,
                    "trend_description": trend_desc,
                    "trend_color": trend_color
                }
    except Exception as e:
        log.warning(f"Failed to fetch open interest or price klines: {e}")
        
    # Fallback to simulated/mock history if Binance API limits or fails
    mock_history = []
    import time
    now_ms = int(time.time() * 1000)
    base_price = 95200.0 if "BTC" in clean_symbol else 2520.0
    base_oi = 24500.0 if "BTC" in clean_symbol else 185000.0
    for idx in range(30):
        t = now_ms - (30 - idx) * 300000
        mock_history.append({
            "timestamp": t,
            "open_interest": base_oi * (1 + 0.002 * idx),
            "open_interest_value": base_oi * base_price * (1 + 0.0025 * idx),
            "price": base_price * (1 + 0.001 * idx)
        })
    return {
        "symbol": clean_symbol,
        "history": mock_history,
        "trend": "LONG_BUILDUP",
        "trend_description": "Güçlü Alıcı Kaldıracı (Long Yığılması - Simüle)",
        "trend_color": "emerald"
    }


# ──────────────────────────────────────────────────────────────────────
# Runtime Agent Team (canonical A6)
# ──────────────────────────────────────────────────────────────────────


def _get_agent_team():
    """Return the live ``AgentTeam`` instance, or None if not yet initialised.

    The bot worker creates the SafeOrchestrator (and therefore the
    AgentTeam) asynchronously. Until that happens, the AI endpoints
    return 503 instead of crashing.
    """
    orch = getattr(runner, "orch", None)
    if orch is None:
        return None
    return getattr(orch, "agent_team", None)


@router.get("/ai/agents", dependencies=[Depends(require_auth)])
async def ai_agents_recent() -> dict:
    """Return the most recent in-memory AgentTeam verdicts.

    Backed by ``AgentTeam.recent_reviews()`` (newest first). When the
    bot has not yet produced a verdict (or is starting up), returns
    ``{"reviews": [], "enabled": false}`` with HTTP 200 — the dashboard
    can poll without flooding error logs.
    """
    team = _get_agent_team()
    if team is None:
        return {"enabled": False, "reviews": [], "message": "agent team not initialised"}
    from engine.agents.gemini_client import DEFAULT_MODEL
    return {
        "enabled": bool(team.cfg.get("enabled", False)),
        "gating": bool(team.cfg.get("gating", False)),
        "model": team.cfg.get("model", DEFAULT_MODEL),
        "reviews": team.recent_reviews(limit=20),
    }


@router.post("/ai/post-mortem", dependencies=[Depends(require_auth)])
async def ai_post_mortem(schedule: str = "daily") -> dict:
    """Trigger the PostMortemAgent and return the generated report path.

    The agent is fail-safe: missing API key, no LLM response, or empty
    journal all still produce a markdown report shell so the operator
    has something to look at.
    """
    team = _get_agent_team()
    if team is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="agent team not initialised (bot worker not started yet)",
        )
    if schedule not in ("daily", "weekly"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="schedule must be 'daily' or 'weekly'",
        )
    try:
        journal_path = "state/trade_journal.jsonl"
        out_path = team.run_post_mortem(
            journal_path=journal_path,
            reports_dir="reports",
            schedule=schedule,
        )
    except Exception as e:
        log.error(f"PostMortemAgent failed: {e!r}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"post-mortem failed: {e}",
        )
    return {"report_path": out_path, "schedule": schedule}


from backend.signals_smc import get_smc_signal

@router.get("/signals/smc", dependencies=[Depends(require_auth)])
async def signals_smc(symbol: str = "BTCUSDT", timeframe: str = "15m") -> dict:
    """Calculated SMC structure (swings → BOS/ChoCh, OB, FVG, premium/discount, PDH/PDL)."""
    return await get_smc_signal(symbol, timeframe, runner)

