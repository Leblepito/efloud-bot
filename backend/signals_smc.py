"""Calculated SMC telemetry for the dashboard chart overlay.

Serves the same shape the frontend ``SmcOverlayPrimitive`` consumes:

    {
      "symbol": "BTCUSDT", "timeframe": "15m", "source": "engine"|"heuristic",
      "structure": [{"time": int, "price": float, "kind": "BOS"|"CHOCH", "dir": "bull"|"bear"}],
      "fvgs":      [{"startTime": int, "top": float, "bottom": float, "dir": "bull"|"bear", "mitigated": bool}],
      "obs":       [{"startTime": int, "top": float, "bottom": float, "dir": "bull"|"bear", "mitigated": bool}],
      "pdh": float|None, "pdl": float|None,
      "range": {"high": float, "low": float, "eq": float} | None
    }

The endpoint prefers live structure from the running engine (``engine/smc_v2``)
and falls back to a deterministic, dependency-free heuristic computed from raw
Binance klines so the chart always has something correct to draw. This module
holds NO FastAPI imports, so it is unit-testable in isolation.
"""
from __future__ import annotations

import logging
import time
from typing import Any, Optional

log = logging.getLogger("efloud.signals.smc")

# In-memory cache to prevent duplicate Binance API requests (Q1)
_SMC_CACHE: dict[tuple[str, str], tuple[float, dict[str, Any]]] = {}
_CACHE_TTL = 15.0  # seconds TTL

Candle = dict[str, float]  # {time, open, high, low, close}


