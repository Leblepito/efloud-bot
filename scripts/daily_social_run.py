"""Daily social-content runner — one cron tick, whole chain.

Wires the whole pipeline behind a single command so a cron entry does not have
to chain five module invocations and keep their paths in sync:

    Lane A jobs (JSONL, written by the live bot)
      → Lane B  analysis artifacts
      → Lane C  compliance-gated copy (+ numeric levels)
      → Lane D  annotated chart PNGs        (scripts/chart_render.py)
      → Lane G  per-platform bundles + clips (scripts/lane_g_social.py)
      → Lane G  publish dispatch             (scripts/lane_g_publish.py)

Default posture is **safe**: charts and clips are generated, bundles land in
``pending_review``, and the publish step runs as a dry-run. Going live needs two
explicit opt-ins (``--auto-approve`` and ``--live``) *plus* the per-platform env
flags (``X_API_ENABLED`` / ``INSTAGRAM_ENABLED`` / ``YOUTUBE_ENABLED``), so no
single mistake can start posting.

Video backend is ffmpeg (offline, pixel-exact). The Higgsfield generative
backend is deliberately NOT selectable here: it rewrites price labels on the
chart (see the warning in ``scripts/video_render.py``), which must never happen
to a published signal.

Cron example (chart + clip + bundles, nothing published):

    0 * * * * cd /opt/efloud-bot && python -m scripts.daily_social_run \
        --date "$(date -u +%%F)" >> /app/logs/social_run.log 2>&1
"""
from __future__ import annotations

import json
import logging
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Optional

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from scripts.chart_render import chart_renderer
from scripts.lane_b_consumer import LaneBConsumer, _dry_run_processor
from scripts.lane_c_copywriter import LaneCCopywriter
from scripts.lane_d_visual import LaneDVisual
from scripts.lane_g_social import DEFAULT_PLATFORMS, LaneGOrchestrator
from scripts.lane_g_publish import run as publish_run

log = logging.getLogger("efloud.daily_social")


def _utc_today() -> str:
    return datetime.now(timezone.utc).date().isoformat()


def run_all(
    *,
    date: Optional[str] = None,
    jobs_path: str | Path = "/app/data/content_jobs",
    work_dir: str | Path = "/tmp/efloud-social",
    cache_dir: str | Path = "cache/ohlcv",
    platforms: Optional[list[str]] = None,
    clip_seconds: float = 8.0,
    auto_approve: bool = False,
    live: bool = False,
    allow_fetch: bool = False,
    lane_b_processor: Optional[Callable[[dict], dict]] = None,
    notifier: Optional[Callable[[str], None]] = None,
) -> dict:
    """Run one full tick. Returns a per-lane summary dict."""
    date = date or _utc_today()
    work = Path(work_dir)
    analysis_dir = work / "analysis"
    copy_dir = work / "copy"
    visual_dir = work / "visual"
    bundle_dir = work / "bundles"
    state_dir = work / "state"

    # Lane B — analysis artifacts. The dry-run processor is used unless a real
    # one is injected: the live Manus processor needs an API key that the
    # chart/clip path does not require, and the levels it forwards come straight
    # from the Lane A signal either way.
    b = LaneBConsumer(
        jobs_path=jobs_path, state_path=state_dir, artifacts_path=work,
        processor=lane_b_processor or _signal_passthrough_processor,
    ).run_batch(date)

    # Lane C — compliance-gated copy + numeric levels for the chart.
    c = LaneCCopywriter(analysis_dir=analysis_dir, out_dir=copy_dir).run(date)

    # Lane D — real annotated chart pixels (falls back to a manifest per event
    # when the candle cache has no data for that symbol/timeframe).
    def _renderer(spec: dict, fmt: str, base: Path) -> Path:
        spec = {**spec, "cache_dir": str(cache_dir), "allow_fetch": allow_fetch}
        return chart_renderer(spec, fmt, base)

    d = LaneDVisual(copy_dir=copy_dir, out_dir=visual_dir, renderer=_renderer).run(date)

    # Lane G — per-platform bundles + short-form clips (ffmpeg, pixel-exact).
    g = LaneGOrchestrator(
        copy_dir=copy_dir, visual_dir=visual_dir, out_dir=bundle_dir,
        state_path=state_dir / "lane_g_state.json",
        platforms=platforms or list(DEFAULT_PLATFORMS),
        clip_seconds=clip_seconds, video_backend="ffmpeg",
        auto_approve=auto_approve,
    ).run(date)

    # Publish — dry-run unless --live, and every publisher still self-gates.
    p = publish_run(
        bundle_dir=bundle_dir, date=date,
        state_path=state_dir / "lane_e_publish_state.json",
        dry_run=not live,
    )

    summary = {
        "date": date, "lane_b": b, "lane_c": c, "lane_d": d, "lane_g": g,
        "publish": {k: v for k, v in p.items() if k != "results"},
        "auto_approve": auto_approve, "live": live,
    }
    _notify(notifier, summary)
    return summary


