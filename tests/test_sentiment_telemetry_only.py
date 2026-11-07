"""Macro sentiment is telemetry only and lives in the bot's state_dir (decision 1, spec 2026-11-07).

Audit A1: the LLM's RISK_ON/RISK_OFF added ±5 confluence BEFORE min_confluence,
so a working LLM could open or block a marginal entry (contradicts ADR-0002).
Audit A2: the writer used <repo>/state, the engine read state_dir (prod
./state_1k) and the dashboard read ./state, so live traded on NEUTRAL while the
dashboard showed the LLM value. Live is already effectively NEUTRAL, so dropping
the ±5 changes no live trade.
"""
from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pandas as pd
import pytest

from engine.signals import generate_signals
from tests.test_gemini_advisory_not_blocking import _mock_engine


def _df():
    return pd.DataFrame({"open": [100.0] * 50, "high": [102.0] * 50, "low": [98.0] * 50,
                         "close": [100.0] * 50, "volume": [1.0] * 50})


def _sig(macro):
    choch = SimpleNamespace(direction="BULL", kind="CHoCH", idx=45, ts="2026-05-08T00:00", price=100.0)
    sigs = generate_signals(_mock_engine(choch), _df(), _df(), _df(), min_confluence=20, min_rr=1.0,
                            fib_ext=1.618, recency_bars=40, symbol=None,
                            ai_sentiment={"macro_sentiment": macro} if macro else None)
    assert len(sigs) == 1
    return sigs[0]


@pytest.mark.parametrize("macro", ["RISK_ON", "RISK_OFF"])
def test_sentiment_does_not_move_the_confluence_score(macro):
    assert _sig(macro).confluence == _sig(None).confluence


def test_sentiment_is_recorded_as_telemetry():
    s = _sig("RISK_OFF")
    assert s.meta["macro_sentiment"] == "RISK_OFF"
    assert not any("Sentiment" in r for r in s.reasons)


def test_writer_uses_the_given_state_dir(tmp_path, monkeypatch):
    from engine.ai import sentiment

    class _Client:
        def complete_json(self, prompt, **kw):
            return {"macro_sentiment": "RISK_ON", "confidence_score": 0.8, "fear_and_greed": 60,
                    "bitcoin_trend": "BULLISH", "reasoning": "x"}

    class _NoHttp:
        def __init__(self, *a, **k):
            raise OSError("offline")

    monkeypatch.setattr(sentiment.httpx, "AsyncClient", _NoHttp)
    monkeypatch.setattr(sentiment._cache, "get", lambda k: None)
    monkeypatch.setattr(sentiment._cache, "set", lambda k, v: None)
    with patch("engine.agents.llm.make_llm_client", return_value=_Client()):
        asyncio.run(sentiment.fetch_and_save_sentiment(state_dir=str(tmp_path)))
    data = json.loads((tmp_path / "ai_sentiment_registry.json").read_text(encoding="utf-8"))
    assert data["macro_sentiment"] == "RISK_ON"


def test_runner_writes_into_its_own_state_dir(monkeypatch):
    from backend.bot_runner import BotRunner

    runner = object.__new__(BotRunner)
    runner.cfg = {"operation": {"state_dir": "./state_1k"}, "llm": {"provider": "openrouter"}}
    runner.stopped = False
    runner.orch = None
    seen = {}

    async def fake_fetch(**kw):
        seen.update(kw)
        runner.stopped = True
        return {"macro_sentiment": "NEUTRAL"}

    monkeypatch.setattr("engine.ai.sentiment.fetch_and_save_sentiment", fake_fetch)
    monkeypatch.setattr("engine.agents.llm.provider_key_present", lambda cfg: True)
    with patch("asyncio.sleep", new=AsyncMock()):
        asyncio.run(runner._run_sentiment_loop())
    assert seen["state_dir"] == "./state_1k"


def test_dashboard_reads_the_configured_state_dir(tmp_path, monkeypatch):
    import backend.api as api

    (tmp_path / "ai_sentiment_registry.json").write_text(json.dumps({"macro_sentiment": "RISK_OFF"}),
                                                         encoding="utf-8")
    monkeypatch.setattr(api, "_state_dir", lambda: str(tmp_path))
    assert asyncio.run(api.ai_sentiment())["macro_sentiment"] == "RISK_OFF"
