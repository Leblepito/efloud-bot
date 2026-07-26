"""Higgsfield MCP adapter — the live submit/poll/download triple for video_render.

``scripts/video_render.py`` keeps its Higgsfield backend behind three injected
callables so the module stays import-clean and testable. This is the *real*
implementation of that triple, talking JSON-RPC to the Higgsfield MCP endpoint
over HTTPS (the same server the Hermes MCP client uses).

Why a standalone HTTP client rather than reusing an MCP session: cron ticks and
the VPS bot process have no Hermes MCP session — they need a plain bearer token
from the environment. One dependency (``requests``, already in the project) and
no MCP handshake bookkeeping beyond ``initialize``.

Credentials: ``HIGGSFIELD_MCP_TOKEN`` (bearer) and optional
``HIGGSFIELD_MCP_URL``. Absent token → ``HiggsfieldUnavailable``, which
``render_clip`` treats as "fall back to ffmpeg", so an unconfigured deploy
degrades to the free offline path instead of failing.

Cost note: image-to-video is a *paid* generation. The default model/params here
are the cheap tier (``mode='fast'``, 720p, 5s, no generated audio) because these
clips are chart animations, not cinematic shots — and the chart pixels must not
be reinterpreted anyway.
"""
from __future__ import annotations

import json
import logging
import os
import re
import time
from pathlib import Path
from typing import Any, Optional

log = logging.getLogger("efloud.higgsfield")

DEFAULT_URL = "https://mcp.higgsfield.ai/mcp"
TOKEN_ENV = "HIGGSFIELD_MCP_TOKEN"
URL_ENV = "HIGGSFIELD_MCP_URL"

# Model choice (verified 2026-07-26 against a live `plus` account):
#
# Third-party video backends — kling3_0_turbo, kling2_6, seedance_2_0,
# seedance1_5 — all return HTTP 422 on this account, even for a `get_cost`
# preflight with no media attached. It is an upstream/account entitlement issue,
# not a parameter problem (a text-only request fails identically).
# Higgsfield's OWN models price and submit fine, so default to one of those:
#   cinematic_studio_video_v2 →  7 credits / 5s  ← default (cheap, silent-able)
#   cinematic_studio_3_0      → 75 credits / 15s   (premium, overkill for charts)
# If the third-party models are re-enabled on the account later, they can be
# selected with DEFAULT_MODEL / the `model=` argument without other changes.
DEFAULT_MODEL = "cinematic_studio_video_v2"
DEFAULT_RESOLUTION = "720p"
DEFAULT_MODE = "std"

_SSE_DATA = re.compile(r"^data: (.+)$", re.M)


class HiggsfieldError(Exception):
    """Higgsfield call failed."""


class HiggsfieldUnavailable(HiggsfieldError):
    """No token / no endpoint — caller should fall back to the offline backend."""