# ──────────────────────────────────────────────────────────────────────
# Deterministic heuristic (Python port of frontend computeSMC)
# ──────────────────────────────────────────────────────────────────────
def compute_smc_heuristic(
    candles: list[Candle],
    *,
    swing_lookback: int = 5,
    max_fvg: int = 6,
    max_ob: int = 4,
    max_structure: int = 6,
    range_bars: int = 50,  # aligned to engine's range_lookback
) -> dict[str, Any]:
    n = len(candles)
    empty = {"structure": [], "fvgs": [], "obs": [], "pdh": None, "pdl": None, "range": None}
    if n < swing_lookback * 2 + 5:
        return empty

    L = swing_lookback

    # 1. Fractal swings
    swings: list[dict[str, Any]] = []
    for i in range(L, n - L):
        is_high = is_low = True
        for j in range(i - L, i + L + 1):
            if j == i:
                continue
            if candles[j]["high"] >= candles[i]["high"]:
                is_high = False
            if candles[j]["low"] <= candles[i]["low"]:
                is_low = False
        if is_high:
            swings.append({"idx": i, "time": candles[i]["time"], "price": candles[i]["high"], "type": "high"})
        if is_low:
            swings.append({"idx": i, "time": candles[i]["time"], "price": candles[i]["low"], "type": "low"})

    # 2. BOS / CHOCH
    structure: list[dict[str, Any]] = []
    trend: Optional[str] = None
    last_high = last_low = None
    si = 0
    for i in range(n):
        while si < len(swings) and swings[si]["idx"] <= i:
            if swings[si]["type"] == "high":
                last_high = swings[si]
            else:
                last_low = swings[si]
            si += 1
        c = candles[i]
        if last_high and c["close"] > last_high["price"] and i > last_high["idx"]:
            kind = "CHOCH" if trend == "bear" else "BOS"
            structure.append({"time": int(c["time"]), "price": last_high["price"], "kind": kind, "dir": "bull"})
            trend, last_high = "bull", None
        elif last_low and c["close"] < last_low["price"] and i > last_low["idx"]:
            kind = "CHOCH" if trend == "bull" else "BOS"
            structure.append({"time": int(c["time"]), "price": last_low["price"], "kind": kind, "dir": "bear"})
            trend, last_low = "bear", None

    # 3. Fair Value Gaps
    fvgs: list[dict[str, Any]] = []
    for i in range(1, n - 1):
        a, c = candles[i - 1], candles[i + 1]
        if a["high"] < c["low"]:
            top, bottom = c["low"], a["high"]
            mitigated = any(k["low"] <= bottom for k in candles[i + 2:])
            fvgs.append({"startTime": int(candles[i]["time"]), "top": top, "bottom": bottom, "dir": "bull", "mitigated": mitigated})
        elif a["low"] > c["high"]:
            top, bottom = a["low"], c["high"]
            mitigated = any(k["high"] >= top for k in candles[i + 2:])
            fvgs.append({"startTime": int(candles[i]["time"]), "top": top, "bottom": bottom, "dir": "bear", "mitigated": mitigated})
    recent_fvgs = [f for f in fvgs if not f["mitigated"]][-max_fvg:]

    # 4. Order Blocks (last opposing candle before a structure break)
    obs: list[dict[str, Any]] = []
    time_to_idx = {c["time"]: idx for idx, c in enumerate(candles)}
    for s in structure:
        bi = time_to_idx.get(s["time"], -1)
        if bi < 1:
            continue
        rng = range(bi - 1, max(-1, bi - 13), -1)
        if s["dir"] == "bull":
            for k in rng:
                if candles[k]["close"] < candles[k]["open"]:
                    obs.append({"startTime": int(candles[k]["time"]), "top": candles[k]["high"], "bottom": candles[k]["low"], "dir": "bull", "mitigated": False})
                    break
        else:
            for k in rng:
                if candles[k]["close"] > candles[k]["open"]:
                    obs.append({"startTime": int(candles[k]["time"]), "top": candles[k]["high"], "bottom": candles[k]["low"], "dir": "bear", "mitigated": False})
                    break
    recent_obs = obs[-max_ob:]

    # 5. Previous Day High / Low
    pdh = pdl = None
    last_t_ms = candles[-1]["time"] * 1000
    day_ms = 86_400_000
    last_day_start = (last_t_ms // day_ms) * day_ms
    prev_day_start = last_day_start - day_ms
    prev_day = [c for c in candles if prev_day_start <= c["time"] * 1000 < last_day_start]
    if prev_day:
        pdh = max(c["high"] for c in prev_day)
        pdl = min(c["low"] for c in prev_day)

    # 6. Premium / Discount / Equilibrium
    sl = candles[-range_bars:]
    high = max(c["high"] for c in sl)
    low = min(c["low"] for c in sl)
    rng_obj = {"high": high, "low": low, "eq": (high + low) / 2}

    return {
        "structure": structure[-max_structure:],
        "fvgs": recent_fvgs,
        "obs": recent_obs,
        "pdh": pdh,
        "pdl": pdl,
        "range": rng_obj,
    }


# ──────────────────────────────────────────────────────────────────────
# Engine bridge (best-effort) + public entrypoint
# ──────────────────────────────────────────────────────────────────────
def _candles_from_klines(klines: list[list]) -> list[Candle]:
    out: list[Candle] = []
    for k in klines:
        out.append({
            "time": int(k[0]) // 1000,
            "open": float(k[1]),
            "high": float(k[2]),
            "low": float(k[3]),
            "close": float(k[4]),
        })
    return out


def _engine_smc(symbol: str, timeframe: str, runner: Any) -> Optional[dict[str, Any]]:
    """Try to read live SMC structure off the running orchestrator.

    The bot's ``engine/smc_v2`` setups (``select_htf_swing_anchor``,
    ``build_pullback_zones``, ``generate_setup_candidates``) already compute
    swings / OB / FVG zones each cycle. If your orchestrator caches the latest
    per-symbol structure, expose it and map it here. Returns ``None`` when no
    live structure is available so the caller falls back to the heuristic.
    """
    orch = getattr(runner, "orch", None)
    if orch is None:
        return None
    # Defensive: only use a cache if the engine actually exposes one.
    cache = getattr(orch, "smc_telemetry", None) or getattr(orch, "smc_v2_state", None)
    if not cache:
        return None
    try:
        sym = symbol.replace("/", "").replace(":", "").upper()
        entry = cache.get(sym) if hasattr(cache, "get") else None
        if not entry:
            return None
        # Expect entry already shaped like the heuristic output; pass through.
        return {
            "structure": entry.get("structure", []),
            "fvgs": entry.get("fvgs", []),
            "obs": entry.get("obs", []),
            "pdh": entry.get("pdh"),
            "pdl": entry.get("pdl"),
            "range": entry.get("range"),
        }
    except Exception as e:  # never break the endpoint on engine shape drift
        log.debug("engine SMC bridge skipped: %s", e)
        return None


async def get_smc_signal(symbol: str, timeframe: str, runner: Any) -> dict[str, Any]:
    clean = symbol.replace("/", "").replace(":", "").upper()
    if not clean.endswith("USDT"):
        clean += "USDT"

    now = time.time()
    cache_key = (clean, timeframe)
    
    # Check in-memory cache to prevent duplicate loads (Q1)
    if cache_key in _SMC_CACHE:
        ts, cached_data = _SMC_CACHE[cache_key]
        if now - ts < _CACHE_TTL:
            return cached_data

    # 1. Prefer live engine structure
    engine = _engine_smc(clean, timeframe, runner)
    if engine and (engine.get("structure") or engine.get("obs") or engine.get("fvgs")):
        res = {"symbol": clean, "timeframe": timeframe, "source": "engine", **engine}
        _SMC_CACHE[cache_key] = (now, res)
        return res

    # 2. Fallback: deterministic heuristic from Binance klines
    import httpx
    url = f"https://fapi.binance.com/fapi/v1/klines?symbol={clean}&interval={timeframe}&limit=500"
    try:
        async with httpx.AsyncClient(timeout=4.0) as client:
            res = await client.get(url)
            res.raise_for_status()
            candles = _candles_from_klines(res.json())
    except Exception as e:
        log.warning("SMC klines fetch failed for %s %s: %s", clean, timeframe, e)
        err_res = {"symbol": clean, "timeframe": timeframe, "source": "unavailable",
                "structure": [], "fvgs": [], "obs": [], "pdh": None, "pdl": None, "range": None}
        _SMC_CACHE[cache_key] = (now, err_res)
        return err_res

    # Use the range_bars matching the config
    cfg_range = 50
    if runner.cfg and runner.cfg.get("structure"):
        cfg_range = runner.cfg.get("structure").get("range_lookback", 50)

    smc = compute_smc_heuristic(candles, range_bars=cfg_range)
    final_res = {"symbol": clean, "timeframe": timeframe, "source": "heuristic", **smc}
    _SMC_CACHE[cache_key] = (now, final_res)
    return final_res
