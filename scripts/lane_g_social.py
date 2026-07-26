"""Lane G — social media orchestrator (chart + clip → approval → publish).

The missing seam between the offline draft pipeline (Lane B→D) and the
platform publishers (Lane E). One tick does:

  1. **collect** — read the day's Lane D visual output (annotated chart PNGs
     produced by ``scripts/chart_render.py``) plus the matching Lane C copy;
  2. **clip** — render a short-form MP4 per event via ``scripts/video_render.py``
     (ffmpeg offline by default, Higgsfield opt-in) for the video platforms;
  3. **package** — build one *post bundle* per platform target, each with the
     right media geometry, caption shape and the mandatory disclaimer;
  4. **gate** — re-run ``scripts/content_compliance.find_violations`` on every
     caption (defence in depth: Lane C already gated, this catches per-platform
     rewrites);
  5. **hand off** — write bundles as ``pending_review`` and (only when
     ``auto_approve`` is explicitly on) mark them ``approved`` for Lane E.

**Publishing is never done here.** Lane G produces approved-or-pending bundles;
``scripts/lane_e/publisher.py`` owns dispatch, and every publisher is flag-gated
OFF by default. So the default posture of a fully wired cron is: charts +
clips + captions generated automatically, nothing leaves the machine until the
operator approves and the platform flags are on.

Idempotent on ``(event_id, platform)`` via a JSON state file, so a re-run never
double-packages or double-publishes.

Platform targets (geometry chosen to match each platform's native format):
    x           still 1080×1350 + optional clip      (X/Twitter post)
    instagram   still 1080×1350                       (IG feed post)
    ig_reels    vertical clip 1080×1920               (Reels)
    youtube     vertical clip 1080×1920               (Shorts)
"""
from __future__ import annotations

import json
import logging
import os
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Optional

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from engine.content_jobs import COMPLIANCE_TR
from scripts.content_compliance import find_violations

log = logging.getLogger("efloud.lane_g")

# platform → (needs_clip, still_format, clip_format, caption_limit)
PLATFORM_SPECS: dict[str, dict] = {
    "x":         {"clip": False, "still": "still",    "clip_fmt": "vertical", "limit": 280},
    "instagram": {"clip": False, "still": "still",    "clip_fmt": None,       "limit": 2200},
    "ig_reels":  {"clip": True,  "still": "vertical", "clip_fmt": "vertical", "limit": 2200},
    "youtube":   {"clip": True,  "still": "vertical", "clip_fmt": "vertical", "limit": 5000},
}

DEFAULT_PLATFORMS = ["x", "instagram", "ig_reels", "youtube"]
DEFAULT_CLIP_SECONDS = 8.0

# Hashtags are appended per platform where they help discovery. Deliberately
# generic (no promise language) so they can never trip the compliance gate.
HASHTAGS = {
    "x": "#BTC #trading #SMC #algotrading",
    "instagram": "#trading #algotrading #smc #kripto #u2algo",
    "ig_reels": "#trading #algotrading #smc #kripto #u2algo",
    "youtube": "#trading #algotrading #smc",
}


@dataclass
class PostBundle:
    """One ready-to-publish package for a single (event, platform) pair."""

    event_id: str
    platform: str
    symbol: str
    caption: str
    media: list[str] = field(default_factory=list)
    thread: list[str] = field(default_factory=list)
    alt_text: str = ""
    state: str = "pending_review"
    violations: list[str] = field(default_factory=list)
    created_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    )

    @property
    def draft_id(self) -> str:
        """Stable per (event, platform) — the Lane E idempotency key."""
        return f"{self.event_id}:{self.platform}"

    def to_dict(self) -> dict:
        return {
            "draft_id": self.draft_id,
            "event_id": self.event_id,
            "platform": self.platform,
            "symbol": self.symbol,
            "state": self.state,
            "created_at": self.created_at,
            "violations": self.violations,
            # Lane E reads payload.caption / payload.media
            "payload": {
                "caption": self.caption,
                "media": self.media,
                "thread": self.thread,
                "alt_text": self.alt_text,
            },
        }


