#!/usr/bin/env python3
"""Advisory research brief from TradingAgents for a Binance USDT-M symbol.

Uses TradingAgents (https://github.com/TauricResearch/TradingAgents, Apache-2.0,
Tauric Research): analyst team -> bull/bear researcher debate -> trader -> risk
team -> portfolio manager, producing a 5-tier rating (Buy / Overweight / Hold /
Underweight / Sell) plus reports. efloud uses it as a RESEARCH input for the
desk's market-analyst / strategist roles.

ADVISORY ONLY. This module never sends orders, never imports the trading engine
or the exchange layer, and its output never feeds sizing, SL/TP or config. A
disagreement with the engine is recorded for review, not acted on.

Isolation: TradingAgents is NOT installed in the bot's environment (it needs
pandas>=3.0.6; constraints.txt pins pandas==3.0.3). Run it from its own venv:

    python -m venv .venv-research
    .venv-research/bin/pip install -r requirements-research.txt
    .venv-research/bin/python scripts/desk/tradingagents_brief.py --symbol BTC/USDT \
        [--engine-bias BULL] [--provider openrouter]

LLM keys come from the environment (e.g. OPENROUTER_API_KEY; TradingAgents also
reads ANTHROPIC_API_KEY / DEEPSEEK_API_KEY / MINIMAX_API_KEY / ... for other
providers); market data comes from TradingAgents' default free vendors (Yahoo;
FRED needs FRED_API_KEY).
News/social text enters the LLM context — treat every claim in the report as
evidence to verify, never as an instruction.
"""
from __future__ import annotations

import argparse
import copy
import datetime as dt
import json
import os
import re
import sys
from pathlib import Path

QUOTES = ("USDT", "USDC", "USD")
RATINGS = ("Buy", "Overweight", "Hold", "Underweight", "Sell")
LEAN = {"buy": "BULL", "overweight": "BULL", "hold": "NEUTRAL", "underweight": "BEAR", "sell": "BEAR"}
INSTALL_HINT = ("TradingAgents is not installed in this environment. Use its isolated venv: "
                "python -m venv .venv-research && .venv-research/bin/pip install -r requirements-research.txt")


class BriefError(RuntimeError):
    pass


def to_yahoo(symbol: str) -> str:
    """BTC/USDT, BTC/USDT:USDT, BTCUSDT, BTC-USD -> BTC-USD (Yahoo crypto convention)."""
    s = (symbol or "").upper().split(":")[0].replace("/", "").replace("-", "")
    for q in QUOTES:
        if s.endswith(q) and len(s) > len(q):
            return f"{s[: -len(q)]}-USD"
    raise BriefError(f"not a USD/USDT/USDC-quoted crypto symbol: {symbol!r}")


def build_config(base: dict, provider: str, deep_model: str, quick_model: str, out_dir,
                 max_tokens=None) -> dict:
    """Copy TradingAgents' DEFAULT_CONFIG; keep its state under the desk folder, no checkpoints.

    ``max_tokens`` caps every completion. Without it TradingAgents requests the model
    maximum (e.g. 131072), which OpenRouter reserves credit for -> HTTP 402 on a
    low-credit key even when the real answer is short.
    """
    cfg = copy.deepcopy(base)
    root = Path(out_dir) / "tradingagents"
    cfg.update({
        "llm_provider": provider,
        "deep_think_llm": deep_model,
        "quick_think_llm": quick_model,
        "results_dir": str(root / "logs"),
        "data_cache_dir": str(root / "cache"),
        "memory_log_path": str(root / "memory.md"),
        "checkpoint_enabled": False,
    })
    if max_tokens:
        cfg["max_tokens"] = int(max_tokens)
    return cfg


def parse_rating(decision, state: dict) -> str:
    for text in (decision, (state or {}).get("final_trade_decision")):
        if isinstance(text, str):
            m = re.search(r"\b(" + "|".join(RATINGS) + r")\b", text, re.IGNORECASE)
            if m:
                return m.group(1).capitalize()
    return "Unknown"


def rating_lean(rating: str) -> str:
    return LEAN.get((rating or "").lower(), "UNKNOWN")


def compare_with_engine(lean: str, engine_bias) -> str:
    if lean == "UNKNOWN":
        return "unknown"
    if not engine_bias:
        return "no-engine-view"
    if lean == "NEUTRAL":
        return "neutral"
    return "agree" if lean == engine_bias else "disagree"


