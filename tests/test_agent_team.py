"""
Tests for engine.agents — Runtime Agent Team.

Regression guard: the canonical plan says the agent layer must be
``enabled=False``-by-default and fail-safe when ``GEMINI_API_KEY`` is
missing. These tests exercise that contract plus the per-role
verdict-coercion, the disabled-team path, and the post-mortem
markdown emission.

All tests use a stub client (no network). Live Gemini calls are
exercised only in shadow-mode smoke (see scripts/agent_team_smoke.py),
not in pytest.
"""

from __future__ import annotations

import json
import os
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional
from unittest.mock import MagicMock

import pytest


# ── Stubs ──────────────────────────────────────────────────────────────────


@dataclass
class _StubResponse:
    verdict: str = "NEUTRAL"
    confidence: float = 0.5
    reasoning: str = "stub"


class _StubGeminiClient:
    """Records every call; returns whatever the test scripted."""

    def __init__(self, response: Optional[_StubResponse] = None,
                 raise_on_complete: bool = False) -> None:
        self.response = response or _StubResponse()
        self.raise_on_complete = raise_on_complete
        self.calls: List[str] = []

    def complete_json(self, prompt: str, *, timeout: float = 20.0) -> Dict[str, Any]:
        self.calls.append(prompt)
        if self.raise_on_complete:
            raise RuntimeError("simulated network failure")
        return {
            "verdict": self.response.verdict,
            "confidence": self.response.confidence,
            "reasoning": self.response.reasoning,
        }


def _make_ctx(**overrides: Any) -> Dict[str, Any]:
    """Baseline context matching what safe_orchestrator would feed the team."""
    base = {
        "symbol": "BTC/USDT",
        "direction": "LONG",
        "entry": 100.0,
        "sl": 95.0,
        "tp1": 110.0,
        "confluence": 65,
        "htf_bias": "BULL",
        "adx": 28.0,
        "htf_slope_pct": 0.5,
        "rr": 2.0,
        "size_notional_pct": 4.0,
        "sl_atr_distance": 1.0,
    }
    base.update(overrides)
    return base


# ── Tests ──────────────────────────────────────────────────────────────────


