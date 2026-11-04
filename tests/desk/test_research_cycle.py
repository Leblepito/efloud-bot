"""Tests for scripts/desk/research_cycle.py — 5-hourly advisory research cycle.

Per symbol: LuxAlgo-port structure on 15m / 1h / 4h (engine code, loaded by file
path so the research venv never imports the trading engine package), then a
TradingAgents brief with the 4h swing trend passed as the engine bias. Quick tier =
Sonnet 5.5, deep tier (research + portfolio managers, the "escalation" step) =
Opus 5.5. Advisory only.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from typing import ClassVar

import numpy as np
import pandas as pd

from scripts.desk import research_cycle as rc

ROOT = Path(__file__).resolve().parents[2]
TF_MIN = {"15m": 15, "1h": 60, "4h": 240}


def frame(tf, n=600, trend=0.0008, seed=0):
    rng = np.random.default_rng(seed)
    idx = pd.date_range("2026-08-01", periods=n, freq=f"{TF_MIN[tf]}min", tz="UTC")
    t = np.arange(n)
    close = 100 * np.exp(trend * t + 0.03 * np.sin(t / 15.0) + rng.normal(0, 0.002, n).cumsum())
    open_ = np.r_[close[0], close[:-1]]
    high = np.maximum(open_, close) * 1.002
    low = np.minimum(open_, close) * 0.998
    return pd.DataFrame({"open": open_, "high": high, "low": low, "close": close, "volume": 1.0}, index=idx)


def fake_fetch(symbol, tf, days):
    return frame(tf)


class FakeGraph:
    calls: ClassVar[list] = []

    def __init__(self, config):
        self.config = config

    def propagate(self, ticker, trade_date, asset_type="stock", portfolio=None):
        FakeGraph.calls.append((ticker, asset_type))
        return {"final_trade_decision": "Rating: Hold."}, "Hold"


LUX_CFG = {"swing_length": 50, "internal_length": 5, "eq_length": 3, "eq_threshold": 0.1}


def test_mtf_context_has_each_timeframe_and_htf_bias_from_4h():
    ctx = rc.mtf_context({tf: frame(tf) for tf in rc.TIMEFRAMES}, LUX_CFG)
    assert set(ctx["timeframes"]) == {"15m", "1h", "4h"}
    for tf in rc.TIMEFRAMES:
        c = ctx["timeframes"][tf]
        assert {"swing_trend", "internal_trend", "last_break", "zone", "active_obs", "last_close",
                "last_bar_utc"} <= set(c)
    four = ctx["timeframes"]["4h"]["swing_trend"]
    assert ctx["htf_bias"] == (four if four in ("BULL", "BEAR") else None)
    assert ctx["alignment"] in ("ALIGNED_BULL", "ALIGNED_BEAR", "MIXED")


def test_cycle_writes_combined_brief_and_passes_4h_bias(tmp_path):
    FakeGraph.calls.clear()
    docs = rc.run_cycle(["BTC/USDT"], out_dir=tmp_path, lux_cfg=LUX_CFG, fetch=fake_fetch,
                        graph_factory=FakeGraph, ta_config={}, now=pd.Timestamp("2026-11-04T05:00Z"))
    assert FakeGraph.calls == [("BTC-USD", "crypto")]
    d = docs[0]
    assert d["status"] == "ok" and d["tradingagents"]["rating"] == "Hold"
    assert d["tradingagents"]["engine_bias"] == d["mtf"]["htf_bias"]
    md = Path(d["file"]).read_text()
    assert "ADVISORY ONLY" in md and "15m" in md and "1h" in md and "4h" in md
    assert Path(d["file"]).name == "2026-11-04-0500-BTCUSDT-research.md"


def test_one_failing_symbol_does_not_stop_the_cycle(tmp_path):
    def flaky(symbol, tf, days):
        if symbol.startswith("ETH"):
            raise OSError("network down")
        return frame(tf)

    docs = rc.run_cycle(["ETH/USDT", "BTC/USDT"], out_dir=tmp_path, lux_cfg=LUX_CFG, fetch=flaky,
                        graph_factory=FakeGraph, ta_config={}, now=pd.Timestamp("2026-11-04T05:00Z"))
    assert [d["status"] for d in docs] == ["unavailable", "ok"]
    assert "network down" in docs[0]["error"]


def test_mtf_only_mode_skips_tradingagents(tmp_path):
    FakeGraph.calls.clear()
    docs = rc.run_cycle(["BTC/USDT"], out_dir=tmp_path, lux_cfg=LUX_CFG, fetch=fake_fetch,
                        graph_factory=FakeGraph, ta_config=None, now=pd.Timestamp("2026-11-04T05:00Z"))
    assert FakeGraph.calls == []
    assert docs[0]["tradingagents"] is None and docs[0]["status"] == "ok"


def test_default_models_are_deepseek_flash_quick_pro_deep(monkeypatch):
    """Operator decision 2026-11-03: the research cycle runs on OpenRouter —
    deepseek flash for the quick tier, deepseek pro where conflicts are resolved.
    No Anthropic key exists on the VPS, so a claude-* default would 401."""
    for var in ("TRADINGAGENTS_LLM_PROVIDER", "TRADINGAGENTS_QUICK_THINK_LLM", "TRADINGAGENTS_DEEP_THINK_LLM"):
        monkeypatch.delenv(var, raising=False)
    a = rc.parse_args([])
    assert a.provider == "openrouter"
    assert a.quick_model == "deepseek/deepseek-v4.1-flash"
    assert a.deep_model == "deepseek/deepseek-v4-pro"
    assert a.symbols == "BTC/USDT,ETH/USDT"


def test_luxalgo_is_loaded_without_importing_the_engine_package():
    code = (f"import sys; sys.path.insert(0, {str(ROOT)!r}); "
            "from scripts.desk import research_cycle as r; r._lux(); print('engine' in sys.modules)")
    out = subprocess.run([sys.executable, "-I", "-c", code], capture_output=True, text=True,
                         check=False, timeout=60)
    assert out.returncode == 0, out.stderr
    assert out.stdout.strip() == "False"


def test_model_tiers_and_token_cap_come_from_env_when_set(monkeypatch):
    """.env.research is how the VPS picks models (e.g. a free OpenRouter model) without
    a code change; the cycle must honour the same TRADINGAGENTS_* vars as the brief."""
    monkeypatch.setenv("TRADINGAGENTS_LLM_PROVIDER", "openrouter")
    monkeypatch.setenv("TRADINGAGENTS_QUICK_THINK_LLM", "vendor/free-model:free")
    monkeypatch.setenv("TRADINGAGENTS_DEEP_THINK_LLM", "vendor/free-model:free")
    monkeypatch.setenv("TRADINGAGENTS_MAX_TOKENS", "6000")
    a = rc.parse_args([])
    assert a.quick_model == a.deep_model == "vendor/free-model:free"
    assert a.max_tokens == 6000


def test_default_token_cap_avoids_model_max_reservation(monkeypatch):
    """Without a cap TradingAgents asked OpenRouter for the model maximum (131072
    tokens) and the key's credit could not cover the reservation (HTTP 402)."""
    monkeypatch.delenv("TRADINGAGENTS_MAX_TOKENS", raising=False)
    assert rc.parse_args([]).max_tokens == 8192