class HiggsfieldClient:
    """Minimal JSON-RPC client for the Higgsfield MCP tool surface."""

    def __init__(self, token: Optional[str] = None, url: Optional[str] = None,
                 timeout: int = 120):
        self.token = token or os.environ.get(TOKEN_ENV, "").strip()
        self.url = url or os.environ.get(URL_ENV, "").strip() or DEFAULT_URL
        self.timeout = timeout
        self._initialised = False
        self._id = 0
        if not self.token:
            raise HiggsfieldUnavailable(
                f"no Higgsfield token (set ${TOKEN_ENV}) — offline backend will be used"
            )

    # ── transport ───────────────────────────────────────────────────────────
    def _rpc(self, method: str, params: Optional[dict] = None) -> dict:
        import requests

        self._id += 1
        body: dict[str, Any] = {"jsonrpc": "2.0", "id": self._id, "method": method}
        if params is not None:
            body["params"] = params
        try:
            resp = requests.post(
                self.url, json=body, timeout=self.timeout,
                headers={
                    "Authorization": f"Bearer {self.token}",
                    "Content-Type": "application/json",
                    # The server answers JSON-RPC over SSE framing.
                    "Accept": "application/json, text/event-stream",
                },
            )
        except Exception as e:
            raise HiggsfieldError(f"transport error: {e}") from e

        if resp.status_code in (401, 403):
            raise HiggsfieldUnavailable(
                f"Higgsfield auth rejected (HTTP {resp.status_code}) — token expired?"
            )
        if resp.status_code >= 400:
            raise HiggsfieldError(f"HTTP {resp.status_code}: {resp.text[:300]}")

        payload = self._parse(resp.text)
        if "error" in payload:
            raise HiggsfieldError(f"rpc error: {payload['error']}")
        return payload.get("result", {})

    @staticmethod
    def _parse(text: str) -> dict:
        """Unwrap an SSE-framed JSON-RPC response (falls back to plain JSON)."""
        m = _SSE_DATA.search(text or "")
        raw = m.group(1) if m else (text or "")
        try:
            return json.loads(raw)
        except json.JSONDecodeError as e:
            raise HiggsfieldError(f"unparseable response: {raw[:200]}") from e

    def _ensure_init(self) -> None:
        if self._initialised:
            return
        self._rpc("initialize", {
            "protocolVersion": "2024-11-05", "capabilities": {},
            "clientInfo": {"name": "efloud-bot", "version": "1.0"},
        })
        self._initialised = True

    def call_tool(self, name: str, arguments: dict) -> dict:
        """Invoke an MCP tool; returns its ``structuredContent`` when present."""
        self._ensure_init()
        result = self._rpc("tools/call", {"name": name, "arguments": arguments})
        structured = result.get("structuredContent")
        if isinstance(structured, dict):
            return structured
        # Some tools answer only as text content — surface it uniformly.
        content = result.get("content") or []
        text = content[0].get("text") if content and isinstance(content[0], dict) else None
        return {"text": text} if text else {}

    # ── high-level helpers ──────────────────────────────────────────────────
    def balance(self) -> dict:
        return self.call_tool("balance", {})

    def upload_image(self, path: str | Path) -> str:
        """Upload a local PNG and return its confirmed ``media_id``.

        Three steps mandated by the MCP media contract: reserve a presigned URL,
        PUT the bytes, confirm. The confirmed id (not a URL) is what generation
        calls accept in ``medias[].value``.
        """
        import requests

        p = Path(path)
        if not p.exists():
            raise HiggsfieldError(f"image not found: {p}")

        reserved = self.call_tool("media_upload", {
            "filename": p.name, "content_type": "image/png", "method": "upload_url",
        })
        media_id, upload_url = _extract_upload(reserved)
        if not media_id or not upload_url:
            raise HiggsfieldError(f"media_upload gave no id/url: {str(reserved)[:300]}")

        try:
            r = requests.put(upload_url, data=p.read_bytes(),
                             headers={"Content-Type": "image/png"}, timeout=self.timeout)
        except Exception as e:
            raise HiggsfieldError(f"upload PUT failed: {e}") from e
        if r.status_code >= 400:
            raise HiggsfieldError(f"upload PUT HTTP {r.status_code}: {r.text[:200]}")

        self.call_tool("media_confirm", {"media_id": media_id, "type": "image"})
        log.info("higgsfield_uploaded media_id=%s file=%s", media_id, p.name)
        return media_id

    def submit_image_to_video(
        self, *, media_id: str, prompt: str, aspect_ratio: str = "9:16",
        duration: int = 5, model: str = DEFAULT_MODEL,
        resolution: str = DEFAULT_RESOLUTION, mode: str = DEFAULT_MODE,
    ) -> str:
        """Queue an image-to-video job; returns the job id.

        Parameter shape differs per model family, so only the keys the selected
        model actually declares are sent — an unknown key is a 422 on this API:
          * ``cinematic_studio_video*`` take ``sound`` as the string "on"/"off"
            and do NOT accept ``resolution`` / ``generate_audio``;
          * the third-party families (seedance/kling) take ``resolution``,
            ``mode`` and a boolean ``generate_audio``.
        Silent output either way: the caption carries the message, platforms lay
        their own audio over Reels/Shorts, and generated audio costs extra.
        """
        params: dict[str, Any] = {
            "model": model,
            "prompt": prompt,
            "aspect_ratio": aspect_ratio,
            "duration": int(duration),
            "medias": [{"role": "start_image", "value": media_id}],
        }
        if model.startswith("cinematic_studio"):
            params["sound"] = "off"
        else:
            params["resolution"] = resolution
            params["mode"] = mode
            params["generate_audio"] = False

        res = self.call_tool("generate_video", {"params": params})
        job_id = _extract_job_id(res)
        if not job_id:
            raise HiggsfieldError(f"generate_video gave no job id: {str(res)[:300]}")
        return str(job_id)

    def job_status(self, job_id: str) -> dict:
        """Normalised ``{"status": ..., "url": ...}`` for one job.

        The payload nests everything under ``generation``, so read the status
        from there when present — reading the top level returns "" and the poll
        loop would spin until timeout on an already-finished job.
        """
        res = self.call_tool("job_status", {"jobId": job_id})
        gen = res.get("generation") if isinstance(res.get("generation"), dict) else res
        return {"status": str(gen.get("status") or res.get("status") or "").lower(),
                "url": _extract_url(res),
                "raw": res}

    def download(self, url: str, out_path: str | Path) -> Path:
        import requests

        out = Path(out_path)
        out.parent.mkdir(parents=True, exist_ok=True)
        try:
            r = requests.get(url, timeout=self.timeout, stream=True)
            r.raise_for_status()
            with open(out, "wb") as f:
                for chunk in r.iter_content(chunk_size=1 << 16):
                    if chunk:
                        f.write(chunk)
        except Exception as e:
            raise HiggsfieldError(f"download failed: {e}") from e
        return out


def _extract_job_id(payload: Any) -> Optional[str]:
    """Pull the job id out of a generate_video response.

    The submit response nests the job under ``results[]`` (``{"results":
    [{"id": ..., "status": "pending"}]}``) rather than returning a bare ``id``,
    so check both shapes.
    """
    if not isinstance(payload, dict):
        return None
    for key in ("id", "job_id"):
        v = payload.get(key)
        if isinstance(v, (str, int)):
            return str(v)
    results = payload.get("results")
    if isinstance(results, list) and results and isinstance(results[0], dict):
        v = results[0].get("id") or results[0].get("job_id")
        if v:
            return str(v)
    return None


