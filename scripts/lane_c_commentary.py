"""Multi-timeframe SMC commentary generator — Phase 4a (PR #13).

Renders a top-down narration over the doctrine chain
(1D macro → 4H trend/bias → 1H structure → 15M trigger → invalidation →
disclaimer), per CLAUDE.md. Output is both a structured object (validates against
``scripts/lane_c/commentary_schema.json``) and a human script.

Guardrails (decision #5 + growth-OS): ratio/risk metrics only (R:R + risk-%,
never absolute $); the mandated disclaimer is always appended; and
``commentary_violations`` rejects banned promise-phrases (shared checker) plus
future-certainty / promise language ("kesinlikle", "garanti", "guaranteed",
"will"...). Draft-only; touches no trade state.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Optional

from engine.content_jobs import COMPLIANCE_TR
from scripts.content_compliance import find_violations

log = logging.getLogger("efloud.lane_c_commentary")

SCHEMA_PATH = Path(__file__).parent / "lane_c" / "commentary_schema.json"

# Doctrine chain, top-down (HTF macro → entry trigger).
TF_ORDER = ["1d", "4h", "1h", "15m"]

# Future-certainty / promise language — never appears in compliant commentary.
PROMISE_WORDS = [
    "kesinlikle", "mutlaka", "garanti", "kaybetmez", "%100", "100%",
    "guaranteed", "will ", "sure win", "can't lose",
]


def _rr_risk(setup: dict, tp_key: str) -> tuple[Optional[float], Optional[float]]:
    try:
        entry = float(setup["entry"]); sl = float(setup["sl"]); tp = float(setup[tp_key])
    except (KeyError, TypeError, ValueError):
        return None, None
    risk = abs(entry - sl)
    if risk == 0 or entry == 0:
        return None, None
    return abs(tp - entry) / risk, risk / abs(entry) * 100


def build_commentary(setup: dict) -> dict:
    """Structured commentary (validates against ``commentary_schema.json``)."""
    symbol = setup["symbol"]
    direction = setup["direction"]
    tfs = setup.get("timeframes", {}) or {}

    sections = []
    for tf in TF_ORDER:
        d = tfs.get(tf)
        if d:
            sections.append({"timeframe": tf.upper(),
                             "label": d.get("label", ""), "note": d.get("note", "")})

    rr1, risk_pct = _rr_risk(setup, "tp1")
    rr2, _ = _rr_risk(setup, "tp2")
    invalidation = setup.get("invalidation", "—")

    header = f"{symbol} · {direction} — Çok zaman dilimli görünüm"
    body = [f"{s['timeframe']} ({s['label']}): {s['note']}" for s in sections]

    metrics = []
    if risk_pct is not None:
        metrics.append(f"Risk ~{risk_pct:.1f}%")
    if rr1 is not None:
        metrics.append(f"R:R 1:{rr1:.1f} (TP1)")
    if rr2 is not None:
        metrics.append(f"1:{rr2:.1f} (TP2)")
    metrics_line = " · ".join(metrics)

    script = "\n".join([
        header, "",
        *body, "",
        metrics_line,
        f"Geçersizleşme: {invalidation}", "",
        COMPLIANCE_TR,
    ])

    return {
        "symbol": symbol,
        "direction": direction,
        "sections": sections,
        "risk": {"risk_pct": risk_pct, "rr_tp1": rr1, "rr_tp2": rr2},
        "invalidation": invalidation,
        "disclaimer": COMPLIANCE_TR,
        "script": script,
    }


def render_commentary(setup: dict) -> str:
    """The human-readable narration script."""
    return build_commentary(setup)["script"]


def commentary_violations(text: str) -> list[str]:
    """Content-compliance violations + promise / future-certainty language."""
    v = list(find_violations(text))
    low = (text or "").lower()
    for w in PROMISE_WORDS:
        if w.lower() in low:
            v.append(f"promise:{w.strip()}")
    return v


def main(argv: Optional[list[str]] = None) -> dict:
    """Render commentary from a setup JSON file; quarantine on any violation."""
    import argparse

    ap = argparse.ArgumentParser(description="Lane C — multi-timeframe commentary")
    ap.add_argument("--setup", required=True, help="path to a setup JSON file")
    ap.add_argument("--out", default=None, help="write commentary JSON here")
    args = ap.parse_args(argv)

    setup = json.loads(Path(args.setup).read_text(encoding="utf-8"))
    commentary = build_commentary(setup)
    violations = commentary_violations(commentary["script"])
    if violations:
        log.warning("commentary_quarantined symbol=%s violations=%s",
                    setup.get("symbol"), violations)
        result = {"quarantined": True, "violations": violations}
    else:
        if args.out:
            Path(args.out).write_text(
                json.dumps(commentary, ensure_ascii=False, indent=2), encoding="utf-8")
        result = {"quarantined": False, "symbol": commentary["symbol"]}
    print(json.dumps(result, ensure_ascii=False))
    return result


__all__ = [
    "build_commentary", "render_commentary", "commentary_violations",
    "SCHEMA_PATH", "TF_ORDER", "PROMISE_WORDS", "main",
]


if __name__ == "__main__":  # pragma: no cover
    main()
