"""Lane D-video — annotated chart still → short-form video (Reels/Shorts/X).

Turns the ``scripts/chart_render.py`` PNG into a vertical (or square/landscape)
MP4 suitable for direct upload to Reels / Shorts / X. Two interchangeable
backends behind one ``render_clip`` call:

- **ffmpeg** (default, offline, free) — a deterministic Ken-Burns style push-in
  over the chart still plus a level-reveal wipe, encoded H.264/yuv420p +
  silent AAC track. Needs only the ``ffmpeg`` binary (already on the VPS image
  and the operator box); no API key, no credits, no network. **Pixel-exact:**
  the chart is never reinterpreted, so the published SL/TP prices are always
  the real ones.
- **higgsfield** (opt-in, paid, NOT for signal charts) — sends the still to a
  Higgsfield image-to-video model for a cinematic animated version. Requires a
  live Higgsfield MCP session; the *caller* supplies the submit/poll callables
  so this module stays import-clean and testable (no MCP dependency at import
  time).

  ⚠️ **Measured 2026-07-26 (``cinematic_studio_video_v2``): the generative path
  ALTERS THE DATA.** A 5s clip built from a real signal chart came back with the
  TP1 label rewritten (64,800.0 → 64,400.0), y-axis ticks garbled
  (65,500.0 → "i5.500.0"), candles redrawn and phantom vertical lines added —
  despite a prompt explicitly forbidding any change. Publishing a wrong SL/TP
  price is a compliance/reputational problem, so this backend stays opt-in and
  is only suitable for decorative assets that carry no numbers (intros, brand
  stings). Signal charts use ffmpeg.

Backend choice is explicit (``backend=``) or env-driven
(``EFLOUD_VIDEO_BACKEND``, default ``ffmpeg``). The higgsfield backend degrades
to ffmpeg when it is unavailable or errors, so a batch never dies because a
paid API is down — the post still ships with the offline animation.

Draft-only: writes files, posts nothing, touches no trade state.
"""
from __future__ import annotations

import json
import logging
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Callable, Optional

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

log = logging.getLogger("efloud.video_render")

# Output geometries. vertical = Reels/Shorts/TikTok; square = IG feed; wide = YT/X.
VIDEO_FORMATS: dict[str, tuple[int, int]] = {
    "vertical": (1080, 1920),
    "square": (1080, 1080),
    "wide": (1920, 1080),
}

DEFAULT_DURATION = 8.0
DEFAULT_FPS = 30
BACKEND_ENV = "EFLOUD_VIDEO_BACKEND"


class VideoRenderError(Exception):
    """Clip could not be produced."""


def _ffmpeg_bin() -> Optional[str]:
    return os.environ.get("FFMPEG_BIN") or shutil.which("ffmpeg")


def ffmpeg_available() -> bool:
    return _ffmpeg_bin() is not None


# ── ffmpeg backend ──────────────────────────────────────────────────────────

def _build_filter(w: int, h: int, duration: float, fps: int, *, zoom: float) -> str:
    """Ken-Burns push-in + fade, letterboxed onto the target canvas.

    The still is upscaled first (zoompan works on the *scaled* input, so scaling
    up front keeps the pan smooth instead of stepping between source pixels),
    zoomed slowly to ``zoom``, then padded to the exact output geometry so a
    4:5 chart fits a 9:16 canvas without distortion.

    ``zoom`` must stay gentle: zoompan crops toward the frame centre, so a large
    value eats the outer margins where the y-axis price labels, the footer
    disclaimer and the @u2algo watermark live. 1.04 keeps every edge element on
    screen for the whole clip while still reading as motion; the canvas is
    pre-scaled to ~fit so the initial frame already shows the full chart.
    """
    frames = max(1, int(duration * fps))
    # Fit (not cover) the canvas so the entire chart is visible from frame 1,
    # then pad the letterbox with the brand background before the slow zoom.
    return (
        f"scale={w}:{h}:force_original_aspect_ratio=decrease,"
        f"pad={w}:{h}:(ow-iw)/2:(oh-ih)/2:color=0x050510,"
        f"scale={w * 2}:{h * 2},"
        f"zoompan=z='min(zoom+{(zoom - 1) / frames:.8f},{zoom})'"
        f":d={frames}:x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)'"
        f":s={w}x{h}:fps={fps},"
        f"fade=t=in:st=0:d=0.4,fade=t=out:st={max(0.0, duration - 0.5):.2f}:d=0.5,"
        f"format=yuv420p"
    )


