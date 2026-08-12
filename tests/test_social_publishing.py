"""Tests — chart_render + video_render + Lane G social orchestrator.

Covers the new social-publishing chain added on top of Lane B→E:
  chart_render   annotated entry/SL/TP chart PNG (offline, cache-backed)
  video_render   still → short-form MP4 (ffmpeg backend + higgsfield fallback)
  lane_g_social  per-platform bundle packaging, compliance gate, idempotency

Every test is offline and deterministic: candles are synthesised in-memory (no
parquet cache, no Binance), and the higgsfield path is exercised with injected
fakes so no MCP session or credits are needed. The ffmpeg-dependent tests skip
cleanly where the binary is absent (CI containers without ffmpeg).
"""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pandas as pd
import pytest

from engine.content_jobs import COMPLIANCE_TR
from scripts.chart_render import (
    CHART_FORMATS,
    ChartRenderError,
    TradeLevels,
    chart_renderer,
    render_trade_chart,
)
from scripts.lane_g_social import (
    PLATFORM_SPECS,
    LaneGOrchestrator,
    PostBundle,
    approve_bundle,
    build_caption,
    load_bundles,
)
from scripts.video_render import (
    VideoRenderError,
    build_video_prompt,
    ffmpeg_available,
    probe,
    render_clip,
    render_clip_higgsfield,
)

DATE = "2026-07-26"


def _candles(n: int = 60, start: float = 100.0) -> pd.DataFrame:
    """Deterministic synthetic OHLCV — no network, no cache."""
    idx = pd.date_range("2026-07-20", periods=n, freq="15min")
    rows = []
    price = start
    for i in range(n):
        o = price
        c = price + (1.5 if i % 3 else -1.0)
        rows.append({"open": o, "high": max(o, c) + 0.8, "low": min(o, c) - 0.8,
                     "close": c, "volume": 10.0 + i})
        price = c
    return pd.DataFrame(rows, index=idx)


def _levels(**kw) -> TradeLevels:
    base = dict(symbol="BTC/USDT", timeframe="15m", direction="LONG",
                entry=100.0, sl=97.0, tp1=106.0, tp2=110.0, confluence=75)
    base.update(kw)
    return TradeLevels(**base)


def _copy_draft(event_id: str = "ev-1", **overrides) -> dict:
    draft = {
        "event_id": event_id,
        "symbol": "BTC/USDT",
        "timeframe": "15m",
        "lang": "tr",
        "caption": (
            "BTC/USDT · 15m · LONG\nHTF yapı korunuyor.\n"
            f"Risk ~2.0% · R:R 1:2.0 (TP1)\n\n{COMPLIANCE_TR}"
        ),
        "thread": ["BTC/USDT 15m LONG — yapı: BOS.", "Risk yönetimi: Risk ~2.0%.",
                   COMPLIANCE_TR],
        "alt_text": "BTC/USDT 15m grafiği — LONG setup",
        "levels": {"symbol": "BTC/USDT", "timeframe": "15m", "direction": "LONG",
                   "entry": 100.0, "sl": 97.0, "tp1": 106.0, "tp2": 110.0,
                   "confluence": 75},
    }
    draft.update(overrides)
    return draft


# ── chart_render ────────────────────────────────────────────────────────────

class TestTradeLevels:
    def test_rr_and_risk_pct_from_levels(self):
        lv = _levels(entry=100.0, sl=98.0, tp1=104.0)
        assert lv.rr_tp1 == pytest.approx(2.0)
        assert lv.risk_pct == pytest.approx(2.0)

    def test_zero_risk_yields_none_instead_of_dividing(self):
        assert _levels(entry=100.0, sl=100.0).rr_tp1 is None

    def test_from_signal_maps_lane_a_shape(self):
        lv = TradeLevels.from_signal({
            "symbol": "ETH/USDT", "timeframe": "1h", "direction": "short",
            "entry": "1850.5", "sl": "1880", "tp1": "1800", "tp2": None,
            "confluence": "71",
        })
        assert (lv.symbol, lv.direction, lv.tp2, lv.confluence) == ("ETH/USDT", "SHORT", None, 71)

    def test_from_signal_rejects_missing_levels(self):
        with pytest.raises(ChartRenderError):
            TradeLevels.from_signal({"symbol": "BTC/USDT", "entry": 100.0})

    def test_from_signal_treats_zero_tp2_as_absent(self):
        # Legacy rows carried tp2=0.0 for single-target setups; a 0-price line
        # would be drawn at the bottom of the chart and look like a real level.
        assert TradeLevels.from_signal(
            {"symbol": "B/USDT", "entry": 1, "sl": 2, "tp1": 3, "tp2": 0.0}
        ).tp2 is None