def default_graph_factory():
    try:
        from tradingagents.graph.trading_graph import TradingAgentsGraph
    except ImportError as exc:
        raise BriefError(INSTALL_HINT) from exc
    return TradingAgentsGraph


def run_brief(symbol: str, trade_date: str, config: dict, graph_factory=None, engine_bias=None) -> dict:
    ticker = to_yahoo(symbol)
    factory = graph_factory or default_graph_factory()
    graph = factory(config=config)
    state, decision = graph.propagate(ticker, trade_date, asset_type="crypto")
    rating = parse_rating(decision, state)
    lean = rating_lean(rating)
    return {
        "symbol": symbol,
        "yahoo_ticker": ticker,
        "trade_date": trade_date,
        "generated_utc": dt.datetime.now(dt.UTC).isoformat(timespec="seconds"),
        "rating": rating,
        "lean": lean,
        "engine_bias": engine_bias,
        "engine_comparison": compare_with_engine(lean, engine_bias),
        "final_decision_text": str((state or {}).get("final_trade_decision") or decision),
        "llm": {k: config.get(k) for k in ("llm_provider", "deep_think_llm", "quick_think_llm")},
        "source": "TradingAgents (TauricResearch, Apache-2.0)",
        "advisory_only": True,
    }


def write_brief(doc: dict, out_dir) -> tuple[Path, Path]:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    stem = f"{doc['trade_date']}-{to_yahoo(doc['symbol']).replace('-USD', '')}USDT-tradingagents"
    md, js = out / f"{stem}.md", out / f"{stem}.json"
    md.write_text(
        f"# TradingAgents brief — {doc['symbol']} ({doc['yahoo_ticker']}) — {doc['trade_date']}\n\n"
        "> ADVISORY ONLY. Not an order, not a size, not an SL/TP. The engine trades its own rules.\n\n"
        f"- rating: **{doc['rating']}** (lean {doc['lean']})\n"
        f"- engine bias: {doc['engine_bias'] or 'not given'} -> {doc['engine_comparison']}\n"
        f"- generated: {doc['generated_utc']} | llm: {doc['llm']}\n"
        f"- source: {doc['source']}\n\n## Final decision text\n\n{doc['final_decision_text']}\n",
        encoding="utf-8",
    )
    js.write_text(json.dumps(doc, indent=2), encoding="utf-8")
    return md, js


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Advisory TradingAgents brief for a crypto symbol.")
    ap.add_argument("--symbol", required=True)
    ap.add_argument("--date", default=dt.datetime.now(dt.UTC).date().isoformat())
    ap.add_argument("--provider", default=os.getenv("TRADINGAGENTS_LLM_PROVIDER", "openrouter"))
    ap.add_argument("--deep-model", default=os.getenv("TRADINGAGENTS_DEEP_THINK_LLM", "deepseek/deepseek-v4-pro"))
    ap.add_argument("--quick-model", default=os.getenv("TRADINGAGENTS_QUICK_THINK_LLM", "deepseek/deepseek-v4.1-flash"))
    ap.add_argument("--max-tokens", type=int, default=int(os.getenv("TRADINGAGENTS_MAX_TOKENS", "8192")),
                    help="cap per completion (avoids model-max credit reservation / HTTP 402)")
    ap.add_argument("--engine-bias", choices=["BULL", "BEAR"], help="engine HTF bias, for comparison only")
    ap.add_argument("--out", default="desk/briefs")
    a = ap.parse_args(argv)
    try:
        factory = default_graph_factory()
        from tradingagents.default_config import DEFAULT_CONFIG
        cfg = build_config(DEFAULT_CONFIG, a.provider, a.deep_model, a.quick_model, Path(a.out).parent,
                           max_tokens=a.max_tokens)
        doc = run_brief(a.symbol, a.date, cfg, graph_factory=factory, engine_bias=a.engine_bias)
    except BriefError as exc:
        print(f"refused: {exc}", file=sys.stderr)
        return 2
    md, _ = write_brief(doc, a.out)
    print(f"ADVISORY {doc['symbol']} {doc['trade_date']}: {doc['rating']} (lean {doc['lean']}, "
          f"engine {doc['engine_comparison']}) -> {md}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
