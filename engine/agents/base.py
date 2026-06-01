"""Base class for role agents + the AgentVerdict value object.

Each role agent subclasses :class:`BaseAgent`, implements
:meth:`build_prompt` (and optionally :meth:`filter_context`), and gets
a uniform :meth:`review` for free. ``review`` runs the prompt through
the shared :class:`engine.agents.gemini_client.GeminiClient` and
coerces the response into a typed :class:`AgentVerdict`.

Verdict vocabulary is intentionally tight — exactly
``{"ACCEPT", "REJECT", "NEUTRAL"}``. Anything outside this set is
coerced to ``NEUTRAL`` by :func:`_verdict_from_payload`. Don't add
new verdicts without updating the team aggregation logic.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict

from .gemini_client import GeminiClient


VERDICTS = ("ACCEPT", "REJECT", "NEUTRAL")


@dataclass
class AgentVerdict:
    """One agent's decision on a given trade context.

    ``raw`` carries any extra fields the LLM emitted (key_levels,
    risk_factors, …). Keep it small — it gets logged to the
    disagreement JSONL and the size compounds.
    """
    name: str
    verdict: str          # one of VERDICTS
    confidence: float     # 0.0 - 1.0
    reasoning: str
    raw: Dict[str, Any]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "verdict": self.verdict,
            "confidence": self.confidence,
            "reasoning": self.reasoning,
        }


class BaseAgent:
    """Skeleton for all role agents.

    Subclasses MUST override :meth:`build_prompt` and MAY override
    :meth:`filter_context` (the latter is the primary anti-echoing
    defence — restrict the context to the slice the role should see).
    """

    name: str = "base"
    enabled: bool = True

    def __init__(self, client: GeminiClient) -> None:
        self.client = client

    # ── Hooks subclasses override ─────────────────────────────────────────

    def build_prompt(self, ctx: Dict[str, Any]) -> str:
        raise NotImplementedError

    def filter_context(self, ctx: Dict[str, Any]) -> Dict[str, Any]:
        """Default: pass through unchanged. Override to enforce role scope."""
        return ctx

    # ── Default orchestration ─────────────────────────────────────────────

    def review(self, ctx: Dict[str, Any]) -> AgentVerdict:
        """Filter → prompt → LLM → verdict.

        Failures (network, parse, empty response) are caught upstream
        by :meth:`GeminiClient.complete_json` and surface as ``{}`` here.
        We coerce to NEUTRAL with confidence 0 and let the team policy
        decide whether to proceed.
        """
        filtered_ctx = self.filter_context(ctx)
        prompt = self.build_prompt(filtered_ctx)
        data = self.client.complete_json(prompt)
        return _verdict_from_payload(self.name, data)


def _verdict_from_payload(name: str, data: Dict[str, Any]) -> AgentVerdict:
    """Coerce a raw LLM JSON payload into a typed :class:`AgentVerdict`.

    Expected schema (validated permissively — missing fields tolerated,
    wrong types coerced):
        {
          "verdict":    "ACCEPT" | "REJECT" | "NEUTRAL",
          "confidence": 0.0 - 1.0,
          "reasoning":  "string"
        }
    """
    if not data:
        return AgentVerdict(name=name, verdict="NEUTRAL",
                            confidence=0.0, reasoning="", raw={})

    verdict = str(data.get("verdict", "NEUTRAL")).upper().strip()
    if verdict not in VERDICTS:
        verdict = "NEUTRAL"

    try:
        confidence = float(data.get("confidence", 0.0) or 0.0)
    except (TypeError, ValueError):
        confidence = 0.0
    confidence = max(0.0, min(1.0, confidence))

    reasoning = str(data.get("reasoning", "") or "")
    return AgentVerdict(name=name, verdict=verdict, confidence=confidence,
                        reasoning=reasoning, raw=data)