@pytest.mark.skipif(
    importlib.util.find_spec("matplotlib") is None,
    reason="matplotlib kurulu değil — chart render opsiyonel bağımlılık "
           "(requirements.txt'te yok; sosyal pipeline'ı çalıştıran ortamlar kurar)",
)
class TestRenderTradeChart:
    def test_renders_both_formats_as_real_pngs(self, tmp_path):
        candles = _candles()
        for fmt in CHART_FORMATS:
            out = render_trade_chart(_levels(), tmp_path / f"c.{fmt}.png",
                                     fmt=fmt, candles=candles)
            assert out.exists() and out.stat().st_size > 5000
            assert out.read_bytes()[:8] == b"\x89PNG\r\n\x1a\n"

    def test_rejects_unknown_format(self, tmp_path):
        with pytest.raises(ChartRenderError):
            render_trade_chart(_levels(), tmp_path / "x.png", fmt="tiktok",
                               candles=_candles())

    def test_rejects_empty_candles(self, tmp_path):
        with pytest.raises(ChartRenderError):
            render_trade_chart(_levels(), tmp_path / "x.png",
                               candles=pd.DataFrame(columns=["open", "high", "low", "close"]))

    def test_single_target_setup_renders(self, tmp_path):
        out = render_trade_chart(_levels(tp2=None), tmp_path / "s.png", candles=_candles())
        assert out.exists()

    def test_short_setup_renders(self, tmp_path):
        out = render_trade_chart(
            _levels(direction="SHORT", entry=100.0, sl=103.0, tp1=94.0, tp2=90.0),
            tmp_path / "sh.png", candles=_candles())
        assert out.exists()

    def test_levels_outside_candle_range_still_render(self, tmp_path, caplog):
        # A stale cache must not crash the batch — it warns and still draws.
        with caplog.at_level("WARNING"):
            out = render_trade_chart(_levels(entry=5000.0, sl=4900.0, tp1=5200.0, tp2=None),
                                     tmp_path / "far.png", candles=_candles())
        assert out.exists()
        assert any("chart_levels_far_from_price" in r.message for r in caplog.records)


class TestChartRendererAdapter:
    """chart_renderer is the Lane D ``Renderer`` seam."""

    def test_no_levels_falls_back_to_manifest(self, tmp_path):
        out = chart_renderer({"event_id": "e", "overlay": {}}, "still", tmp_path / "b")
        assert out.suffix == ".json"

    def test_unrenderable_levels_fall_back_to_manifest(self, tmp_path):
        # Missing candle cache (bogus cache_dir, fetch disabled) → manifest,
        # never an exception that would abort the whole Lane D batch.
        spec = {"event_id": "e", "overlay": {}, "levels": _copy_draft()["levels"],
                "cache_dir": str(tmp_path / "nope")}
        out = chart_renderer(spec, "still", tmp_path / "b")
        assert out.suffix == ".json"


# ── video_render ────────────────────────────────────────────────────────────

class TestVideoPrompt:
    def test_prompt_forbids_redrawing_the_chart(self):
        p = build_video_prompt({"symbol": "BTC/USDT", "direction": "LONG"})
        assert "do not" in p.lower() and "bullish" in p
        assert "BTC/USDT" in p

    def test_short_direction_reads_bearish(self):
        assert "bearish" in build_video_prompt({"direction": "SHORT"})