def _extract_upload(payload: dict) -> tuple[Optional[str], Optional[str]]:
    """Pull (media_id, upload_url) out of a media_upload response.

    The response shape varies (single vs batch); walk it defensively rather than
    hardcoding one nesting.
    """
    if not isinstance(payload, dict):
        return None, None
    mid = payload.get("media_id") or payload.get("id")
    url = payload.get("upload_url") or payload.get("url")
    if mid and url:
        return str(mid), str(url)
    for key in ("files", "uploads", "items", "medias"):
        seq = payload.get(key)
        if isinstance(seq, list) and seq and isinstance(seq[0], dict):
            first = seq[0]
            mid = mid or first.get("media_id") or first.get("id")
            url = url or first.get("upload_url") or first.get("url")
            if mid and url:
                return str(mid), str(url)
    return (str(mid) if mid else None), (str(url) if url else None)


def _extract_url(payload: Any) -> Optional[str]:
    """Find the first video/media URL in a job payload (shape-tolerant).

    Real shape from ``job_status`` is nested and camelCase::

        {"generation": {"status": "completed",
                        "results": {"rawUrl": "https://...mp4",
                                    "thumbnailUrl": "https://...png"}}}

    so ``rawUrl`` must be checked (and preferred over ``thumbnailUrl``, which is
    the *source still* — returning it would silently "succeed" with a PNG).
    """
    if isinstance(payload, str):
        return payload if payload.startswith("http") else None
    if isinstance(payload, dict):
        # Ordered by specificity; thumbnailUrl is deliberately NOT included.
        for key in ("rawUrl", "raw_url", "url", "result_url", "resultUrl",
                    "video_url", "videoUrl", "output_url", "outputUrl"):
            v = payload.get(key)
            if isinstance(v, str) and v.startswith("http"):
                return v
        for key in ("generation", "results", "result", "outputs", "assets", "media"):
            found = _extract_url(payload.get(key))
            if found:
                return found
    if isinstance(payload, list):
        for item in payload:
            found = _extract_url(item)
            if found:
                return found
    return None


# ── video_render integration ────────────────────────────────────────────────

def build_callables(client: Optional[HiggsfieldClient] = None) -> dict:
    """Return the ``submit`` / ``poll`` / ``download`` triple for render_clip.

    Usage::

        from scripts.higgsfield_adapter import build_callables
        from scripts.video_render import render_clip
        render_clip(still, out, backend="higgsfield", levels=levels,
                    **build_callables())

    Raises ``HiggsfieldUnavailable`` when no token is configured; callers that
    want automatic degradation should catch it and omit the kwargs so
    ``render_clip`` uses ffmpeg.
    """
    c = client or HiggsfieldClient()

    _ratio = {"vertical": "9:16", "square": "1:1", "wide": "16:9"}

    def submit(image_path: str, prompt: str, fmt: str, duration: float) -> str:
        media_id = c.upload_image(image_path)
        return c.submit_image_to_video(
            media_id=media_id, prompt=prompt,
            aspect_ratio=_ratio.get(fmt, "9:16"),
            duration=max(4, min(15, int(round(duration)))),
        )

    def poll(job_id: str) -> dict:
        return c.job_status(job_id)

    def download(url: str, out_path: Path) -> Path:
        return c.download(url, out_path)

    return {"submit": submit, "poll": poll, "download": download}


def main(argv: Optional[list[str]] = None) -> int:
    """CLI: smoke-test the adapter (balance, or a real clip with --image)."""
    import argparse

    ap = argparse.ArgumentParser(description="Higgsfield adapter smoke test")
    ap.add_argument("--image", default=None, help="chart PNG to animate (paid)")
    ap.add_argument("--out", default=None, help="output MP4 path")
    ap.add_argument("--format", default="vertical", choices=["vertical", "square", "wide"])
    ap.add_argument("--duration", type=float, default=5.0)
    args = ap.parse_args(argv)

    try:
        client = HiggsfieldClient()
    except HiggsfieldUnavailable as e:
        print(json.dumps({"available": False, "reason": str(e)}))
        return 1

    bal = client.balance()
    if not args.image:
        print(json.dumps({"available": True, "balance": bal}, ensure_ascii=False))
        return 0

    if not args.out:
        print(json.dumps({"error": "--out required with --image"}))
        return 2

    from scripts.video_render import render_clip

    started = time.time()
    path, backend = render_clip(
        args.image, args.out, backend="higgsfield", fmt=args.format,
        duration=args.duration, fallback=False, **build_callables(client),
    )
    print(json.dumps({"path": str(path), "backend": backend,
                      "seconds": round(time.time() - started, 1),
                      "balance_before": bal}, ensure_ascii=False))
    return 0


__all__ = [
    "HiggsfieldClient", "HiggsfieldError", "HiggsfieldUnavailable",
    "build_callables", "main",
]


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
