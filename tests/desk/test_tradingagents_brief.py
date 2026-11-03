"""Tests for scripts/desk/tradingagents_brief.py — advisory TradingAgents research briefs.

TradingAgents (TauricResearch, Apache-2.0) is NOT installed in the bot's
environment (its pandas>=3.0.6 conflicts with constraints.txt pandas==3.0.3).
The adapter imports it lazily and takes an injectable graph factory, so these
tests run without it.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import ClassVar

import pytest

from scripts.desk import tradingagents_brief as tb


class FakeGraph:
    calls: ClassVar[list] = []

    def __init__(self, config):
        self.config = config

    def propagate(self, ticker, trade_date, asset_type="stock", portfolio=None):
        FakeGraph.calls.append((ticker, trade_date, asset_type))
        state = {"final_trade_decision": "Rating: Overweight. Momentum and flows support upside."}
        return state, "Overweight"


@pytest.mark.parametrize("symbol, ticker", [
    ("BTC/USDT", "BTC-USD"), ("ETH/USDT:USDT", "ETH-USD"), ("SOLUSDT", "SOL-USD"),
    ("doge/usdt", "DOGE-USD"), ("XRP-USD", "XRP-USD"),
])
def test_symbol_mapping(symbol, ticker):
    assert tb.to_yahoo(symbol) == ticker


@pytest.mark.parametrize("bad", ["AAPL", "BTC/EUR", "", "USDT"])
def test_non_crypto_or_unsupported_quote_is_refused(bad):
    with pytest.raises(tb.BriefError):
        tb.to_yahoo(bad)


def test_config_isolates_state_under_desk_and_disables_checkpoints(tmp_path):
    base = {"llm_provider": "openai", "deep_think_llm": "x", "quick_think_llm": "y",
            "results_dir": "/home/u/.tradingagents/logs", "memory_log_path": "/home/u/.tradingagents/m.md",
            "checkpoint_enabled": True, "data_vendors": {"news_data": "yfinance"}}
    cfg = tb.build_config(base, provider="anthropic", deep_model="d", quick_model="q", out_dir=tmp_path)
    assert cfg["llm_provider"] == "anthropic" and cfg["deep_think_llm"] == "d" and cfg["quick_think_llm"] == "q"
    assert cfg["checkpoint_enabled"] is False
    assert str(tmp_path) in cfg["results_dir"] and str(tmp_path) in cfg["memory_log_path"]
    assert base["llm_provider"] == "openai", "base config must not be mutated"


@pytest.mark.parametrize("rating, lean", [
    ("Buy", "BULL"), ("Overweight", "BULL"), ("Hold", "NEUTRAL"),
    ("Underweight", "BEAR"), ("Sell", "BEAR"), ("garbage", "UNKNOWN"),
])
def test_rating_lean(rating, lean):
    assert tb.rating_lean(rating) == lean


@pytest.mark.parametrize("lean, engine_bias, verdict", [
    ("BULL", "BULL", "agree"), ("BEAR", "BULL", "disagree"), ("NEUTRAL", "BEAR", "neutral"),
    ("BULL", None, "no-engine-view"), ("UNKNOWN", "BULL", "unknown"),
])
def test_compare_with_engine(lean, engine_bias, verdict):
    assert tb.compare_with_engine(lean, engine_bias) == verdict


def test_run_brief_uses_crypto_pipeline_and_marks_advisory(tmp_path):
    FakeGraph.calls.clear()
    doc = tb.run_brief("BTC/USDT", "2026-11-03", config={}, graph_factory=FakeGraph, engine_bias="BEAR")
    assert FakeGraph.calls == [("BTC-USD", "2026-11-03", "crypto")]
    assert doc["rating"] == "Overweight" and doc["lean"] == "BULL"
    assert doc["engine_comparison"] == "disagree"
    assert doc["advisory_only"] is True
    assert "Momentum" in doc["final_decision_text"]


def test_write_brief_creates_md_and_json(tmp_path):
    doc = tb.run_brief("ETH/USDT", "2026-11-03", config={}, graph_factory=FakeGraph)
    md, js = tb.write_brief(doc, tmp_path)
    assert md.name == "2026-11-03-ETHUSDT-tradingagents.md"
    assert "ADVISORY ONLY" in md.read_text()
    assert json.loads(js.read_text())["yahoo_ticker"] == "ETH-USD"


def test_missing_library_gives_install_hint(monkeypatch):
    import builtins
    real = builtins.__import__

    def fake_import(name, *a, **k):
        if name.startswith("tradingagents"):
            raise ImportError("no module")
        return real(name, *a, **k)

    monkeypatch.setattr(builtins, "__import__", fake_import)
    with pytest.raises(tb.BriefError, match="requirements-research.txt"):
        tb.default_graph_factory()


def test_module_never_imports_exchange_or_engine():
    src = Path(tb.__file__).read_text(encoding="utf-8")
    for forbidden in ("import ccxt", "from exchange", "from engine", "create_order"):
        assert forbidden not in src