class TestHiggsfieldBackend:
    def test_missing_callables_raise_so_dispatcher_can_fall_back(self, tmp_path):
        img = tmp_path / "c.png"
        img.write_bytes(b"\x89PNG\r\n\x1a\n")
        with pytest.raises(VideoRenderError):
            render_clip_higgsfield(img, tmp_path / "o.mp4")

    def test_happy_path_with_injected_fakes(self, tmp_path):
        img = tmp_path / "c.png"
        img.write_bytes(b"\x89PNG\r\n\x1a\n")
        calls = {}

        def submit(image_path, prompt, fmt, duration):
            calls["prompt"] = prompt
            return "job-1"

        def poll(job_id):
            return {"status": "completed", "url": "https://cdn/x.mp4"}

        def download(url, out):
            Path(out).write_bytes(b"fake-mp4")
            return Path(out)

        out = render_clip_higgsfield(img, tmp_path / "o.mp4", levels={"symbol": "BTC/USDT"},
                                     submit=submit, poll=poll, download=download,
                                     poll_interval=0)
        assert out.exists() and "BTC/USDT" in calls["prompt"]

    def test_failed_job_raises(self, tmp_path):
        img = tmp_path / "c.png"
        img.write_bytes(b"\x89PNG\r\n\x1a\n")
        with pytest.raises(VideoRenderError):
            render_clip_higgsfield(
                img, tmp_path / "o.mp4",
                submit=lambda **kw: "j", poll=lambda j: {"status": "failed"},
                download=lambda u, o: Path(o), poll_interval=0)

    def test_dispatcher_falls_back_to_ffmpeg_when_higgsfield_unavailable(self, tmp_path):
        if not ffmpeg_available():
            pytest.skip("ffmpeg not installed")
        still = render_trade_chart(_levels(), tmp_path / "c.png", fmt="vertical",
                                   candles=_candles())
        path, backend = render_clip(still, tmp_path / "o.mp4", backend="higgsfield",
                                    duration=1.0, fps=12)
        assert backend == "ffmpeg" and path.exists()


@pytest.mark.skipif(not ffmpeg_available(), reason="ffmpeg not installed")
class TestFfmpegBackend:
    def test_renders_playable_mp4_with_expected_geometry(self, tmp_path):
        still = render_trade_chart(_levels(), tmp_path / "c.png", fmt="vertical",
                                   candles=_candles())
        out, backend = render_clip(still, tmp_path / "clip.mp4", backend="ffmpeg",
                                   fmt="vertical", duration=2.0, fps=15)
        assert backend == "ffmpeg" and out.exists()
        info = probe(out)
        if info:  # ffprobe present
            assert (info["width"], info["height"]) == (1080, 1920)
            assert info["video_codec"] == "h264"
            # A silent audio track is mandatory: IG Reels rejects video-only MP4s.
            assert info["audio_codec"] == "aac"
            assert info["duration"] == pytest.approx(2.0, abs=0.4)

    def test_missing_still_raises(self, tmp_path):
        with pytest.raises(VideoRenderError):
            render_clip(tmp_path / "nope.png", tmp_path / "o.mp4", backend="ffmpeg")

    def test_unknown_backend_rejected(self, tmp_path):
        with pytest.raises(VideoRenderError):
            render_clip(tmp_path / "a.png", tmp_path / "o.mp4", backend="sora")


# ── Lane G ──────────────────────────────────────────────────────────────────

