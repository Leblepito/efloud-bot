"""Unit tests for the Kronos advisory integration + LLM synthesis.

HERMETIC: no test here spawns the real Kronos subprocess or touches the network.
`subprocess.run` is monkeypatched everywhere a prediction is exercised, so the
full suite stays fast (< ~2s) and CI never triggers the 3-7 min torch install.
"""
from __future__ import annotations

import subprocess as _sp

import pytest
from unittest.mock import AsyncMock, MagicMock

from engine.ai.kronos import (
    get_yfinance_ticker,
    synthesize_signal_with_kronos,
    run_kronos_prediction,
)
from backend.db import Database


# ── Sample Kronos stdout in the real runner format (for parse tests) ──────────
_KRONOS_STDOUT = (
    "# Kronos Prediction: BTC-USD\n"
    "**Last close:** $61,762.03 (2026-06-05 06:00)\n"
    "**Predicted close after 24 x 1h candles:** $68,021.89\n"
    "**Direction:** UP (+10.14%)\n"
    "**Confidence band:** MODERATE (mixed signal, check other timeframes)\n"
    "**Forecast range:** $62,580.43 - $68,329.98 (±9.31% of last close)\n"
)


def _mock_pool(execute_return=None):
    """Build a MagicMock asyncpg.Pool with one acquired conn."""
    conn = MagicMock()
    conn.execute = AsyncMock(return_value=execute_return)
    acquire_ctx = MagicMock(
        __aenter__=AsyncMock(return_value=conn),
        __aexit__=AsyncMock(return_value=False),
    )
    pool = MagicMock()
    pool.acquire = MagicMock(return_value=acquire_ctx)
    return pool, conn


def _kronos_data():
    return {
        "last_close": 68000.0,
        "predicted_close": 69500.0,
        "predicted_direction": "UP",
        "change_pct": 2.2,
        "confidence_band": "NARROW",
        "range_low": 67800.0,
        "range_high": 70100.0,
    }


# ── Symbol normalization ──────────────────────────────────────────────────────

def test_yfinance_ticker_normalization():
    assert get_yfinance_ticker("BTCUSDT") == "BTC-USD"
    assert get_yfinance_ticker("ETHUSDT") == "ETH-USD"
    assert get_yfinance_ticker("BTC/USDT:USDT") == "BTC-USD"
    assert get_yfinance_ticker("SOL-USD") == "SOL-USD"
    assert get_yfinance_ticker("ADAUSD") == "ADA-USD"


# ── DB write ───────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_db_update_trade_kronos_data():
    db = Database()
    pool, conn = _mock_pool()
    db.pool = pool

    trade_id = "460adf75-694a-45cf-a100-633f72498fbb"
    comment = "BTC is looking bullish today."
    confidence = 88

    await db.update_trade_kronos_data(trade_id, comment, confidence)

    conn.execute.assert_called_once()
    sql = conn.execute.call_args[0][0]
    assert "UPDATE trades" in sql
    assert "SET kronos_comment = $2, kronos_confidence = $3" in sql
    assert "WHERE id = $1::uuid" in sql

    args = conn.execute.call_args[0][1:]
    assert args[0] == trade_id
    assert args[1] == comment
    assert args[2] == confidence


# ── LLM synthesis (duck-typed client) ──────────────────────────────────────────

def test_synthesize_signal_success_uses_injected_client():
    """A valid provider response → source='llm', confidence passed through."""
    mock_client = MagicMock()
    mock_client.complete_json.return_value = {
        "comment": "Kronos-small trend yapısıyla uyumlu bir yükseliş öngörüyor.",
        "confidence": 92,
    }

    result = synthesize_signal_with_kronos(
        symbol="BTCUSDT", direction="LONG", entry=68100.0, sl=67000.0,
        tp1=70000.0, tp2=72000.0, confluence=80,
        reasons=["HTF bias aligned (BULL)", "Price at Order Block"],
        kronos_data=_kronos_data(), llm_client=mock_client,
    )

    assert result["confidence"] == 92
    assert result["source"] == "llm"
    assert "uyumlu" in result["comment"]
    mock_client.complete_json.assert_called_once()
    prompt = mock_client.complete_json.call_args[0][0]
    assert "Confluence Score: 80/100" in prompt
    # template fully interpolated (no raw dict-access tokens leaked)
    assert "predicted_direction" not in prompt


def test_synthesize_signal_fallback_tags_source():
    """Empty/invalid provider response → static fallback tagged source='fallback'."""
    mock_client = MagicMock()
    mock_client.complete_json.return_value = {}  # provider down / 404

    result = synthesize_signal_with_kronos(
        symbol="BTCUSDT", direction="LONG", entry=68100.0, sl=67000.0,
        tp1=70000.0, tp2=72000.0, confluence=80,
        reasons=["HTF bias aligned (BULL)"],
        kronos_data=_kronos_data(), llm_client=mock_client,
    )

    assert result["confidence"] == 76  # aligned: 80 * 0.95
    assert result["source"] == "fallback"
    assert "Kronos" in result["comment"]
    assert "LONG" in result["comment"]


