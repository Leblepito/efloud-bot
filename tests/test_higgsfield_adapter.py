"""Tests — Higgsfield MCP adapter (scripts/higgsfield_adapter.py).

Focus is the response-shape parsing that actually broke in production against
the live API, and the credential gate:

  * ``_extract_job_id`` — the submit response nests the job in ``results[]``,
    not a bare ``id`` (first live submit raised "gave no job id").
  * ``_extract_url`` — ``job_status`` answers
    ``{"generation": {"results": {"rawUrl": ...}}}``; a flat ``url`` lookup found
    nothing and the poll loop timed out on an already-completed job. Also asserts
    ``thumbnailUrl`` is never returned (it is the source PNG — returning it would
    "succeed" with a still instead of a video).
  * per-model parameter shaping — ``cinematic_studio_video*`` reject
    ``resolution``/``generate_audio`` with HTTP 422 and want ``sound: "off"``.
  * missing token → ``HiggsfieldUnavailable`` so ``render_clip`` degrades to the
    free offline ffmpeg backend instead of failing a batch.

Offline: the transport is stubbed, no network and no credits are used.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from scripts.higgsfield_adapter import (
    DEFAULT_MODEL,
    HiggsfieldClient,
    HiggsfieldError,
    HiggsfieldUnavailable,
    TOKEN_ENV,
    _extract_job_id,
    _extract_upload,
    _extract_url,
    build_callables,
)

# Verbatim shapes captured from the live API on 2026-07-26.
LIVE_SUBMIT = {
    "results": [{"id": "16331178-5a4e-461c-a522-e03142c508c2", "type": "video",
                 "status": "pending", "model": "cinematic_studio_video_v2"}],
}
LIVE_STATUS_DONE = {
    "generation": {
        "id": "16331178-5a4e-461c-a522-e03142c508c2",
        "type": "video",
        "status": "completed",
        "model": "cinematic_studio_video_v2",
        "results": {
            "rawUrl": "https://cdn.example/hf_20260726_101413_1633.mp4",
            "thumbnailUrl": "https://cdn.example/b80842c9.png",
        },
    }
}
LIVE_STATUS_PENDING = {"generation": {"id": "x", "status": "pending", "results": None}}
LIVE_UPLOAD = {
    "uploads": [{
        "media_id": "b80842c9-0c8a-4cc3-80d7-ad3a5493232a",
        "upload_url": "https://upload.example/user_x/b80842c9.png?X-Amz-Signature=abc",
        "url": "https://cdn.example/user_x/b80842c9.png",
        "content_type": "image/png",
    }]
}


class _StubClient(HiggsfieldClient):
    """HiggsfieldClient with the JSON-RPC transport replaced by a script."""

    def __init__(self, responses: dict):
        self.token = "test-token"
        self.url = "https://mcp.example/mcp"
        self.timeout = 5
        self._initialised = True
        self._id = 0
        self._responses = responses
        self.calls: list[tuple[str, dict]] = []

    def call_tool(self, name: str, arguments: dict) -> dict:
        self.calls.append((name, arguments))
        value = self._responses.get(name, {})
        return value() if callable(value) else value


class TestExtractJobId:
    def test_reads_the_live_nested_results_shape(self):
        assert _extract_job_id(LIVE_SUBMIT) == "16331178-5a4e-461c-a522-e03142c508c2"

    def test_reads_a_flat_id(self):
        assert _extract_job_id({"id": "abc"}) == "abc"
        assert _extract_job_id({"job_id": "def"}) == "def"

    def test_returns_none_when_absent(self):
        assert _extract_job_id({"error": "422"}) is None
        assert _extract_job_id({"results": []}) is None
        assert _extract_job_id("nonsense") is None


class TestExtractUrl:
    def test_reads_the_live_nested_rawurl(self):
        assert _extract_url(LIVE_STATUS_DONE) == "https://cdn.example/hf_20260726_101413_1633.mp4"

    def test_never_returns_the_thumbnail_still(self):
        # Returning thumbnailUrl would hand a PNG to the publisher as if it were
        # the rendered clip — a silent, hard-to-notice failure.
        only_thumb = {"generation": {"status": "completed",
                                     "results": {"thumbnailUrl": "https://cdn.example/x.png"}}}
        assert _extract_url(only_thumb) is None

    def test_pending_job_has_no_url(self):
        assert _extract_url(LIVE_STATUS_PENDING) is None

    def test_tolerates_alternative_shapes(self):
        assert _extract_url({"url": "https://a/x.mp4"}) == "https://a/x.mp4"
        assert _extract_url({"outputs": [{"video_url": "https://b/y.mp4"}]}) == "https://b/y.mp4"

    def test_ignores_non_http_values(self):
        assert _extract_url({"url": "not-a-url"}) is None


class TestExtractUpload:
    def test_reads_the_live_uploads_array(self):
        mid, url = _extract_upload(LIVE_UPLOAD)
        assert mid == "b80842c9-0c8a-4cc3-80d7-ad3a5493232a"
        assert url.startswith("https://upload.example/")

    def test_reads_a_flat_shape(self):
        mid, url = _extract_upload({"media_id": "m1", "upload_url": "https://u/1"})
        assert (mid, url) == ("m1", "https://u/1")

    def test_missing_fields_yield_none(self):
        assert _extract_upload({}) == (None, None)


class TestCredentialGate:
    def test_missing_token_raises_unavailable(self, monkeypatch):
        # HiggsfieldUnavailable (not a generic error) is what makes render_clip
        # fall back to ffmpeg rather than failing the whole batch.
        monkeypatch.delenv(TOKEN_ENV, raising=False)
        with pytest.raises(HiggsfieldUnavailable):
            HiggsfieldClient()

    def test_unavailable_is_a_higgsfield_error(self):
        assert issubclass(HiggsfieldUnavailable, HiggsfieldError)

    def test_token_from_env_is_picked_up(self, monkeypatch):
        monkeypatch.setenv(TOKEN_ENV, "tok-123")
        assert HiggsfieldClient().token == "tok-123"

    def test_build_callables_propagates_unavailable(self, monkeypatch):
        monkeypatch.delenv(TOKEN_ENV, raising=False)
        with pytest.raises(HiggsfieldUnavailable):
            build_callables()


class TestSubmitParameterShaping:
    def test_cinematic_model_omits_rejected_keys(self):
        # resolution / mode / generate_audio on a cinematic_studio model is a 422.
        c = _StubClient({"generate_video": LIVE_SUBMIT})
        c.submit_image_to_video(media_id="m1", prompt="p", model="cinematic_studio_video_v2")
        params = c.calls[0][1]["params"]
        assert params["sound"] == "off"
        assert "resolution" not in params and "generate_audio" not in params

    def test_third_party_model_sends_resolution_and_silent_audio(self):
        c = _StubClient({"generate_video": LIVE_SUBMIT})
        c.submit_image_to_video(media_id="m1", prompt="p", model="seedance_2_0")
        params = c.calls[0][1]["params"]
        assert params["resolution"] and params["generate_audio"] is False
        assert "sound" not in params

    def test_default_model_is_a_working_one(self):
        # The third-party families 422 on this account; the default must not be one.
        assert DEFAULT_MODEL.startswith("cinematic_studio")

    def test_media_is_passed_as_start_image_id(self):
        c = _StubClient({"generate_video": LIVE_SUBMIT})
        c.submit_image_to_video(media_id="m-42", prompt="p")
        assert c.calls[0][1]["params"]["medias"] == [{"role": "start_image", "value": "m-42"}]

    def test_backend_error_response_raises(self):
        c = _StubClient({"generate_video": {"error": "backend request failed (422)"}})
        with pytest.raises(HiggsfieldError):
            c.submit_image_to_video(media_id="m1", prompt="p")


class TestJobStatus:
    def test_completed_job_reports_status_and_url(self):
        c = _StubClient({"job_status": LIVE_STATUS_DONE})
        st = c.job_status("j1")
        assert st["status"] == "completed"
        assert st["url"].endswith(".mp4")

    def test_pending_job_reports_pending_without_url(self):
        c = _StubClient({"job_status": LIVE_STATUS_PENDING})
        st = c.job_status("j1")
        assert st["status"] == "pending" and st["url"] is None

    def test_flat_status_shape_still_works(self):
        c = _StubClient({"job_status": {"status": "failed"}})
        assert c.job_status("j1")["status"] == "failed"


class TestRenderClipIntegration:
    def test_full_triple_drives_render_clip_to_a_file(self, tmp_path):
        from scripts.video_render import render_clip

        still = tmp_path / "chart.png"
        still.write_bytes(b"\x89PNG\r\n\x1a\n")
        out = tmp_path / "clip.mp4"

        c = _StubClient({
            "media_upload": LIVE_UPLOAD,
            "media_confirm": {"results": [{"media_id": "m1", "status": "uploaded"}]},
            "generate_video": LIVE_SUBMIT,
            "job_status": LIVE_STATUS_DONE,
        })
        # Bypass the real HTTP PUT / GET: only the MCP tool calls are stubbed.
        c.upload_image = lambda p: "m1"            # type: ignore[method-assign]
        c.download = lambda url, o: (Path(o).write_bytes(b"mp4"), Path(o))[1]  # type: ignore[method-assign]

        path, backend = render_clip(still, out, backend="higgsfield",
                                    levels={"symbol": "BTC/USDT", "direction": "LONG"},
                                    fmt="vertical", duration=5.0, fallback=False,
                                    poll_interval=0, **_triple_from(c))
        assert backend == "higgsfield" and path.exists()

    def test_failed_job_falls_back_to_ffmpeg(self, tmp_path):
        from scripts.video_render import ffmpeg_available, render_clip

        if not ffmpeg_available():
            pytest.skip("ffmpeg not installed")
        from scripts.chart_render import TradeLevels, render_trade_chart
        import pandas as pd

        idx = pd.date_range("2026-07-20", periods=30, freq="15min")
        candles = pd.DataFrame({"open": 100.0, "high": 101.0, "low": 99.0,
                                "close": 100.5, "volume": 5.0}, index=idx)
        still = render_trade_chart(
            TradeLevels(symbol="B/USDT", timeframe="15m", direction="LONG",
                        entry=100.0, sl=98.0, tp1=104.0),
            tmp_path / "c.png", fmt="vertical", candles=candles)

        c = _StubClient({"generate_video": LIVE_SUBMIT,
                         "job_status": {"generation": {"status": "failed"}}})
        c.upload_image = lambda p: "m1"  # type: ignore[method-assign]

        path, backend = render_clip(still, tmp_path / "o.mp4", backend="higgsfield",
                                    fmt="vertical", duration=1.0, fps=12,
                                    poll_interval=0, **_triple_from(c))
        assert backend == "ffmpeg" and path.exists()


def _triple_from(client) -> dict:
    """build_callables() equivalent for a stub client (skips the token check)."""
    ratio = {"vertical": "9:16", "square": "1:1", "wide": "16:9"}

    def submit(image_path, prompt, fmt, duration):
        mid = client.upload_image(image_path)
        return client.submit_image_to_video(
            media_id=mid, prompt=prompt, aspect_ratio=ratio.get(fmt, "9:16"),
            duration=max(4, min(15, int(round(duration)))))

    return {"submit": submit, "poll": client.job_status,
            "download": lambda url, out: client.download(url, out)}