class TestBuildCaption:
    def test_x_caption_fits_280_and_keeps_disclaimer(self):
        cap = build_caption(_copy_draft(), "x")
        assert len(cap) <= PLATFORM_SPECS["x"]["limit"]
        assert COMPLIANCE_TR in cap

    def test_long_body_is_trimmed_but_disclaimer_survives(self):
        draft = _copy_draft(caption="x" * 5000 + f"\n\n{COMPLIANCE_TR}")
        cap = build_caption(draft, "x")
        assert len(cap) <= 280
        assert cap.endswith(COMPLIANCE_TR)

    def test_instagram_caption_expands_thread_into_bullets(self):
        cap = build_caption(_copy_draft(), "instagram")
        assert "•" in cap and COMPLIANCE_TR in cap

    def test_disclaimer_added_when_copy_lacks_it(self):
        cap = build_caption(_copy_draft(caption="BTC LONG", thread=[]), "x")
        assert COMPLIANCE_TR in cap


class TestPostBundle:
    def test_draft_id_is_event_platform_pair(self):
        b = PostBundle(event_id="e1", platform="x", symbol="BTC/USDT", caption="c")
        assert b.draft_id == "e1:x"

    def test_payload_shape_matches_lane_e_envelope(self):
        d = PostBundle(event_id="e1", platform="x", symbol="B", caption="c",
                       media=["/tmp/a.png"]).to_dict()
        assert d["payload"]["caption"] == "c" and d["payload"]["media"] == ["/tmp/a.png"]


class _LaneGFixture:
    """Builds a Lane C copy dir + Lane D visual dir on disk."""

    def __init__(self, tmp_path: Path, *, events=("ev-1",), formats=("still", "vertical")):
        self.root = tmp_path
        self.copy_dir = tmp_path / "copy"
        self.visual_dir = tmp_path / "visual"
        self.out_dir = tmp_path / "laneg"
        self.state = tmp_path / "state.json"
        (self.copy_dir / DATE).mkdir(parents=True)
        (self.visual_dir / DATE).mkdir(parents=True)
        for ev in events:
            (self.copy_dir / DATE / f"{ev}.json").write_text(
                json.dumps(_copy_draft(ev), ensure_ascii=False), encoding="utf-8")
            for fmt in formats:
                (self.visual_dir / DATE / f"{ev}.{fmt}.png").write_bytes(b"\x89PNG\r\n\x1a\n")

    def orchestrator(self, **kw) -> LaneGOrchestrator:
        defaults = dict(
            copy_dir=self.copy_dir, visual_dir=self.visual_dir, out_dir=self.out_dir,
            state_path=self.state, platforms=["x", "instagram", "ig_reels", "youtube"],
            # Fake clip renderer: no ffmpeg dependency in the orchestration tests.
            clip_renderer=lambda still, out, **k: (self._fake_clip(out), "fake"),
        )
        defaults.update(kw)
        return LaneGOrchestrator(**defaults)

    @staticmethod
    def _fake_clip(out) -> Path:
        p = Path(out)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(b"fake-mp4")
        return p