def _truncate_caption(text: str, limit: int) -> str:
    """Fit a caption to a platform limit while KEEPING the disclaimer.

    The disclaimer is legally mandated, so it is never what gets cut: the body
    is trimmed and the disclaimer is re-appended. If even the disclaimer alone
    exceeds the limit the disclaimer wins (a too-long post is a platform error;
    a disclaimer-less post is a compliance breach).
    """
    if len(text) <= limit:
        return text
    disclaimer = COMPLIANCE_TR
    body = text.split(disclaimer)[0].rstrip() if disclaimer in text else text
    room = limit - len(disclaimer) - 2  # "\n\n"
    if room <= 0:
        return disclaimer
    trimmed = body[:room].rstrip()
    return f"{trimmed}\n\n{disclaimer}"


def build_caption(copy: dict, platform: str) -> str:
    """Platform-shaped caption from a Lane C copy draft.

    X gets the tight single-post caption; IG/YouTube get the caption plus the
    thread lines as body paragraphs (they have room and reward detail).
    Hashtags are appended before truncation so a trim never leaves a dangling
    half-tag at the end.
    """
    spec = PLATFORM_SPECS.get(platform) or PLATFORM_SPECS["x"]
    caption = copy.get("caption", "") or ""
    tags = HASHTAGS.get(platform, "")

    if platform == "x":
        text = caption
    else:
        thread = [t for t in (copy.get("thread") or []) if t and t != COMPLIANCE_TR]
        body = caption.split(COMPLIANCE_TR)[0].rstrip() if COMPLIANCE_TR in caption else caption
        detail = "\n".join(f"• {t}" for t in thread)
        text = f"{body}\n\n{detail}\n\n{COMPLIANCE_TR}" if detail else caption

    if tags:
        text = f"{text}\n\n{tags}"
    if COMPLIANCE_TR not in text:  # never ship without it
        text = f"{text}\n\n{COMPLIANCE_TR}"
    return _truncate_caption(text, spec["limit"])


