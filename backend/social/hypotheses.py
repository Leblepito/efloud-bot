"""Research-only strategy hypothesis generation from social doctrine tags."""
from __future__ import annotations

from collections import Counter
from typing import Any

_DEFAULT_METRICS = [
    "win_rate",
    "avg_realized_rr",
    "stop_hunt_rate",
    "max_drawdown_pct",
    "sharpe_like",
]


def _counter(doctrines: list[dict[str, Any]], key: str) -> Counter[str]:
    c: Counter[str] = Counter()
    for doctrine in doctrines:
        for value in doctrine.get(key, []) or []:
            c[str(value)] += 1
    return c


def generate_hypotheses(doctrines: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Generate safe, backtestable hypotheses from parsed social doctrine.

    Returned candidate patches are declarative research metadata. They are not
    applied to live config by this function.
    """
    zone_counts = _counter(doctrines, "zones")
    structure_counts = _counter(doctrines, "structure_terms")
    liquidity_counts = _counter(doctrines, "liquidity_terms")
    risk_counts = _counter(doctrines, "risk_terms")
    hypotheses: list[dict[str, Any]] = []

    if zone_counts["FVG"] and (zone_counts["OTE"] or structure_counts["MSB"]):
        hypotheses.append(
            {
                "id": "social_ote_fvg_htf_bias_v1",
                "title": "HTF structure + OTE/FVG pullback confluence",
                "rationale": (
                    "Efloud posts repeatedly combine market-structure confirmation "
                    "with OTE/FVG pullback zones before targeting continuation."
                ),
                "doctrine_tags": [
                    tag
                    for tag in ["MSB", "OTE", "FVG", "HTF_BIAS"]
                    if tag == "HTF_BIAS" or zone_counts[tag] or structure_counts[tag]
                ],
                "candidate_config_patch": {
                    "engine.social_research.require_htf_structure": True,
                    "engine.social_research.prefer_pullback_zones": ["OTE", "FVG"],
                },
                "metrics_to_watch": _DEFAULT_METRICS,
                "risk": "research_only",
            }
        )

    if liquidity_counts["liquidity_sweep"]:
        hypotheses.append(
            {
                "id": "social_liquidity_sweep_filter_v1",
                "title": "Liquidity sweep before reversal filter",
                "rationale": (
                    "Educational MPA/liquidity posts emphasize cleaned liquidity "
                    "as a potential reversal context. Validate as a filter only."
                ),
                "doctrine_tags": ["MPA", "LIQUIDITY_SWEEP"],
                "candidate_config_patch": {
                    "engine.social_research.require_liquidity_sweep_context": True,
                },
                "metrics_to_watch": _DEFAULT_METRICS,
                "risk": "research_only",
            }
        )

    if risk_counts["risk_management"]:
        hypotheses.append(
            {
                "id": "social_tp1_be_lifecycle_audit_v1",
                "title": "TP1 + break-even lifecycle audit",
                "rationale": (
                    "Risk-management posts stress TP1, break-even, and capital "
                    "protection. Validate lifecycle telemetry rather than entry logic."
                ),
                "doctrine_tags": ["TP1", "BE", "RISK_MANAGEMENT"],
                "candidate_config_patch": {},
                "metrics_to_watch": ["avg_realized_rr", "max_drawdown_pct", "profit_factor"],
                "risk": "research_only",
            }
        )

    return hypotheses
