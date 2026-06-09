"""Lane C copywriter — Phase 4a (PR #12).

Consumes Lane B analysis JSON (§3.2), gates on ``confidence >= medium``, and
produces platform-agnostic copy (caption + thread + alt-text). Every draft
carries the mandated disclaimer (engine COMPLIANCE_TR) and is run through the
content-compliance checker as defense-in-depth: any draft that trips a banned
phrase / absolute-$ / performance-% rule is **quarantined** (not emitted).

Ratio/risk metrics only — R:R and risk-% are derived from the signal levels;
absolute dollar profit/loss is never produced (decision #5).

Draft-only: writes copy artifacts to local disk, posts nothing, touches no trade
state. Input is Lane B output; output feeds Lane D / Lane E.
"""
from __future__ import annotations

import json
import logging
import sys
from pathlib import Path
from typing import Optional

# Allow `python scripts/lane_c_copywriter.py ...` (repo root not otherwise on
# sys.path when invoked as a file rather than `-m`).
_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from engine.content_jobs import COMPLIANCE_TR
from scripts.content_compliance import find_violations

log = logging.getLogger("efloud.lane_c")

_ACCEPTED_CONFIDENCE = {"medium", "high"}


def _rr_and_risk(a: dict) -> tuple[Optional[float], Optional[float]]:
    """Return (rr_to_tp1, risk_pct) from signal levels, or (None, None)."""
    try:
        entry = float(a["entry"]); sl = float(a["sl"]); tp1 = float(a["tp1"])
    except (KeyError, TypeError, ValueError):
        return None, None
    risk = abs(entry - sl)
    if risk == 0 or entry == 0:
        return None, None
    rr = abs(tp1 - entry) / risk
    risk_pct = risk / abs(entry) * 100
    return rr, risk_pct


def _zones_str(analysis: dict) -> str:
    zones = analysis.get("smc_zones") or []
    parts = []
    for z in zones:
        rng = z.get("price_range") or []
        rng_s = f" {rng[0]}–{rng[1]}" if len(rng) == 2 else ""
        fresh = z.get("freshness")
        parts.append(f"{z.get('type', '?')}{rng_s}" + (f" ({fresh})" if fresh else ""))
    return ", ".join(parts) if parts else "—"


def build_copy(item: dict, *, lang: str = "tr") -> dict:
    """Build the platform-agnostic copy bundle for one Lane B analysis item."""
    analysis = item.get("analysis", {}) or {}
    symbol = item.get("symbol", "?")
    tf = item.get("timeframe", "?")
    direction = item.get("direction", "?")
    structure = analysis.get("structure") or "—"
    summary = analysis.get("summary") or structure
    invalidation = analysis.get("invalidation") or "—"
    rr, risk_pct = _rr_and_risk(item)

    metrics = []
    if risk_pct is not None:
        metrics.append(f"Risk ~{risk_pct:.1f}%")
    if rr is not None:
        metrics.append(f"R:R 1:{rr:.1f} (TP1)")
    metrics_line = " · ".join(metrics) if metrics else "—"

    caption = (
        f"{symbol} · {tf} · {direction}\n"
        f"{summary}.\n"
        f"{metrics_line} · Geçersizleşme: {invalidation}\n\n"
        f"{COMPLIANCE_TR}"
    )
    thread = [
        f"{symbol} {tf} {direction} — yapı: {structure}.",
        f"Bölgeler: {_zones_str(analysis)}.",
        f"Risk yönetimi: {metrics_line}.",
        f"Geçersizleşme: {invalidation}.",
        COMPLIANCE_TR,
    ]
    alt_text = f"{symbol} {tf} grafiği — {direction} {structure} setup"

    return {
        "event_id": item.get("event_id"),
        "symbol": symbol,
        "timeframe": tf,
        "lang": lang,
        "caption": caption,
        "thread": thread,
        "alt_text": alt_text,
        "source_confidence": analysis.get("confidence"),
    }


class LaneCCopywriter:
    def __init__(self, *, analysis_dir, out_dir, lang: str = "tr"):
        self.analysis_dir = Path(analysis_dir)
        self.out_dir = Path(out_dir)
        self.lang = lang

    def run(self, date: str) -> dict:
        src = self.analysis_dir / date
        files = sorted(src.glob("*.json")) if src.exists() else []
        generated = skipped_low = violations = errored = 0

        for f in files:
            try:
                item = json.loads(f.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as e:
                errored += 1
                log.warning("lane_c_read_failed file=%s err=%s", f.name, e)
                continue

            confidence = (item.get("analysis", {}) or {}).get("confidence")
            if confidence not in _ACCEPTED_CONFIDENCE:
                skipped_low += 1
                continue

            copy = build_copy(item, lang=self.lang)
            blob = copy["caption"] + " " + " ".join(copy["thread"]) + " " + copy["alt_text"]
            v = find_violations(blob)
            if v:
                violations += 1
                log.warning("lane_c_quarantined event_id=%s violations=%s",
                            copy.get("event_id"), v)
                continue

            self._write(date, copy)
            generated += 1

        return {
            "date": date,
            "total": len(files),
            "generated": generated,
            "skipped_low_confidence": skipped_low,
            "violations": violations,
            "errored": errored,
        }

    def _write(self, date: str, copy: dict) -> Path:
        d = self.out_dir / date
        d.mkdir(parents=True, exist_ok=True)
        out = d / f"{copy['event_id']}.json"
        out.write_text(json.dumps(copy, ensure_ascii=False, indent=2), encoding="utf-8")
        return out


def main(argv: Optional[list[str]] = None) -> dict:
    """Cron entry: Lane B analysis dir → compliance-gated copy drafts."""
    import argparse
    import os

    ap = argparse.ArgumentParser(description="Lane C — analysis → platform copy drafts")
    ap.add_argument("--analysis", default=os.environ.get(
        "EFLOUD_LANE_B_ARTIFACTS", "/tmp/lane-b") + "/analysis")
    ap.add_argument("--out", default=os.environ.get("EFLOUD_LANE_C_OUT", "/tmp/lane-c"))
    ap.add_argument("--date", required=True, help="UTC date YYYY-MM-DD")
    ap.add_argument("--lang", default="tr")
    args = ap.parse_args(argv)

    summary = LaneCCopywriter(
        analysis_dir=args.analysis, out_dir=args.out, lang=args.lang
    ).run(date=args.date)
    print(json.dumps(summary, ensure_ascii=False))
    return summary


__all__ = ["LaneCCopywriter", "build_copy", "main"]


if __name__ == "__main__":  # pragma: no cover
    main()
