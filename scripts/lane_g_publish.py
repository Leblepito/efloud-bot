"""Lane G publish runner — approved bundles → Lane E dispatch.

The last link of the chain. Reads the ``approved`` post bundles written by
``scripts/lane_g_social.py`` and hands each to ``scripts/lane_e/publisher.py``,
which dispatches to the platform adapters in ``backend/social/`` (X via xurl,
Instagram Graph, YouTube Data API).

Safety posture — three independent gates, all default-closed:

  1. bundles are ``pending_review`` unless Lane G ran with ``--auto-approve``;
     this runner only ever touches ``approved`` ones;
  2. every publisher is flag-gated OFF (``X_API_ENABLED`` / ``INSTAGRAM_ENABLED``
     / ``YOUTUBE_ENABLED``) — with the flags unset the run is a no-op that still
     exercises the whole path;
  3. ``--dry-run`` (default) never calls a publisher at all; real dispatch needs
     an explicit ``--live``.

Publishing is idempotent on ``(draft_id, platform)`` inside Lane E's own state
file, so a re-run cannot double-post.
"""
from __future__ import annotations

import json
import logging
import os
import sys
from pathlib import Path
from typing import Callable, Optional

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from scripts.lane_e.publisher import LaneEPublisher
from scripts.lane_e.publishers.base import PublishResult, Publisher
from scripts.lane_g_social import load_bundles

log = logging.getLogger("efloud.lane_g_publish")


class DryRunPublisher:
    """Records what *would* be published without touching any network.

    Mirrors the ``Publisher`` protocol. ``enabled`` is True so Lane E exercises
    the full dispatch path (envelope build + compliance re-check + idempotency
    state) — the only thing that does not happen is the API call.
    """

    def __init__(self, name: str = "dry_run"):
        self.name = name
        self.enabled = True
        self.calls: list[dict] = []

    def publish(self, envelope: dict) -> PublishResult:
        self.calls.append(dict(envelope))
        log.info("dry_run_publish draft=%s media=%s chars=%d",
                 envelope.get("draft_id"), envelope.get("media"),
                 len(envelope.get("text") or ""))
        return PublishResult(platform=self.name, ok=True,
                             ref=f"dryrun:{envelope.get('draft_id')}")


class PlatformClientPublisher:
    """Adapts a ``backend/social`` client to the Lane E ``Publisher`` protocol.

    The clients expect a ``ContentDraft``-shaped object with ``.body`` and
    ``.meta``; Lane E hands over an envelope dict. This wraps the envelope in a
    tiny shim carrying the media list so the client's own ``post_draft`` picks
    the right asset (image for IG, MP4 for YouTube Shorts).
    """

    def __init__(self, name: str, client):
        self.name = name
        self._client = client

    @property
    def enabled(self) -> bool:
        """Live only when the client's own env flag + credentials are set."""
        try:
            return bool(self._client.is_active())
        except Exception as e:
            log.warning("publisher_is_active_failed platform=%s err=%s", self.name, e)
            return False

    def publish(self, envelope: dict) -> PublishResult:
        draft = _DraftShim(text=envelope.get("text", ""),
                           media=list(envelope.get("media") or []))
        try:
            res = self._client.post_draft(draft)
        except Exception as e:
            return PublishResult(platform=self.name, ok=False, error=str(e))
        ok = bool(getattr(res, "ok", False))
        return PublishResult(
            platform=self.name, ok=ok,
            ref=getattr(res, "post_url", None) or getattr(res, "post_id", None),
            error=None if ok else (getattr(res, "stderr", None) or "publish failed"),
        )


class _DraftShim:
    """Minimal ContentDraft stand-in for the backend/social clients."""

    def __init__(self, text: str, media: list[str]):
        self.body = text
        self.meta = {"media": media}
        self.lang = "tr"
        self.post_type = "signal"