class TestGeminiClientFailSafe:
    """The canonical fail-safe: ANY failure → ``{}``."""

    def test_no_api_key_returns_empty_dict(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("GEMINI_API_KEY", raising=False)
        from engine.agents.gemini_client import GeminiClient
        client = GeminiClient(api_key=None)
        assert client.complete_json("any prompt") == {}

    def test_real_client_returns_empty_when_endpoint_fails(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Stub httpx to raise; the client must still return ``{}``."""
        import httpx
        from engine.agents import gemini_client as gc
        from engine.agents.gemini_client import GeminiClient

        def _fake_post(*args: Any, **kwargs: Any) -> Any:
            raise httpx.ConnectError("simulated network down")

        monkeypatch.setattr(gc.httpx, "post", _fake_post)
        client = GeminiClient(api_key="fake-key")
        assert client.complete_json("any prompt") == {}


class TestRoleVerdicts:
    """Each role produces a verdict with the right schema and coerced value."""

    @pytest.mark.parametrize("role_name", [
        "signal_validator", "risk_reviewer", "regime", "overseer",
    ])
    def test_verdict_coerced_to_known_set(self, role_name: str) -> None:
        from engine.agents.roles import (
            OverseerAgent, RegimeAgent, RiskReviewerAgent,
            SignalValidatorAgent,
        )
        client = _StubGeminiClient(response=_StubResponse(
            verdict="NONSENSE", confidence=0.4, reasoning="weird"
        ))
        cls = {
            "signal_validator": SignalValidatorAgent,
            "risk_reviewer": RiskReviewerAgent,
            "regime": RegimeAgent,
            "overseer": OverseerAgent,
        }[role_name]
        agent = cls(client)
        verdict = agent.review(_make_ctx())
        assert verdict.verdict == "NEUTRAL"  # coerced
        assert 0.0 <= verdict.confidence <= 1.0

    def test_empty_payload_yields_neutral(self) -> None:
        from engine.agents.roles import SignalValidatorAgent
        client = _StubGeminiClient()  # returns {} because we mock
        # Override: make complete_json return {} to test the empty path
        client.complete_json = lambda prompt, *, timeout=20.0: {}  # type: ignore[assignment]
        agent = SignalValidatorAgent(client)
        v = agent.review(_make_ctx())
        assert v.verdict == "NEUTRAL"
        assert v.confidence == 0.0


class TestDisabledTeam:
    """When ``enabled: false``, the team is a no-op (no LLM calls)."""

    def test_disabled_returns_neutral_no_llm_calls(self) -> None:
        from engine.agents.team import AgentTeam

        with tempfile.TemporaryDirectory() as tmpdir:
            client = _StubGeminiClient()
            team = AgentTeam(
                config={"enabled": False, "model": "stub"},
                client=client,
                state_dir=tmpdir,
            )
            review = team.review_trade(_make_ctx())
            assert review["team_verdict"] == "NEUTRAL"
            assert review["score"] == 0.0
            assert client.calls == []  # no LLM traffic when disabled


class TestTeamAggregation:
    """Verdicts are aggregated; the team exposes a per-agent audit trail."""

    def test_score_is_fraction_of_accepts(self) -> None:
        from engine.agents.team import AgentTeam

        with tempfile.TemporaryDirectory() as tmpdir:
            client = _StubGeminiClient(response=_StubResponse(
                verdict="ACCEPT", confidence=0.7
            ))
            team = AgentTeam(
                config={"enabled": True, "model": "stub"},
                client=client,
                state_dir=tmpdir,
            )
            review = team.review_trade(_make_ctx())
            assert review["team_verdict"] == "ACCEPT"
            assert review["score"] == 1.0
            assert len(review["agents"]) == 4  # 3 sub-agents + 1 overseer

    def test_mixed_verdicts_counted_correctly(self) -> None:
        from engine.agents.roles import (
            OverseerAgent, RegimeAgent, RiskReviewerAgent, SignalValidatorAgent,
        )
        from engine.agents.team import AgentTeam

        with tempfile.TemporaryDirectory() as tmpdir:
            accept_client = _StubGeminiClient(response=_StubResponse(
                verdict="ACCEPT", confidence=0.7
            ))
            team = AgentTeam(
                config={"enabled": True, "model": "stub"},
                client=accept_client,
                state_dir=tmpdir,
            )
            # Force 2 accepts + 1 reject via independent clients
            team.signal = SignalValidatorAgent(_StubGeminiClient(
                response=_StubResponse(verdict="ACCEPT", confidence=0.9)))
            team.risk = RiskReviewerAgent(_StubGeminiClient(
                response=_StubResponse(verdict="REJECT", confidence=0.8)))
            team.regime = RegimeAgent(accept_client)
            team.overseer = OverseerAgent(accept_client)
            review = team.review_trade(_make_ctx(rr=1.2))
            assert review["team_verdict"] == "ACCEPT"  # Overseer wins when no gating
            assert abs(review["score"] - 2/3) < 0.01  # 2 of 3 accept


class TestLLMExceptionSafety:
    """An LLM exception must NOT crash the bot — fail-safe verdict."""

    def test_exception_yields_neutral_verdict(self) -> None:
        from engine.agents.roles import (
            OverseerAgent, RegimeAgent, RiskReviewerAgent, SignalValidatorAgent,
        )
        from engine.agents.team import AgentTeam

        with tempfile.TemporaryDirectory() as tmpdir:
            bad_client = _StubGeminiClient(raise_on_complete=True)
            team = AgentTeam(
                config={"enabled": True, "model": "stub"},
                client=bad_client,
                state_dir=tmpdir,
            )
            team.signal = SignalValidatorAgent(bad_client)
            team.risk = RiskReviewerAgent(bad_client)
            team.regime = RegimeAgent(bad_client)
            team.overseer = OverseerAgent(bad_client)
            review = team.review_trade(_make_ctx())
            assert review["team_verdict"] in ("NEUTRAL", "REJECT")
            assert "agents" in review


class TestDisagreementLogging:
    """The disagreement JSONL is the input to future Bayesian arbitration."""

    def test_disagreement_log_created_on_call(self) -> None:
        from engine.agents.team import AgentTeam

        with tempfile.TemporaryDirectory() as tmpdir:
            client = _StubGeminiClient(response=_StubResponse(
                verdict="ACCEPT", confidence=0.6
            ))
            team = AgentTeam(
                config={"enabled": True, "model": "stub"},
                client=client,
                state_dir=tmpdir,
            )
            team.review_trade(_make_ctx())
            log_path = Path(tmpdir) / "agent_disagreements.jsonl"
            assert log_path.exists()
            with log_path.open("r", encoding="utf-8") as f:
                lines = [json.loads(line) for line in f if line.strip()]
            assert len(lines) == 1
            assert lines[0]["symbol"] == "BTC/USDT"
            assert "verdicts" in lines[0]


class TestInMemoryHistory:
    """``recent_reviews`` backs the ``GET /api/ai/agents`` endpoint."""

    def test_recent_reviews_returned_newest_first(self) -> None:
        from engine.agents.team import AgentTeam

        with tempfile.TemporaryDirectory() as tmpdir:
            client = _StubGeminiClient(response=_StubResponse(
                verdict="ACCEPT", confidence=0.5
            ))
            team = AgentTeam(
                config={"enabled": True, "model": "stub"},
                client=client,
                state_dir=tmpdir,
            )
            for sym in ("BTC/USDT", "ETH/USDT", "SOL/USDT"):
                team.review_trade(_make_ctx(symbol=sym))
            history = team.recent_reviews()
            assert len(history) == 3
            assert history[0]["symbol"] == "SOL/USDT"  # newest first
            assert history[-1]["symbol"] == "BTC/USDT"


class TestPostMortemAgent:
    """PostMortemAgent writes a markdown report and is fail-safe."""

    def _write_fake_journal(self, path: Path, n_trades: int = 5) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        rows = []
        for i in range(n_trades):
            rows.append({
                "trade_id": f"t{i}",
                "symbol": "BTC/USDT",
                "direction": "LONG",
                "entry_price": 100.0 + i,
                "exit_price": 101.0 + i if i % 2 == 0 else 99.0 + i,
                "realized_pnl": 10.0 if i % 2 == 0 else -5.0,
                "exit_reason": "TP" if i % 2 == 0 else "SL",
            })
        with path.open("w", encoding="utf-8") as f:
            for r in rows:
                f.write(json.dumps(r) + "\n")

    def test_writes_markdown_even_without_llm(self) -> None:
        """No GEMINI_API_KEY → empty LLM payload → report still complete."""
        from engine.agents.roles import PostMortemAgent
        from engine.agents.gemini_client import GeminiClient

        with tempfile.TemporaryDirectory() as tmp:
            journal = Path(tmp) / "trade_journal.jsonl"
            reports = Path(tmp) / "reports"
            self._write_fake_journal(journal, n_trades=4)

            client = GeminiClient(api_key=None)  # fail-safe no-op
            agent = PostMortemAgent(client)
            out = agent.write_report(str(journal), str(reports), schedule="daily")

            assert os.path.isfile(out)
            text = Path(out).read_text(encoding="utf-8")
            assert "# Post-Mortem" in text
            assert "Win rate" in text
            assert "Improvement Suggestions" in text

    def test_writes_markdown_with_llm_payload(self) -> None:
        from engine.agents.roles import PostMortemAgent

        with tempfile.TemporaryDirectory() as tmp:
            journal = Path(tmp) / "trade_journal.jsonl"
            reports = Path(tmp) / "reports"
            self._write_fake_journal(journal, n_trades=6)

            client = _StubGeminiClient()
            # Override complete_json to return the post-mortem-specific schema
            client.complete_json = lambda prompt, *, timeout=20.0: {  # type: ignore[assignment]
                "win_rate_forecast": 0.62,
                "common_loss_reasons": [
                    "Choppy regime", "Late entry after FVG", "Oversized SL",
                ],
                "improvement_suggestions": [
                    "Tighten confluence threshold to 60",
                    "Skip signals when ADX < 20",
                    "Add macro sentiment veto",
                ],
            }
            agent = PostMortemAgent(client)  # type: ignore[arg-type]
            out = agent.write_report(str(journal), str(reports), schedule="weekly")
            text = Path(out).read_text(encoding="utf-8")
            assert "Tighten confluence threshold" in text
            assert "Skip signals when ADX" in text
            assert "Add macro sentiment veto" in text
            assert "62.0%" in text  # win_rate_forecast rendered


class TestAgentTeamRecentReviewsAPI:
    """The API endpoint contract: /api/ai/agents returns the latest reviews."""

    def test_team_recent_reviews_isolated_from_other_instances(self) -> None:
        from engine.agents.team import AgentTeam

        with tempfile.TemporaryDirectory() as tmp:
            client = _StubGeminiClient(response=_StubResponse(
                verdict="NEUTRAL", confidence=0.4
            ))
            team_a = AgentTeam(
                config={"enabled": True, "model": "stub"},
                client=client, state_dir=tmp,
            )
            team_b = AgentTeam(
                config={"enabled": True, "model": "stub"},
                client=client, state_dir=tmp,
            )
            team_a.review_trade(_make_ctx(symbol="BTC/USDT"))
            team_b.review_trade(_make_ctx(symbol="ETH/USDT"))
            assert team_a.recent_reviews()[0]["symbol"] == "BTC/USDT"
            assert team_b.recent_reviews()[0]["symbol"] == "ETH/USDT"
