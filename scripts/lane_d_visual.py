"""Lane D visual harness — Phase 4a (PR #14).

Consumes Lane C copy drafts and builds a branded visual spec (chart + text
overlay) in two formats — a *still* (1080×1350 portrait post) and a *vertical*
(1080×1920 story/reels). The actual pixels are produced by an injected
``renderer``:

- **prod:** ``pillow_renderer`` (mirrors ``u2algo-site/scripts/generate-launch-pngs.py``)
  when Pillow is installed, or the higgsfield image MCP via a thin adapter;
- **default / tested:** ``manifest_renderer`` — a dependency-free render manifest
  (the downstream renderer / higgsfield consumes it). No native deps in CI.

Overlay text is re-checked against the content-compliance rules (defense in
depth). Draft-only: writes to local disk, posts nothing, touches no trade state.
"""
from __future__ import annotations

import json
import logging
import sys
from pathlib import Path
from typing import Callable, Optional

# Allow `python scripts/lane_d_visual.py ...` (repo root not otherwise on
# sys.path when invoked as a file rather than `-m`).
_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from engine.content_jobs import COMPLIANCE_TR
from scripts.content_compliance import find_violations

log = logging.getLogger("efloud.lane_d")

# (width, height). still = IG portrait 4:5; vertical = story/reels 9:16.
VISUAL_FORMATS: dict[str, tuple[int, int]] = {
    "still": (1080, 1350),
    "vertical": (1080, 1920),
}

# Brand palette (sourced from u2algo-site/scripts/generate-launch-pngs.py).
PALETTE = {
    "bg": [5, 5, 16], "panel": [12, 18, 36], "cyan": [0, 240, 255],
    "ink": [248, 250, 252], "muted": [148, 163, 184],
    "green": [0, 255, 136], "red": [255, 51, 102], "warn": [251, 191, 36],
}

Renderer = Callable[[dict, str, Path], Path]


def _split_disclaimer(caption: str) -> tuple[str, str]:
    if COMPLIANCE_TR in caption:
        return caption.split(COMPLIANCE_TR)[0].rstrip(), COMPLIANCE_TR
    return (caption or "").rstrip(), ""


def build_visual_spec(copy: dict, chart_path: Optional[str] = None) -> dict:
    """Build a format-agnostic render spec from a Lane C copy draft."""
    symbol = copy.get("symbol", "?")
    tf = copy.get("timeframe", "?")
    body, footer = _split_disclaimer(copy.get("caption", ""))
    overlay = {
        "headline": f"{symbol} · {tf}",
        "body": body,
        "footer": footer,
        "alt": copy.get("alt_text", ""),
    }
    spec = {
        "event_id": copy.get("event_id"),
        "symbol": symbol,
        "chart_path": chart_path,
        "overlay": overlay,
        "formats": list(VISUAL_FORMATS),
        "palette": PALETTE,
    }
    # Trade levels (entry/SL/TP1/TP2) travel with the copy draft so the chart
    # renderer can draw the annotated price levels. Absent for non-signal copy
    # (educational / recap posts) — chart_renderer then falls back to a manifest.
    levels = copy.get("levels")
    if levels:
        spec["levels"] = levels
    return spec


def manifest_renderer(spec: dict, fmt: str, base: Path) -> Path:
    """Default renderer — writes a dependency-free render manifest JSON."""
    w, h = VISUAL_FORMATS[fmt]
    out = Path(str(base) + f".{fmt}.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "event_id": spec.get("event_id"),
        "format": fmt,
        "width": w,
        "height": h,
        "chart_path": spec.get("chart_path"),
        "overlay": spec.get("overlay"),
        "palette": spec.get("palette"),
    }
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return out