class TestLaneGOrchestrator:
    def test_packages_one_bundle_per_platform(self, tmp_path):
        fx = _LaneGFixture(tmp_path)
        s = fx.orchestrator().run(DATE)
        assert s["packaged"] == 4
        assert s["clips_rendered"] == 2      # ig_reels + youtube
        assert s["blocked_compliance"] == 0
        assert len(load_bundles(fx.out_dir, DATE)) == 4

    def test_default_state_is_pending_review_not_approved(self, tmp_path):
        # Safety posture: nothing is publishable until a human approves.
        fx = _LaneGFixture(tmp_path)
        fx.orchestrator().run(DATE)
        assert all(b["state"] == "pending_review" for b in load_bundles(fx.out_dir, DATE))
        assert load_bundles(fx.out_dir, DATE, state="approved") == []

    def test_auto_approve_marks_bundles_approved(self, tmp_path):
        fx = _LaneGFixture(tmp_path)
        fx.orchestrator(auto_approve=True).run(DATE)
        assert len(load_bundles(fx.out_dir, DATE, state="approved")) == 4

    def test_rerun_is_idempotent(self, tmp_path):
        fx = _LaneGFixture(tmp_path)
        fx.orchestrator().run(DATE)
        second = fx.orchestrator().run(DATE)
        assert second["packaged"] == 0
        assert second["skipped_already_done"] == 4

    def test_video_platform_uses_the_clip_as_primary_media(self, tmp_path):
        fx = _LaneGFixture(tmp_path)
        fx.orchestrator().run(DATE)
        reels = next(b for b in load_bundles(fx.out_dir, DATE)
                     if b["platform"] == "ig_reels")
        assert reels["payload"]["media"][0].endswith(".mp4")

    def test_image_platform_uses_the_still(self, tmp_path):
        fx = _LaneGFixture(tmp_path)
        fx.orchestrator().run(DATE)
        x = next(b for b in load_bundles(fx.out_dir, DATE) if b["platform"] == "x")
        assert x["payload"]["media"][0].endswith(".png")

    def test_missing_still_defers_instead_of_posting_text_only(self, tmp_path):
        fx = _LaneGFixture(tmp_path, formats=())  # Lane D produced no PNG
        s = fx.orchestrator().run(DATE)
        assert s["packaged"] == 0 and s["missing_media"] == 4

    def test_clip_failure_skips_only_the_video_platforms(self, tmp_path):
        fx = _LaneGFixture(tmp_path)
        def boom(still, out, **kw):
            raise RuntimeError("ffmpeg exploded")
        s = fx.orchestrator(clip_renderer=boom).run(DATE)
        assert s["packaged"] == 2        # x + instagram still ship
        assert s["missing_media"] == 2   # ig_reels + youtube deferred

    def test_non_compliant_caption_is_blocked_not_published(self, tmp_path):
        fx = _LaneGFixture(tmp_path)
        (fx.copy_dir / DATE / "ev-1.json").write_text(json.dumps(
            _copy_draft("ev-1", caption=f"Garantili getiri! $500 kâr\n\n{COMPLIANCE_TR}"),
            ensure_ascii=False), encoding="utf-8")
        s = fx.orchestrator().run(DATE)
        assert s["blocked_compliance"] == 4 and s["packaged"] == 0
        blocked = load_bundles(fx.out_dir, DATE, state="blocked_compliance")
        assert blocked and blocked[0]["violations"]

    def test_malformed_copy_file_is_counted_not_fatal(self, tmp_path):
        fx = _LaneGFixture(tmp_path)
        (fx.copy_dir / DATE / "broken.json").write_text("{not json", encoding="utf-8")
        s = fx.orchestrator().run(DATE)
        assert s["errored"] == 1 and s["packaged"] == 4

    def test_unknown_platform_is_ignored(self, tmp_path):
        fx = _LaneGFixture(tmp_path)
        s = fx.orchestrator(platforms=["x", "myspace"]).run(DATE)
        assert s["packaged"] == 1

    def test_notifier_receives_a_summary_and_cannot_break_the_run(self, tmp_path):
        fx = _LaneGFixture(tmp_path)
        seen: list[str] = []
        fx.orchestrator(notifier=seen.append).run(DATE)
        assert seen and "Lane G" in seen[0]

        fx2 = _LaneGFixture(tmp_path / "second")
        def bad(_):
            raise RuntimeError("telegram down")
        assert fx2.orchestrator(notifier=bad).run(DATE)["packaged"] == 4

    def test_approve_bundle_flips_state(self, tmp_path):
        fx = _LaneGFixture(tmp_path)
        fx.orchestrator().run(DATE)
        p = approve_bundle(fx.out_dir, DATE, "ev-1", "x")
        assert p is not None
        assert json.loads(p.read_text(encoding="utf-8"))["state"] == "approved"
        assert len(load_bundles(fx.out_dir, DATE, state="approved")) == 1

    def test_approve_missing_bundle_returns_none(self, tmp_path):
        fx = _LaneGFixture(tmp_path)
        assert approve_bundle(fx.out_dir, DATE, "nope", "x") is None

    def test_no_copy_dir_yields_empty_summary(self, tmp_path):
        fx = _LaneGFixture(tmp_path)
        s = fx.orchestrator().run("2020-01-01")
        assert s["copy_drafts"] == 0 and s["packaged"] == 0
