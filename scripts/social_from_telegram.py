"""Social drafts from the Telegram community channel — collect → draft → approve → publish.

Thin adapter over the existing Lane A→G chain. It does **not** reimplement any
lane: it feeds ``scripts.daily_social_run.run_all`` a jobs directory produced by
``scripts.telegram_channel_collector`` and adds the operator verbs around it.

    collect   getUpdates → {jobs}/{YYYY-MM-DD}.jsonl   (Lane A-shaped feed)
    draft     Lane B → C → D → G, bundles land in ``pending_review``
    approve   pending_review → approved, one (event, platform) or a whole day
    publish   approved → Lane E dispatch, dry-run unless ``--live``

Safety posture is the pipeline's own, unchanged: nothing is published without an
approved bundle, ``--live``, and the per-platform env flags
(``X_API_ENABLED`` / ``INSTAGRAM_ENABLED``). ``--auto-approve`` is never implied.

Only ``x`` and ``instagram`` are packaged by default — both take the 1080×1350
still, so no ffmpeg clip is needed for this flow.
"""
from __future__ import annotations

import json
import logging
import os
import shutil
import sys
from pathlib import Path
from typing import Optional

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from scripts.content_compliance import find_violations, has_disclaimer
from scripts.daily_social_run import run_all
from scripts.lane_g_publish import run as publish_run
from scripts.lane_g_social import approve_bundle, load_bundles
from scripts.telegram_channel_collector import TelegramChannelCollector

log = logging.getLogger("efloud.social_from_telegram")

DEFAULT_PLATFORMS = ["x", "instagram"]
DEFAULT_MAX_BYTES = 150 * 1024


def _channel_processor(event: dict) -> dict:
    """Lane B processor for channel-sourced events (offline, no network).

    A channel post is already an operator-published signal, so the confidence
    floor is ``medium`` — Lane C's gate exists to drop weak *generated* setups,
    not to re-litigate a post the operator already sent. A post that carries an
    explicit high confluence still upgrades to ``high``.
    """
    sig = event.get("signal", {}) or {}
    detail = sig.get("reasons_detail") or {}
    try:
        confluence = int(sig.get("confluence") or 0)
    except (TypeError, ValueError):
        confluence = 0
    confidence = "high" if confluence >= 75 else "medium"

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
            "source": "telegram_channel",
            "confluence_source": detail.get("confluence_source"),
        },
        "cost_usd": 0.0,
    }


def draft(
    *,
    date: str,
    jobs_dir,
    work_dir,
    cache_dir="cache/ohlcv",
    platforms: Optional[list[str]] = None,
    allow_fetch: bool = False,
    auto_approve: bool = False,
    live: bool = False,
) -> dict:
    """Run Lane B→G for one day's channel feed. Bundles stay ``pending_review``."""
    return run_all(
        date=date,
        jobs_path=jobs_dir,
        work_dir=work_dir,
        cache_dir=cache_dir,
        platforms=platforms or list(DEFAULT_PLATFORMS),
        auto_approve=auto_approve,
        live=live,
        allow_fetch=allow_fetch,
        lane_b_processor=_channel_processor,
    )


def approve(*, bundle_dir, date: str, event_id: Optional[str] = None,
            platform: Optional[str] = None) -> dict:
    """Flip ``pending_review`` bundles to ``approved`` (operator action)."""
    approved, missing = [], []
    for b in load_bundles(bundle_dir, date, state="pending_review"):
        if event_id and b.get("event_id") != event_id:
            continue
        if platform and b.get("platform") != platform:
            continue
        path = approve_bundle(bundle_dir, date, b["event_id"], b["platform"])
        if path is None:
            missing.append(b["draft_id"])
        else:
            approved.append(b["draft_id"])
    return {"date": date, "approved": approved, "missing": missing}


def publish(*, bundle_dir, date: str, state_path, live: bool = False) -> dict:
    """Dispatch approved bundles. Dry-run unless ``live`` (flags still gate)."""
    return publish_run(bundle_dir=bundle_dir, date=date, state_path=state_path,
                       dry_run=not live)


def export_bundles(*, bundle_dir, date: str, out_dir,
                   max_bytes: int = DEFAULT_MAX_BYTES, note: str = "") -> dict:
    """Copy a day's bundle media + captions into one flat review directory.

    Writes ``{event_id}.{platform}.png`` / ``.caption.txt`` plus a ``manifest.json``
    carrying byte sizes, the compliance verdict and the bundle state, so a
    reviewer can check the exact files without walking the work tree.
    """
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    files, oversize = [], []
    for b in load_bundles(bundle_dir, date):
        payload = b.get("payload") or {}
        caption = payload.get("caption") or ""
        violations = find_violations(caption)
        entry = {
            "draft_id": b.get("draft_id"),
            "event_id": b.get("event_id"),
            "platform": b.get("platform"),
            "symbol": b.get("symbol"),
            "state": b.get("state"),
            "violations": violations,
            "disclaimer_present": has_disclaimer(caption),
            "caption_chars": len(caption),
            "media": [],
        }
        for src in payload.get("media") or []:
            src_path = Path(src)
            if not src_path.exists():
                entry["media"].append({"src": src, "missing": True})
                continue
            dst = out / f"{b['event_id']}.{b['platform']}{src_path.suffix}"
            shutil.copyfile(src_path, dst)
            size = dst.stat().st_size
            entry["media"].append({"path": dst.name, "bytes": size})
            if size > max_bytes:
                oversize.append(dst.name)
                log.warning("export_oversize file=%s bytes=%d limit=%d",
                            dst.name, size, max_bytes)
        cap_path = out / f"{b['event_id']}.{b['platform']}.caption.txt"
        cap_path.write_text(caption + "\n", encoding="utf-8")
        entry["caption_file"] = cap_path.name
        entry["caption_bytes"] = cap_path.stat().st_size
        files.append(entry)

    manifest = {
        "date": date,
        "note": note,
        "bundle_dir": str(bundle_dir),
        "max_bytes": max_bytes,
        "oversize": oversize,
        "files": files,
    }
    (out / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"out_dir": str(out), "files": len(files), "oversize": oversize}