class LaneGOrchestrator:
    """Assemble per-platform post bundles from Lane C copy + Lane D charts."""

    def __init__(
        self,
        *,
        copy_dir,
        visual_dir,
        out_dir,
        state_path,
        platforms: Optional[list[str]] = None,
        clip_seconds: float = DEFAULT_CLIP_SECONDS,
        video_backend: Optional[str] = None,
        auto_approve: bool = False,
        clip_renderer: Optional[Callable[..., tuple[Path, str]]] = None,
        notifier: Optional[Callable[[str], None]] = None,
    ):
        self.copy_dir = Path(copy_dir)
        self.visual_dir = Path(visual_dir)
        self.out_dir = Path(out_dir)
        self.state_path = Path(state_path)
        self.platforms = list(platforms) if platforms else list(DEFAULT_PLATFORMS)
        self.clip_seconds = float(clip_seconds)
        self.video_backend = video_backend
        self.auto_approve = bool(auto_approve)
        self.clip_renderer = clip_renderer
        self.notifier = notifier

    # ── idempotency state: {event_id: {platform: {"state": ..., "bundle": path}}}
    def _load_state(self) -> dict:
        if not self.state_path.exists():
            return {}
        try:
            data = json.loads(self.state_path.read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else {}
        except (OSError, json.JSONDecodeError) as e:
            log.warning("lane_g_state_load_failed err=%s", e)
            return {}

    def _save_state(self, state: dict) -> None:
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        tmp = Path(str(self.state_path) + ".tmp")
        tmp.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(self.state_path)  # atomic

    # ── media discovery ─────────────────────────────────────────────────────
    def _still_for(self, date: str, event_id: str, fmt: str) -> Optional[Path]:
        p = self.visual_dir / date / f"{event_id}.{fmt}.png"
        return p if p.exists() else None

    def _render_clip(self, still: Path, date: str, event_id: str,
                     levels: dict, fmt: str) -> Optional[Path]:
        out = self.out_dir / date / "clips" / f"{event_id}.{fmt}.mp4"
        if out.exists():  # idempotent: a previous tick already rendered it
            return out
        renderer = self.clip_renderer
        if renderer is None:
            from scripts.video_render import render_clip
            renderer = render_clip
        try:
            path, backend = renderer(
                still, out, backend=self.video_backend, levels=levels,
                fmt=fmt, duration=self.clip_seconds,
            )
            log.info("lane_g_clip event_id=%s backend=%s path=%s", event_id, backend, path)
            return Path(path)
        except Exception as e:
            log.warning("lane_g_clip_failed event_id=%s err=%s", event_id, e)
            return None

    # ── one tick ────────────────────────────────────────────────────────────
    def run(self, date: str) -> dict:
        src = self.copy_dir / date
        files = sorted(src.glob("*.json")) if src.exists() else []
        state = self._load_state()

        packaged = skipped = blocked = errored = no_media = clips = 0
        bundles: list[PostBundle] = []

        for f in files:
            try:
                copy = json.loads(f.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as e:
                errored += 1
                log.warning("lane_g_read_failed file=%s err=%s", f.name, e)
                continue

            event_id = str(copy.get("event_id") or f.stem)
            symbol = copy.get("symbol", "?")
            levels = copy.get("levels") or {}
            done = state.setdefault(event_id, {})

            for platform in self.platforms:
                spec = PLATFORM_SPECS.get(platform)
                if spec is None:
                    log.warning("lane_g_unknown_platform platform=%s", platform)
                    continue
                if done.get(platform, {}).get("state") in ("pending_review", "approved", "published"):
                    skipped += 1
                    continue

                still = self._still_for(date, event_id, spec["still"])
                if still is None:
                    # Lane D produced no chart for this geometry (missing candle
                    # cache → manifest fallback). Without a chart there is no
                    # post worth making, so defer rather than ship text-only.
                    no_media += 1
                    log.warning("lane_g_no_still event_id=%s fmt=%s", event_id, spec["still"])
                    continue

                media = [str(still)]
                if spec["clip"] and spec["clip_fmt"]:
                    clip = self._render_clip(still, date, event_id, levels, spec["clip_fmt"])
                    if clip is None:
                        no_media += 1
                        continue
                    clips += 1
                    media = [str(clip)]  # video platforms take the clip as primary

                caption = build_caption(copy, platform)
                violations = find_violations(caption)
                bundle = PostBundle(
                    event_id=event_id, platform=platform, symbol=symbol,
                    caption=caption, media=media,
                    thread=list(copy.get("thread") or []),
                    alt_text=copy.get("alt_text", ""),
                    violations=violations,
                )
                if violations:
                    bundle.state = "blocked_compliance"
                    blocked += 1
                    log.warning("lane_g_blocked event_id=%s platform=%s violations=%s",
                                event_id, platform, violations)
                else:
                    bundle.state = "approved" if self.auto_approve else "pending_review"
                    packaged += 1

                path = self._write_bundle(date, bundle)
                done[platform] = {"state": bundle.state, "bundle": str(path)}
                bundles.append(bundle)

        self._save_state(state)
        summary = {
            "date": date,
            "copy_drafts": len(files),
            "packaged": packaged,
            "clips_rendered": clips,
            "skipped_already_done": skipped,
            "blocked_compliance": blocked,
            "missing_media": no_media,
            "errored": errored,
            "auto_approve": self.auto_approve,
            "platforms": self.platforms,
        }
        self._notify(summary)
        return summary

    def _write_bundle(self, date: str, bundle: PostBundle) -> Path:
        d = self.out_dir / date / "bundles"
        d.mkdir(parents=True, exist_ok=True)
        out = d / f"{bundle.event_id}.{bundle.platform}.json"
        out.write_text(json.dumps(bundle.to_dict(), ensure_ascii=False, indent=2),
                       encoding="utf-8")
        return out

    def _notify(self, s: dict) -> None:
        if self.notifier is None:
            return
        state_word = "APPROVED" if s["auto_approve"] else "pending review"
        msg = (f"[Lane G] {s['date']}: {s['packaged']} bundle {state_word}, "
               f"{s['clips_rendered']} clip, {s['blocked_compliance']} blocked, "
               f"{s['missing_media']} no-media ({', '.join(s['platforms'])})")
        try:
            self.notifier(msg)
        except Exception as e:
            log.warning("lane_g_notify_failed err=%s", e)


def load_bundles(out_dir, date: str, *, state: Optional[str] = None) -> list[dict]:
    """Read back the day's bundles (optionally filtered by state) — Lane E input."""
    d = Path(out_dir) / date / "bundles"
    if not d.exists():
        return []
    out = []
    for f in sorted(d.glob("*.json")):
        try:
            b = json.loads(f.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if state is None or b.get("state") == state:
            out.append(b)
    return out


def approve_bundle(out_dir, date: str, event_id: str, platform: str) -> Optional[Path]:
    """Flip one bundle pending_review → approved (operator action)."""
    p = Path(out_dir) / date / "bundles" / f"{event_id}.{platform}.json"
    if not p.exists():
        return None
    b = json.loads(p.read_text(encoding="utf-8"))
    if b.get("state") != "pending_review":
        return p
    b["state"] = "approved"
    b["approved_at"] = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    p.write_text(json.dumps(b, ensure_ascii=False, indent=2), encoding="utf-8")
    return p


def main(argv: Optional[list[str]] = None) -> dict:
    """Cron entry: Lane C copy + Lane D charts → per-platform post bundles."""
    import argparse

    ap = argparse.ArgumentParser(
        description="Lane G — package charts + clips + captions per platform")
    ap.add_argument("--copy", default=os.environ.get("EFLOUD_LANE_C_OUT", "/tmp/lane-c"))
    ap.add_argument("--visual", default=os.environ.get("EFLOUD_LANE_D_OUT", "/tmp/lane-d"))
    ap.add_argument("--out", default=os.environ.get("EFLOUD_LANE_G_OUT", "/tmp/lane-g"))
    ap.add_argument("--state", default=os.environ.get(
        "EFLOUD_LANE_G_STATE", "state/lane_g/lane_g_state.json"))
    ap.add_argument("--date", required=True, help="UTC date YYYY-MM-DD")
    ap.add_argument("--platforms", default=",".join(DEFAULT_PLATFORMS),
                    help="comma list: " + ",".join(sorted(PLATFORM_SPECS)))
    ap.add_argument("--clip-seconds", type=float, default=DEFAULT_CLIP_SECONDS)
    ap.add_argument("--video-backend", default=None, choices=["ffmpeg", "higgsfield"])
    ap.add_argument("--auto-approve", action="store_true",
                    help="mark bundles approved (Lane E can then publish them)")
    args = ap.parse_args(argv)

    platforms = [p.strip() for p in args.platforms.split(",") if p.strip()]
    summary = LaneGOrchestrator(
        copy_dir=args.copy, visual_dir=args.visual, out_dir=args.out,
        state_path=args.state, platforms=platforms,
        clip_seconds=args.clip_seconds, video_backend=args.video_backend,
        auto_approve=args.auto_approve,
    ).run(date=args.date)
    print(json.dumps(summary, ensure_ascii=False))
    return summary


__all__ = [
    "PLATFORM_SPECS", "DEFAULT_PLATFORMS", "PostBundle", "LaneGOrchestrator",
    "build_caption", "load_bundles", "approve_bundle", "main",
]


if __name__ == "__main__":  # pragma: no cover
    main()
