"""Runtime Agent Team — multi-model LLM advisors.

Public surface (kept small on purpose):

  * :class:`GeminiClient`        — single source of truth for HTTP calls
  * :class:`BaseAgent`           — uniform ``review(ctx)`` over a Gemini call
  * :class:`AgentVerdict`        — dataclass for one agent's decision
  * :class:`AgentTeam`           — wires the role agents + aggregates verdicts
  * :class:`SignalValidatorAgent` — LTF/MTF structure reviewer
  * :class:`RiskReviewerAgent`   — R:R / notional / SL distance reviewer
  * :class:`RegimeAgent`         — Macro / HTF context reader
  * :class:`OverseerAgent`       — Synthesises sub-agent verdicts
  * :class:`PostMortemAgent`     — Cycle-external; writes markdown reports

The team is **advisory** by default. It never modifies the
deterministic guard/breaker pipeline. Set ``cfg["gating"] = True``
to make a hard ``REJECT`` veto the signal — but only after shadow
mode has built confidence in the verdicts.
"""

from .base import BaseAgent, AgentVerdict
from .gemini_client import GeminiClient
from .team import AgentTeam
from .roles import (
    SignalValidatorAgent,
    RiskReviewerAgent,
    RegimeAgent,
    OverseerAgent,
    PostMortemAgent,
)

__all__ = [
    "BaseAgent",
    "AgentVerdict",
    "GeminiClient",
    "AgentTeam",
    "SignalValidatorAgent",
    "RiskReviewerAgent",
    "RegimeAgent",
    "OverseerAgent",
    "PostMortemAgent",
]