def pillow_renderer(spec: dict, fmt: str, base: Path) -> Path:  # pragma: no cover - needs Pillow
    """Prod renderer — rasterises the overlay onto a branded canvas via Pillow.

    Only used where Pillow is installed (mirrors generate-launch-pngs.py). Falls
    back to ``manifest_renderer`` if Pillow is unavailable so the batch never
    crashes on a missing native dependency.
    """
    try:
        from PIL import Image, ImageDraw
    except ImportError:
        return manifest_renderer(spec, fmt, base)
    w, h = VISUAL_FORMATS[fmt]
    img = Image.new("RGB", (w, h), tuple(PALETTE["bg"]))
    draw = ImageDraw.Draw(img)
    ov = spec.get("overlay", {})
    y = 80
    for line in (ov.get("headline", ""), ov.get("body", ""), ov.get("footer", "")):
        draw.multiline_text((72, y), line, fill=tuple(PALETTE["ink"]))
        y += 220
    out = Path(str(base) + f".{fmt}.png")
    out.parent.mkdir(parents=True, exist_ok=True)
    img.save(out)
    return out


class LaneDVisual:
    def __init__(self, *, copy_dir, out_dir, renderer: Optional[Renderer] = None,
                 formats=None):
        self.copy_dir = Path(copy_dir)
        self.out_dir = Path(out_dir)
        self.renderer = renderer or manifest_renderer
        self.formats = list(formats) if formats else list(VISUAL_FORMATS)

    def run(self, date: str) -> dict:
        src = self.copy_dir / date
        files = sorted(src.glob("*.json")) if src.exists() else []
        generated = quarantined = errored = rendered_files = 0

        for f in files:
            try:
                copy = json.loads(f.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as e:
                errored += 1
                log.warning("lane_d_read_failed file=%s err=%s", f.name, e)
                continue

            spec = build_visual_spec(copy, chart_path=copy.get("chart_path"))
            ov = spec["overlay"]
            blob = " ".join([ov["headline"], ov["body"], ov["footer"], ov["alt"]])
            if find_violations(blob):
                quarantined += 1
                log.warning("lane_d_quarantined event_id=%s", spec.get("event_id"))
                continue

            base = self.out_dir / date / str(copy.get("event_id"))
            base.parent.mkdir(parents=True, exist_ok=True)
            for fmt in self.formats:
                self.renderer(spec, fmt, base)
                rendered_files += 1
            generated += 1

        return {
            "date": date,
            "total": len(files),
            "generated": generated,
            "quarantined": quarantined,
            "errored": errored,
            "rendered_files": rendered_files,
        }


def main(argv: Optional[list[str]] = None) -> dict:
    """Cron entry: Lane C copy dir → branded visual drafts (manifest by default)."""
    import argparse
    import os

    ap = argparse.ArgumentParser(description="Lane D — copy → branded visual drafts")
    ap.add_argument("--copy", default=os.environ.get("EFLOUD_LANE_C_OUT", "/tmp/lane-c"))
    ap.add_argument("--out", default=os.environ.get("EFLOUD_LANE_D_OUT", "/tmp/lane-d"))
    ap.add_argument("--date", required=True, help="UTC date YYYY-MM-DD")
    ap.add_argument("--pillow", action="store_true", help="rasterise with Pillow if available")
    ap.add_argument("--chart", action="store_true",
                    help="render annotated entry/SL/TP charts (scripts.chart_render)")
    args = ap.parse_args(argv)

    if args.chart:
        from scripts.chart_render import chart_renderer
        renderer = chart_renderer
    elif args.pillow:
        renderer = pillow_renderer
    else:
        renderer = manifest_renderer
    summary = LaneDVisual(copy_dir=args.copy, out_dir=args.out, renderer=renderer).run(date=args.date)
    print(json.dumps(summary, ensure_ascii=False))
    return summary


__all__ = ["LaneDVisual", "build_visual_spec", "manifest_renderer",
           "pillow_renderer", "VISUAL_FORMATS", "PALETTE", "main"]


if __name__ == "__main__":  # pragma: no cover
    main()