def _signal_passthrough_processor(event: dict) -> dict:
    """Offline Lane B processor: Lane A signal → analysis artifact, no network.

    The chart renderer needs the numeric levels, not prose, and those already
    live in the Lane A event. This keeps the whole chain runnable with zero
    external dependencies (no Manus, no Gemini, no cost) while still producing
    a real analysis artifact for Lane C to gate on.

    ``confidence`` is set from the signal's own confluence score so Lane C's
    ``confidence >= medium`` gate stays meaningful instead of rubber-stamping
    every event: a low-confluence setup is not worth posting.
    """
    sig = event.get("signal", {}) or {}
    try:
        confluence = int(sig.get("confluence") or 0)
    except (TypeError, ValueError):
        confluence = 0
    confidence = "high" if confluence >= 75 else "medium" if confluence >= 60 else "low"

    direction = str(sig.get("direction") or "").upper()
    bias = "bullish" if direction == "LONG" else "bearish" if direction == "SHORT" else "neutral"
    reasons = [r for r in (sig.get("reasons") or []) if isinstance(r, str)]
    structure = ", ".join(reasons[:3]) if reasons else f"{bias} SMC setup"

    return {
        "event_id": event.get("event_id"),
        "symbol": sig.get("symbol"),
        "timeframe": sig.get("timeframe"),
        "direction": direction,
        "entry": sig.get("entry"),
        "sl": sig.get("sl"),
        "tp1": sig.get("tp1"),
        "tp2": sig.get("tp2"),
        "confluence": sig.get("confluence"),
        "analysis": {
            "structure": structure,
            "confidence": confidence,
            "summary": f"{bias.capitalize()} yapı, {sig.get('timeframe')} onayı",
            "invalidation": "SL seviyesi altında/üstünde kapanış",
            "smc_zones": [],
        },
        "cost_usd": 0.0,
    }


def _notify(notifier: Optional[Callable[[str], None]], s: dict) -> None:
    if notifier is None:
        return
    mode = "LIVE" if s["live"] else "dry-run"
    msg = (f"[Social {mode}] {s['date']}: "
           f"{s['lane_d'].get('generated', 0)} chart, "
           f"{s['lane_g'].get('clips_rendered', 0)} clip, "
           f"{s['lane_g'].get('packaged', 0)} bundle, "
           f"{s['publish'].get('published', 0)} published, "
           f"{s['lane_g'].get('blocked_compliance', 0)} blocked")
    try:
        notifier(msg)
    except Exception as e:
        log.warning("daily_social_notify_failed err=%s", e)


def main(argv: Optional[list[str]] = None) -> dict:
    import argparse

    ap = argparse.ArgumentParser(
        description="Daily social pipeline: Lane A jobs → charts → clips → bundles → publish")
    ap.add_argument("--date", default=None, help="UTC date YYYY-MM-DD (default: today)")
    ap.add_argument("--jobs", default=os.environ.get(
        "EFLOUD_CONTENT_JOBS_PATH", "/app/data/content_jobs"))
    ap.add_argument("--work", default=os.environ.get(
        "EFLOUD_SOCIAL_WORK", "/tmp/efloud-social"))
    ap.add_argument("--cache-dir", default=os.environ.get(
        "EFLOUD_OHLCV_CACHE", "cache/ohlcv"))
    ap.add_argument("--platforms", default=",".join(DEFAULT_PLATFORMS))
    ap.add_argument("--clip-seconds", type=float, default=8.0)
    ap.add_argument("--allow-fetch", action="store_true",
                    help="allow a live Binance pull when the candle cache misses")
    ap.add_argument("--auto-approve", action="store_true",
                    help="mark bundles approved (still needs --live to publish)")
    ap.add_argument("--live", action="store_true",
                    help="really dispatch to platforms (needs the per-platform env flags too)")
    args = ap.parse_args(argv)

    summary = run_all(
        date=args.date, jobs_path=args.jobs, work_dir=args.work,
        cache_dir=args.cache_dir,
        platforms=[p.strip() for p in args.platforms.split(",") if p.strip()],
        clip_seconds=args.clip_seconds, auto_approve=args.auto_approve,
        live=args.live, allow_fetch=args.allow_fetch,
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return summary


__all__ = ["run_all", "main"]


if __name__ == "__main__":  # pragma: no cover
    main()
