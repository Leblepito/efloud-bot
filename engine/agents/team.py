"""AgentTeam orchestrator — wires the sub-agents and aggregates verdicts.

The team is an **advisory** layer (per the canonical A3 contract). It
NEVER modifies the deterministic guard/breaker pipeline. When
``cfg.gating`` is False (the default), the verdict is logged and
persisted but the signal flows through unchanged. When ``gating`` is
True, the team_verdict is forwarded to the orchestrator's hard-veto
gate (``engine/safe_orchestrator.py``); the team itself does not
implement a "hard veto over Overseer" rule. The breaker/guard/orphan
layers are still in charge of every other safety decision.

Default model is ``gemini-1.5-flash`` per the canonical plan; override
via ``config["agent_team"]["model"]``.

NOTE — historical claims removed in the push-prep fixup:
  * "Data Freshness Assertion" / 15-min guard was claimed in the
    handoff but never implemented in the canonical A0 client. The
    client returns ``{}`` on any failure (no key, HTTP, parse,
    timeout) — there is no timestamp check.
  * "Memory poisoning prevention" / ``_filter_pnl_tagged`` was
    claimed but never implemented in the canonical team. The
    orchestrator passes ``ctx`` as-is to the team; if you want a
    PnL-tagged history filter, that's a follow-up.
"""

from __future__ import annotations

import json
import logging
import time
from collections import deque
from pathlib import Path
from typing import Any, Deque, Dict, List, Optional

from .gemini_client import GeminiClient
from .roles import (
    OverseerAgent,
    PostMortemAgent,
    RegimeAgent,
    RiskReviewerAgent,
    SignalValidatorAgent,
)

log = logging.getLogger("efloud.agents.team")


# Cap on in-memory verdict history exposed by ``GET /api/ai/agents``.
# Sized to be readable on a single screen; old verdicts still live in
# ``state/agent_disagreements.jsonl`` for offline analysis.
_INMEM_HISTORY_LIMIT = 50


class AgentTeam:
    """Advisory multi-agent orchestrator. Constructor matches the canonical A3.

    Pass an explicit ``client`` in tests; in production the team's
    constructor builds its own ``GeminiClient`` from the model name and
    the ``GEMINI_API_KEY`` env var.
    """

    def __init__(
        self,
        config: Dict[str, Any],
        *,
        client: Optional[GeminiClient] = None,
        state_dir: str = "./state",
    ) -> None:
        self.cfg = dict(config or {})
        self.state_dir = Path(state_dir)
        self.state_dir.mkdir(parents=True, exist_ok=True)

        if client is None:
            client = GeminiClient(
                api_key=self.cfg.get("api_key"),
                model=self.cfg.get("model", "gemini-3.1-flash"),
            )
        self.client = client

        # Sub-agents. ``self.overseer`` is intentionally public: the test
        # suite and operator tooling may swap individual sub-agents in
        # place to script specific verdicts (e.g. backtest simulation).
        self.signal = SignalValidatorAgent(client)
        self.risk = RiskReviewerAgent(client)
        self.regime = RegimeAgent(client)
        self.overseer = OverseerAgent(client)
        self.post_mortem = PostMortemAgent(client)

        # Rolling in-memory history for the /api/ai/agents endpoint.
        self._history: Deque[Dict[str, Any]] = deque(maxlen=_INMEM_HISTORY_LIMIT)

    # ── Public API ────────────────────────────────────────────────────────

    def review_trade(self, ctx: Dict[str, Any]) -> Dict[str, Any]:
        """Per-signal advisory. Does NOT change deterministic guard behavior.

        Returns a dict with ``team_verdict``, ``team_confidence``, ``score``,
        and an ``agents`` list of per-agent verdicts. The verdict vocabulary
        is exactly ``{"ACCEPT", "REJECT", "NEUTRAL"}``.
        """
        if not self.cfg.get("enabled", False):
            return {"team_verdict": "NEUTRAL", "agents": [], "score": 0.0}

        # NOTE — no PnL-tagged history filter. If the orchestrator ever
        # adds a "history" key to ctx, it will flow straight into the
        # LLM prompts. A memory-poisoning guard is a follow-up.

        try:
            verdicts: List[Any] = [
                self.signal.review(ctx),
                self.risk.review(ctx),
                self.regime.review(ctx),
            ]
            overseer_input = {
                "agent_verdicts": [v.to_dict() if hasattr(v, "to_dict") else dict(v) for v in verdicts],
            }
            final = self.overseer.review(overseer_input)
            score = sum(1 for v in verdicts if v.verdict == "ACCEPT") / len(verdicts)

            review: Dict[str, Any] = {
                "team_verdict": final.verdict,
                "team_confidence": final.confidence,
                "score": score,
                "agents": ([v.to_dict() if hasattr(v, "to_dict") else dict(v) for v in verdicts]
                           + [final.to_dict() if hasattr(final, "to_dict") else dict(final)]),
            }
        except Exception as e:
            # Last-resort safety net — the team must NEVER crash the bot.
            log.warning(f"AgentTeam.review_trade unexpected failure: {e!r}")
            review = {
                "team_verdict": "NEUTRAL",
                "team_confidence": 0.0,
                "score": 0.0,
                "agents": [],
                "error": repr(e),
            }

        # Persist to disagreement log + push to in-memory history.
        self._log_disagreement(ctx, review)
        self._history.append({
            "timestamp": time.time(),
            "symbol": (ctx or {}).get("symbol"),
            "team_verdict": review.get("team_verdict"),
            "score": review.get("score"),
        })
        return review

    def recent_reviews(self, limit: int = 20) -> List[Dict[str, Any]]:
        """Return the most recent verdicts (newest first) for the API."""
        return list(reversed(list(self._history)))[:limit]

    def run_post_mortem(self, journal_path: str, reports_dir: str = "./reports",
                        *, schedule: str = "daily") -> str:
        """Trigger the PostMortemAgent and return the path to the markdown file.

        Args:
            journal_path: Path to the trade journal JSONL.
            reports_dir:   Where to write the markdown report.
            schedule:      "daily" or "weekly" — controls the prompt.

        Returns:
            Absolute path of the generated markdown file.
        """
        return self.post_mortem.write_report(
            journal_path=journal_path,
            reports_dir=reports_dir,
            schedule=schedule,
        )

    # ── Telemetry sinks ───────────────────────────────────────────────────

    def _log_disagreement(self, ctx: Dict[str, Any], review: Dict[str, Any]) -> None:
        """Append one row per cycle to ``agent_disagreements.jsonl``."""
        try:
            row = {
                "schema_version": 1,
                "timestamp": time.time(),
                "symbol": (ctx or {}).get("symbol"),
                "direction": (ctx or {}).get("direction"),
                "verdicts": {
                    a.get("name"): a.get("verdict")
                    for a in review.get("agents", []) if isinstance(a, dict) and "name" in a
                },
                "team_verdict": review.get("team_verdict"),
                "team_confidence": review.get("team_confidence"),
                "score": review.get("score"),
            }
            path = self.state_dir / "agent_disagreements.jsonl"
            with path.open("a", encoding="utf-8") as f:
                f.write(json.dumps(row, ensure_ascii=False) + "\n")
        except Exception as e:
            log.warning(f"AgentTeam: disagreement log failed (ignored): {e!r}")