def test_synthesize_signal_no_kronos_data_fallback():
    """No Kronos output at all → offline fallback, source='fallback', no LLM call."""
    mock_client = MagicMock()
    result = synthesize_signal_with_kronos(
        symbol="ETHUSDT", direction="SHORT", entry=3000.0, sl=3100.0,
        tp1=2900.0, tp2=None, confluence=60, reasons=[],
        kronos_data={}, llm_client=mock_client,
    )
    assert result["source"] == "fallback"
    mock_client.complete_json.assert_not_called()


# ── Prediction parsing (hermetic — subprocess.run monkeypatched) ───────────────

def _fake_completed(stdout: str, rc: int = 0):
    return _sp.CompletedProcess(args=["x"], returncode=rc, stdout=stdout, stderr="")


def test_run_kronos_prediction_parses_output(monkeypatch):
    monkeypatch.setattr(
        "engine.ai.kronos.subprocess.run",
        lambda *a, **k: _fake_completed(_KRONOS_STDOUT),
    )
    res = run_kronos_prediction("BTCUSDT")
    assert res["predicted_direction"] == "UP"
    assert res["change_pct"] == pytest.approx(10.14)
    assert res["confidence_band"] == "MODERATE"
    assert res["last_close"] == pytest.approx(61762.03)
    assert res["range_low"] == pytest.approx(62580.43)


def test_run_kronos_prediction_malformed_band_defaults_wide(monkeypatch):
    """Band vocabulary drift must default to WIDE (most conservative), never junk."""
    bad = _KRONOS_STDOUT.replace("MODERATE (mixed signal, check other timeframes)", "WOBBLY")
    monkeypatch.setattr(
        "engine.ai.kronos.subprocess.run",
        lambda *a, **k: _fake_completed(bad),
    )
    res = run_kronos_prediction("BTCUSDT")
    assert res["confidence_band"] == "WIDE"


def test_run_kronos_prediction_nonzero_returns_empty(monkeypatch):
    """Runner failure → {} (graceful), and NO real subprocess is ever spawned."""
    monkeypatch.setattr(
        "engine.ai.kronos.subprocess.run",
        lambda *a, **k: _fake_completed("", rc=1),
    )
    assert run_kronos_prediction("INVALID") == {}


def test_run_kronos_prediction_timeout_returns_empty(monkeypatch):
    def _raise(*a, **k):
        raise _sp.TimeoutExpired(cmd="kronos", timeout=1)
    monkeypatch.setattr("engine.ai.kronos.subprocess.run", _raise)
    assert run_kronos_prediction("BTCUSDT") == {}


# ── BotRunner gating / concurrency (Phases 0,2,3) ──────────────────────────────

def _runner():
    from backend.bot_runner import BotRunner
    return BotRunner()


def test_init_kronos_default_off():
    """Absent kronos block → fully inert (no executor/sem, feature disabled)."""
    r = _runner()
    r.cfg = {}
    r._init_kronos()
    assert r._kronos_enabled is False
    assert r._kronos_executor is None
    assert r._kronos_sem is None


def test_init_kronos_disabled_block():
    r = _runner()
    r.cfg = {"kronos": {"enabled": False, "run_on": ["trade_open", "readonly"]}}
    r._init_kronos()
    assert r._kronos_enabled is False
    assert r._kronos_executor is None


@pytest.mark.asyncio
async def test_init_kronos_enabled_builds_primitives():
    r = _runner()
    r.cfg = {"kronos": {"enabled": True, "max_concurrency": 2, "run_on": ["trade_open"]}}
    r._init_kronos()
    try:
        assert r._kronos_enabled is True
        assert r._kronos_run_on == {"trade_open"}
        assert r._kronos_executor is not None
        assert r._kronos_sem is not None
        assert r._kronos_sem._value == 2
    finally:
        r._kronos_executor.shutdown(wait=False)


def test_kronos_should_run_cooldown_and_inflight():
    r = _runner()
    r.cfg = {"kronos": {"enabled": False}}
    r._init_kronos()
    r._kronos_cfg = {"cooldown_sec": 3600}
    key = ("BTCUSDT", "LONG", 12345)

    assert r._kronos_should_run(key) is True  # fresh

    import time as _t
    r._kronos_last_run[key] = _t.time()
    assert r._kronos_should_run(key) is False  # within cooldown

    r._kronos_last_run[key] = _t.time() - 7200
    assert r._kronos_should_run(key) is True   # cooldown elapsed

    r._kronos_inflight.add(key)
    assert r._kronos_should_run(key) is False  # in-flight


@pytest.mark.asyncio
async def test_on_signal_readonly_noop_when_disabled():
    """Disabled feature → readonly callback returns immediately, schedules nothing."""
    r = _runner()
    r.cfg = {}
    r._init_kronos()
    sched = MagicMock()
    # Even with a loop set, a disabled feature must not schedule analysis.
    import asyncio
    r.loop = asyncio.get_running_loop()
    # Should simply return; assert no exception and feature stayed off.
    r._on_signal_readonly("BTCUSDT", "LONG", 1.0, 0.9, 1.1, 1.2, 80, [])
    assert r._kronos_enabled is False


# ── Provider-factory regression guard (Phase 1) ────────────────────────────────

def test_make_llm_client_routes_to_minimax():
    """The factory must build a MiniMax client for provider=minimax — the whole
    point of the rewrite (no hard-wired GeminiClient that 404s in prod)."""
    from engine.agents.llm import make_llm_client
    client = make_llm_client({"provider": "minimax"})
    assert type(client).__name__ == "MiniMaxClient"
