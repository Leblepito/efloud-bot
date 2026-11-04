#!/usr/bin/env python3
"""5-hourly advisory research cycle: 15m / 1h / 4h SMC structure + TradingAgents brief.

Per symbol:
  1. Closed Binance USDT-M candles for 15m, 1h and 4h (public klines, no key).
  2. The engine's own LuxAlgo-port `analyze()` on each timeframe with the live
     config's `smc_v2.luxalgo` parameters -> swing/internal trend, last BOS/CHoCH,
     premium/discount position, active order blocks. The 4h swing trend is the HTF
     bias; alignment across the three is reported.
  3. TradingAgents (isolated venv) with the 4h bias as `--engine-bias`. Quick tier
     (analysts, debate, trader, risk team) = deepseek/deepseek-v4.1-flash; deep tier
     (research manager + portfolio manager, where conflicting views are resolved)
     = deepseek/deepseek-v4-pro. Both via OpenRouter (one key: OPENROUTER_API_KEY) —
     operator decision 2026-11-03; no Anthropic key exists on the VPS.
  4. One combined brief: desk/briefs/<YYYY-MM-DD-HHMM>-<SYM>USDT-research.{md,json}.

ADVISORY ONLY: never an order, size, SL/TP, config change or gating input. The
LuxAlgo module is loaded by file path, so the trading engine package (and its
exchange layer) is never imported here.

Schedule every 5 hours (see skills/tradingagents-research), e.g. systemd timer with
OnUnitActiveSec=5h, or cron `0 */5 * * *` (00/05/10/15/20 UTC):
    .venv-research/bin/python scripts/desk/research_cycle.py --symbols BTC/USDT,ETH/USDT
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:  # run by path (cron / docs), not only `python -m`
    sys.path.insert(0, str(ROOT))

from scripts.desk import tradingagents_brief as tb

LUX_PATH = ROOT / "engine" / "smc_v2" / "luxalgo.py"
TIMEFRAMES = ("15m", "1h", "4h")
DAYS = {"15m": 7, "1h": 30, "4h": 120}   # >= ~480 bars each: swing 50 + ATR(200) warm-up
_LUX = None


def _lux():
    """Load engine/smc_v2/luxalgo.py by path (pure numpy/pandas) without the engine package."""
    global _LUX
    if _LUX is None:
        spec = importlib.util.spec_from_file_location("efloud_luxalgo_research", LUX_PATH)
        mod = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = mod
        spec.loader.exec_module(mod)
        _LUX = mod
    return _LUX


def _zone(z, close: float) -> str:
    if z is None:
        return "UNKNOWN"
    if z.eq_low <= close <= z.eq_high:
        return "EQUILIBRIUM"
    return "PREMIUM_HALF" if close > z.equilibrium else "DISCOUNT_HALF"


def mtf_context(frames: dict, lux_cfg: dict) -> dict:
    lx = _lux()
    cfg = lx.LuxConfig.from_dict(lux_cfg)
    out = {}
    for tf in TIMEFRAMES:
        df = frames[tf]
        res = lx.analyze(df, cfg)
        last = res.breaks[-1] if res.breaks else None
        close = float(df["close"].iloc[-1])
        out[tf] = {
            "swing_trend": res.swing_trend,
            "internal_trend": res.internal_trend,
            "last_break": None if last is None else {
                "kind": last.kind, "direction": last.direction, "level": float(last.level),
                "scope": "internal" if last.internal else "swing", "ts": str(last.ts)},
            "zone": _zone(res.zones, close),
            "active_obs": len(res.active_obs()),
            "last_close": close,
            "last_bar_utc": df.index[-1].isoformat(),
        }
    four = out["4h"]["swing_trend"]
    trends = {out[tf]["swing_trend"] for tf in TIMEFRAMES}
    alignment = ("ALIGNED_BULL" if trends == {"BULL"} else
                 "ALIGNED_BEAR" if trends == {"BEAR"} else "MIXED")
    return {"timeframes": out, "htf_bias": four if four in ("BULL", "BEAR") else None,
            "alignment": alignment}


def _markdown(doc: dict) -> str:
    lines = [f"# Research — {doc['symbol']} — {doc['generated_utc']}", "",
             "> ADVISORY ONLY. Not an order, size, SL/TP or config input. The engine trades its own rules.", "",
             f"HTF bias (4h swing): **{doc['mtf']['htf_bias'] or 'UNDEF'}** | alignment: {doc['mtf']['alignment']}", "",
             "| TF | swing | internal | last break | zone | active OBs | last close | last bar (UTC) |",
             "| --- | --- | --- | --- | --- | --- | --- | --- |"]
    for tf in TIMEFRAMES:
        c = doc["mtf"]["timeframes"][tf]
        b = c["last_break"]
        br = "—" if b is None else f"{b['scope']} {b['kind']} {b['direction']} @ {b['level']:.8g}"
        lines.append(f"| {tf} | {c['swing_trend']} | {c['internal_trend']} | {br} | {c['zone']} | "
                     f"{c['active_obs']} | {c['last_close']:.8g} | {c['last_bar_utc']} |")
    ta = doc["tradingagents"]
    lines += ["", "## TradingAgents"]
    if ta is None:
        lines.append("skipped (--no-tradingagents)")
    elif "error" in ta:
        lines.append(f"unavailable: {ta['error']}")
    else:
        lines += [(f"- rating: **{ta['rating']}** (lean {ta['lean']}) vs engine bias "
                   f"{ta['engine_bias'] or 'UNDEF'} -> **{ta['engine_comparison']}**"),
                  f"- llm: {ta['llm']}", "", ta["final_decision_text"]]
    return "\n".join(lines) + "\n"


def run_cycle(symbols, out_dir, lux_cfg: dict, fetch=None, graph_factory=None, ta_config=None, now=None):
    """ta_config=None -> MTF only (no LLM cost)."""
    if fetch is None:
        from scripts.desk.plan_replay import fetch_klines as fetch
    now = now if now is not None else pd.Timestamp.now(tz="UTC")
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    docs = []
    for sym in symbols:
        base = {"symbol": sym, "generated_utc": now.isoformat()}
        try:
            frames = {tf: fetch(sym, tf, DAYS[tf]) for tf in TIMEFRAMES}
            ctx = mtf_context(frames, lux_cfg)
        except Exception as exc:  # noqa: BLE001 — one symbol's data/network failure must not stop the cycle
            docs.append({**base, "status": "unavailable", "error": f"{type(exc).__name__}: {exc}"})
            continue
        ta = None
        if ta_config is not None:
            try:
                ta = tb.run_brief(sym, now.date().isoformat(), ta_config, graph_factory=graph_factory,
                                  engine_bias=ctx["htf_bias"])
            except Exception as exc:  # noqa: BLE001 — LLM/provider failure is recorded, MTF brief still written
                ta = {"error": f"{type(exc).__name__}: {exc}"}
        doc = {**base, "status": "ok", "mtf": ctx, "tradingagents": ta, "advisory_only": True}
        stem = f"{now:%Y-%m-%d-%H%M}-{tb.to_yahoo(sym).replace('-USD', '')}USDT-research"
        md = out / f"{stem}.md"
        md.write_text(_markdown(doc), encoding="utf-8")
        (out / f"{stem}.json").write_text(json.dumps(doc, indent=2, default=str), encoding="utf-8")
        doc["file"] = str(md)
        docs.append(doc)
    return docs


def parse_args(argv=None):
    ap = argparse.ArgumentParser(description="Advisory 15m/1h/4h research cycle.")
    ap.add_argument("--symbols", default="BTC/USDT,ETH/USDT")
    ap.add_argument("--config", default=str(ROOT / "configs" / "config.phase2_1k.yaml"),
                    help="live config; its smc_v2.luxalgo block sets the structure parameters")
    ap.add_argument("--out", default="desk/briefs")
    # Same TRADINGAGENTS_* env vars as tradingagents_brief.py, so .env.research can pick
    # the models (e.g. a free OpenRouter model) without a code change.
    ap.add_argument("--provider", default=os.getenv("TRADINGAGENTS_LLM_PROVIDER", "openrouter"))
    ap.add_argument("--quick-model", default=os.getenv("TRADINGAGENTS_QUICK_THINK_LLM", "deepseek/deepseek-v4.1-flash"))
    ap.add_argument("--deep-model", default=os.getenv("TRADINGAGENTS_DEEP_THINK_LLM", "deepseek/deepseek-v4-pro"))
    ap.add_argument("--max-tokens", type=int, default=int(os.getenv("TRADINGAGENTS_MAX_TOKENS", "8192")),
                    help="cap per completion (avoids model-max credit reservation / HTTP 402)")
    ap.add_argument("--no-tradingagents", action="store_true", help="MTF structure only, no LLM calls")
    return ap.parse_args(argv)


def main(argv=None) -> int:
    a = parse_args(argv)
    import yaml

    lux_cfg = (yaml.safe_load(Path(a.config).read_text(encoding="utf-8")).get("smc_v2") or {}).get("luxalgo") or {}
    ta_config = None
    if not a.no_tradingagents:
        try:
            tb.default_graph_factory()
            from tradingagents.default_config import DEFAULT_CONFIG
        except (tb.BriefError, ImportError) as exc:
            print(f"refused: {exc}", file=sys.stderr)
            return 2
        ta_config = tb.build_config(DEFAULT_CONFIG, a.provider, a.deep_model, a.quick_model, Path(a.out).parent,
                                    max_tokens=a.max_tokens)
    docs = run_cycle([s.strip() for s in a.symbols.split(",") if s.strip()], a.out, lux_cfg, ta_config=ta_config)
    for d in docs:
        if d["status"] != "ok":
            print(f"UNAVAILABLE {d['symbol']}: {d['error']}")
            continue
        ta = d["tradingagents"]
        ta_txt = "TA skipped" if ta is None else (f"TA error: {ta['error']}" if "error" in ta else
                                                  f"TA {ta['rating']} ({ta['engine_comparison']})")
        print(f"ADVISORY {d['symbol']}: 4h bias {d['mtf']['htf_bias']} | {d['mtf']['alignment']} | "
              f"{ta_txt} -> {d['file']}")
    return 0 if any(d["status"] == "ok" for d in docs) else 1


if __name__ == "__main__":
    sys.exit(main())