def build_publishers(*, dry_run: bool = True,
                     platforms: Optional[list[str]] = None) -> list[Publisher]:
    """Assemble the publisher list for one run.

    ``dry_run`` returns a single recording publisher. Live mode wires the real
    ``backend/social`` clients — each still self-gates on its own env flag, so
    an un-configured platform is simply skipped rather than failing.
    """
    if dry_run:
        return [DryRunPublisher()]

    wanted = set(platforms or ["x", "instagram", "youtube"])
    out: list[Publisher] = []
    if "x" in wanted:
        try:
            from backend.social.xurl_client import XurlClient
            out.append(PlatformClientPublisher("x", XurlClient()))
        except Exception as e:
            log.warning("publisher_init_failed platform=x err=%s", e)
    if "instagram" in wanted or "ig_reels" in wanted:
        try:
            from backend.social.instagram_client import InstagramClient
            out.append(PlatformClientPublisher("instagram", InstagramClient()))
        except Exception as e:
            log.warning("publisher_init_failed platform=instagram err=%s", e)
    if "youtube" in wanted:
        try:
            from backend.social.youtube_client import YouTubeClient
            out.append(PlatformClientPublisher("youtube", YouTubeClient()))
        except Exception as e:
            log.warning("publisher_init_failed platform=youtube err=%s", e)
    return out


def run(
    *,
    bundle_dir,
    date: str,
    state_path,
    dry_run: bool = True,
    publishers: Optional[list[Publisher]] = None,
    notifier: Optional[Callable[[str], None]] = None,
) -> dict:
    """Dispatch every ``approved`` bundle for ``date``. Returns a summary."""
    bundles = load_bundles(bundle_dir, date, state="approved")
    if not bundles:
        summary = {"date": date, "approved": 0, "published": 0, "failed": 0,
                   "skipped": 0, "dry_run": dry_run, "results": []}
        _notify(notifier, summary)
        return summary

    pubs = publishers if publishers is not None else build_publishers(dry_run=dry_run)
    lane_e = LaneEPublisher(publishers=pubs, state_path=state_path)

    published = failed = skipped = 0
    results = []
    for b in bundles:
        # Lane E only accepts state == "approved" and re-runs the compliance
        # check on the envelope text itself (defence in depth).
        res = lane_e.publish_draft({"draft_id": b["draft_id"], "state": "approved",
                                    "payload": b.get("payload", {})})
        results.append({"draft_id": b["draft_id"], "platform_target": b.get("platform"),
                        **res})
        if res.get("published"):
            published += 1
        if res.get("failed"):
            failed += 1
        if res.get("status") == "already_published":
            skipped += 1

    summary = {"date": date, "approved": len(bundles), "published": published,
               "failed": failed, "skipped": skipped, "dry_run": dry_run,
               "results": results}
    _notify(notifier, summary)
    return summary


def _notify(notifier: Optional[Callable[[str], None]], s: dict) -> None:
    if notifier is None:
        return
    mode = "DRY-RUN" if s["dry_run"] else "LIVE"
    msg = (f"[Lane G publish · {mode}] {s['date']}: {s['published']}/{s['approved']} "
           f"published, {s['failed']} failed, {s['skipped']} already done")
    try:
        notifier(msg)
    except Exception as e:
        log.warning("lane_g_publish_notify_failed err=%s", e)


def main(argv: Optional[list[str]] = None) -> dict:
    """Cron entry: approved Lane G bundles → platform dispatch."""
    import argparse

    ap = argparse.ArgumentParser(
        description="Lane G publish runner — approved bundles → Lane E dispatch")
    ap.add_argument("--bundles", default=os.environ.get("EFLOUD_LANE_G_OUT", "/tmp/lane-g"))
    ap.add_argument("--date", required=True, help="UTC date YYYY-MM-DD")
    ap.add_argument("--state", default=os.environ.get(
        "EFLOUD_LANE_E_STATE", "state/lane_e/publish_state.json"))
    ap.add_argument("--live", action="store_true",
                    help="actually dispatch (default: dry-run, no network)")
    args = ap.parse_args(argv)

    summary = run(bundle_dir=args.bundles, date=args.date, state_path=args.state,
                  dry_run=not args.live)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return summary


__all__ = ["DryRunPublisher", "PlatformClientPublisher", "build_publishers",
           "run", "main"]


if __name__ == "__main__":  # pragma: no cover
    main()