def main(argv: Optional[list[str]] = None) -> dict:
    import argparse

    ap = argparse.ArgumentParser(
        description="Telegram community channel → Instagram/X drafts (approved, default-closed)")
    sub = ap.add_subparsers(dest="cmd", required=True)

    def _common(p):
        p.add_argument("--date", required=True, help="UTC date YYYY-MM-DD")
        p.add_argument("--jobs", default=os.environ.get(
            "EFLOUD_TG_FEED_DIR", "/app/data/content_jobs"))
        p.add_argument("--work", default=os.environ.get(
            "EFLOUD_SOCIAL_WORK", "/tmp/efloud-social"))

    c = sub.add_parser("collect", help="poll new channel posts into the JSONL feed")
    c.add_argument("--out", default=os.environ.get(
        "EFLOUD_TG_FEED_DIR", "/app/data/content_jobs"))
    c.add_argument("--state", default=os.environ.get(
        "EFLOUD_TG_COLLECTOR_STATE", "state/tg_collector/state.json"))
    c.add_argument("--channel-id", default=os.environ.get("EFLOUD_CUSTOMER_TG_CHANNEL_ID"))
    c.add_argument("--from-file", default=None, help="replay a JSON fixture offline")

    d = sub.add_parser("draft", help="Lane B→G, bundles land in pending_review")
    _common(d)
    d.add_argument("--cache-dir", default=os.environ.get("EFLOUD_OHLCV_CACHE", "cache/ohlcv"))
    d.add_argument("--platforms", default=",".join(DEFAULT_PLATFORMS))
    d.add_argument("--allow-fetch", action="store_true")
    d.add_argument("--auto-approve", action="store_true",
                   help="mark bundles approved (operator opt-in; still needs --live)")
    d.add_argument("--export-dir", default=None,
                   help="copy media + captions + manifest.json into this directory")
    d.add_argument("--note", default="", help="free-text note recorded in the export manifest")

    a = sub.add_parser("approve", help="pending_review → approved")
    _common(a)
    a.add_argument("--event-id", default=None)
    a.add_argument("--platform", default=None, choices=DEFAULT_PLATFORMS)

    p = sub.add_parser("publish", help="approved → Lane E dispatch")
    _common(p)
    p.add_argument("--state", default=os.environ.get(
        "EFLOUD_LANE_E_STATE", "state/lane_e/publish_state.json"))
    p.add_argument("--live", action="store_true",
                   help="really dispatch (needs X_API_ENABLED / INSTAGRAM_ENABLED)")

    args = ap.parse_args(argv)
    work = Path(getattr(args, "work", "/tmp/efloud-social"))
    bundle_dir = work / "bundles"

    if args.cmd == "collect":
        if not args.channel_id:
            raise SystemExit("--channel-id (or EFLOUD_CUSTOMER_TG_CHANNEL_ID) is required")
        collector = TelegramChannelCollector(
            out_dir=args.out, state_path=args.state, channel_id=args.channel_id,
            token=os.environ.get("EFLOUD_CUSTOMER_TG_TOKEN"),
        )
        if args.from_file:
            summary = collector.ingest_posts(
                json.loads(Path(args.from_file).read_text(encoding="utf-8")))
        else:
            summary = collector.collect()
    elif args.cmd == "draft":
        summary = draft(
            date=args.date, jobs_dir=args.jobs, work_dir=work,
            cache_dir=args.cache_dir,
            platforms=[x.strip() for x in args.platforms.split(",") if x.strip()],
            allow_fetch=args.allow_fetch, auto_approve=args.auto_approve,
        )
        if args.export_dir:
            summary["export"] = export_bundles(
                bundle_dir=bundle_dir, date=args.date, out_dir=args.export_dir,
                note=args.note)
    elif args.cmd == "approve":
        summary = approve(bundle_dir=bundle_dir, date=args.date,
                          event_id=args.event_id, platform=args.platform)
    else:
        summary = publish(bundle_dir=bundle_dir, date=args.date,
                          state_path=args.state, live=args.live)

    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return summary


__all__ = ["DEFAULT_PLATFORMS", "DEFAULT_MAX_BYTES", "draft", "approve",
           "publish", "export_bundles", "main"]


if __name__ == "__main__":  # pragma: no cover
    main()