def render_clip_ffmpeg(
    image_path: str | Path,
    out_path: str | Path,
    *,
    fmt: str = "vertical",
    duration: float = DEFAULT_DURATION,
    fps: int = DEFAULT_FPS,
    zoom: float = 1.04,
    audio_path: Optional[str | Path] = None,
    timeout: int = 180,
) -> Path:
    """Animate a chart still into an MP4 with ffmpeg. Returns the written path."""
    binary = _ffmpeg_bin()
    if binary is None:
        raise VideoRenderError("ffmpeg not found (install it or set FFMPEG_BIN)")
    if fmt not in VIDEO_FORMATS:
        raise VideoRenderError(f"unknown format {fmt!r} (have {sorted(VIDEO_FORMATS)})")
    src = Path(image_path)
    if not src.exists():
        raise VideoRenderError(f"chart still not found: {src}")

    w, h = VIDEO_FORMATS[fmt]
    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)

    cmd = [binary, "-y", "-loop", "1", "-i", str(src)]
    if audio_path:
        cmd += ["-i", str(audio_path), "-shortest"]
    else:
        # A silent stereo track: several platforms reject or mis-handle a
        # video-only MP4 (IG Reels in particular), so always ship an audio track.
        cmd += ["-f", "lavfi", "-i", f"anullsrc=channel_layout=stereo:sample_rate=44100"]
    cmd += [
        "-t", f"{duration:.2f}",
        "-vf", _build_filter(w, h, duration, fps, zoom=zoom),
        "-c:v", "libx264", "-preset", "medium", "-crf", "20",
        "-pix_fmt", "yuv420p", "-r", str(fps),
        "-c:a", "aac", "-b:a", "96k",
        "-movflags", "+faststart",
        str(out),
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    if proc.returncode != 0 or not out.exists():
        tail = (proc.stderr or "")[-800:]
        raise VideoRenderError(f"ffmpeg failed (rc={proc.returncode}): {tail}")
    log.info("video_rendered backend=ffmpeg fmt=%s dur=%.1fs path=%s", fmt, duration, out)
    return out


# ── higgsfield backend ──────────────────────────────────────────────────────

# The caller injects these so this module never imports the MCP client:
#   submit(image_path, prompt, fmt, duration) -> job_id
#   poll(job_id) -> {"status": "...", "url": "..."} (terminal when url present)
#   download(url, out_path) -> Path
Submit = Callable[..., str]
Poll = Callable[[str], dict]
Download = Callable[[str, Path], Path]


def build_video_prompt(levels: dict) -> str:
    """Motion prompt for the image-to-video model.

    Deliberately describes *camera* motion only — never new chart content. The
    chart pixels are ground truth (real entry/SL/TP levels); an AI model must not
    invent candles or move the levels, so the prompt asks for a slow cinematic
    push over the existing frame with subtle glow.
    """
    symbol = levels.get("symbol", "the chart")
    direction = str(levels.get("direction") or "").upper()
    bias = "bullish" if direction == "LONG" else "bearish" if direction == "SHORT" else "neutral"
    return (
        f"Slow cinematic push-in over an existing dark trading chart of {symbol}. "
        f"Keep every candle, price line and text label exactly as-is — do not "
        f"redraw, add or move any chart element. Subtle {bias} neon cyan glow "
        f"pulsing along the horizontal price levels, faint scanline shimmer, "
        f"gentle parallax. Premium fintech motion-graphics look, 4k, no text changes."
    )


def render_clip_higgsfield(
    image_path: str | Path,
    out_path: str | Path,
    *,
    levels: Optional[dict] = None,
    fmt: str = "vertical",
    duration: float = 5.0,
    submit: Optional[Submit] = None,
    poll: Optional[Poll] = None,
    download: Optional[Download] = None,
    max_polls: int = 60,
    poll_interval: float = 5.0,
) -> Path:
    """Animate the still through Higgsfield image-to-video.

    ``submit`` / ``poll`` / ``download`` are injected by the caller (the Hermes
    MCP tools, or a test fake). Raises ``VideoRenderError`` when they are missing
    so ``render_clip`` can fall back to ffmpeg.
    """
    import time

    if submit is None or poll is None or download is None:
        raise VideoRenderError(
            "higgsfield backend needs submit/poll/download callables "
            "(no live MCP session wired)"
        )
    src = Path(image_path)
    if not src.exists():
        raise VideoRenderError(f"chart still not found: {src}")

    prompt = build_video_prompt(levels or {})
    job_id = submit(image_path=str(src), prompt=prompt, fmt=fmt, duration=duration)
    log.info("higgsfield_submitted job=%s fmt=%s", job_id, fmt)

    url = None
    for _ in range(max_polls):
        res = poll(job_id) or {}
        status = str(res.get("status") or "").lower()
        if res.get("url"):
            url = res["url"]
            break
        if status in ("failed", "error", "nsfw", "canceled", "cancelled"):
            raise VideoRenderError(f"higgsfield job {job_id} ended status={status}")
        time.sleep(poll_interval)
    if not url:
        raise VideoRenderError(f"higgsfield job {job_id} did not finish in time")

    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    download(url, out)
    if not out.exists():
        raise VideoRenderError(f"higgsfield download produced no file: {out}")
    log.info("video_rendered backend=higgsfield job=%s path=%s", job_id, out)
    return out


# ── dispatcher ──────────────────────────────────────────────────────────────

def render_clip(
    image_path: str | Path,
    out_path: str | Path,
    *,
    backend: Optional[str] = None,
    levels: Optional[dict] = None,
    fmt: str = "vertical",
    duration: float = DEFAULT_DURATION,
    fallback: bool = True,
    **kwargs,
) -> tuple[Path, str]:
    """Render a clip with the chosen backend. Returns ``(path, backend_used)``.

    ``backend`` defaults to ``$EFLOUD_VIDEO_BACKEND`` then ``"ffmpeg"``. With
    ``fallback=True`` (default) a failing higgsfield render degrades to ffmpeg
    rather than failing the batch.
    """
    chosen = (backend or os.environ.get(BACKEND_ENV) or "ffmpeg").strip().lower()
    if chosen not in ("ffmpeg", "higgsfield"):
        raise VideoRenderError(f"unknown backend {chosen!r} (ffmpeg|higgsfield)")

    if chosen == "higgsfield":
        # ⚠️ DATA-INTEGRITY WARNING (measured 2026-07-26, cinematic_studio_video_v2).
        # Generative image-to-video does NOT preserve the chart: in a 5s clip made
        # from a real signal chart the model silently rewrote the TP1 price label
        # (64,800.0 → 64,400.0), garbled the y-axis ticks (65,500.0 → "i5.500.0"),
        # redrew candles that never existed and added phantom vertical lines.
        # Publishing a wrong SL/TP price is a compliance and reputational problem,
        # so this backend must NOT be the default for signal charts — the prompt
        # asking the model to "keep every label exactly as-is" is not honoured and
        # cannot be relied on. Keep it opt-in, for decorative/non-numeric assets
        # (intros, brand stings) only.
        log.warning(
            "higgsfield backend selected — generative video is known to alter "
            "chart numbers/labels; do not use it for signal charts"
        )
        hf_kwargs = {k: v for k, v in kwargs.items()
                     if k in ("submit", "poll", "download", "max_polls", "poll_interval")}
        try:
            p = render_clip_higgsfield(image_path, out_path, levels=levels, fmt=fmt,
                                       duration=min(duration, 10.0), **hf_kwargs)
            return p, "higgsfield"
        except Exception as e:
            if not fallback:
                raise
            log.warning("higgsfield_backend_failed err=%s → falling back to ffmpeg", e)

    ff_kwargs = {k: v for k, v in kwargs.items()
                 if k in ("fps", "zoom", "audio_path", "timeout")}
    p = render_clip_ffmpeg(image_path, out_path, fmt=fmt, duration=duration, **ff_kwargs)
    return p, "ffmpeg"


def probe(path: str | Path) -> dict:
    """ffprobe summary of a rendered clip (duration/size/codec) — verification."""
    binary = os.environ.get("FFPROBE_BIN") or shutil.which("ffprobe")
    if binary is None:
        return {}
    cmd = [binary, "-v", "quiet", "-print_format", "json",
           "-show_format", "-show_streams", str(path)]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        data = json.loads(proc.stdout or "{}")
    except (subprocess.SubprocessError, json.JSONDecodeError, OSError):
        return {}
    v = next((s for s in data.get("streams", []) if s.get("codec_type") == "video"), {})
    a = next((s for s in data.get("streams", []) if s.get("codec_type") == "audio"), {})
    fmt = data.get("format", {})
    return {
        "duration": float(fmt.get("duration", 0) or 0),
        "size_bytes": int(fmt.get("size", 0) or 0),
        "width": v.get("width"),
        "height": v.get("height"),
        "video_codec": v.get("codec_name"),
        "audio_codec": a.get("codec_name"),
    }


def main(argv: Optional[list[str]] = None) -> int:
    """CLI: chart still → MP4 (manual/QA use)."""
    import argparse

    ap = argparse.ArgumentParser(description="Chart still → short-form video clip")
    ap.add_argument("--image", required=True, help="chart PNG from scripts.chart_render")
    ap.add_argument("--out", required=True, help="output MP4 path")
    ap.add_argument("--format", default="vertical", choices=sorted(VIDEO_FORMATS))
    ap.add_argument("--duration", type=float, default=DEFAULT_DURATION)
    ap.add_argument("--fps", type=int, default=DEFAULT_FPS)
    ap.add_argument("--backend", default=None, choices=["ffmpeg", "higgsfield"])
    ap.add_argument("--audio", default=None, help="optional audio track")
    args = ap.parse_args(argv)

    path, used = render_clip(
        args.image, args.out, backend=args.backend, fmt=args.format,
        duration=args.duration, fps=args.fps, audio_path=args.audio,
    )
    info = probe(path)
    print(json.dumps({"path": str(path), "backend": used, **info}, ensure_ascii=False))
    return 0


__all__ = [
    "VIDEO_FORMATS", "VideoRenderError", "ffmpeg_available", "build_video_prompt",
    "render_clip", "render_clip_ffmpeg", "render_clip_higgsfield", "probe", "main",
]


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
