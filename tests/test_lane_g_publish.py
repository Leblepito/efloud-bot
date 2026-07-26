"""Tests — Lane G publish runner (approved bundles → Lane E dispatch).

Verifies the three default-closed safety gates that stand between a generated
chart and a live social post:

  1. only ``approved`` bundles are ever dispatched;
  2. a publisher that is not ``enabled`` (env flag off) publishes nothing;
  3. ``dry_run`` never touches a real client.

Plus idempotency (no double-post on re-run) and the client adapter's media
routing (image → Instagram, MP4 → YouTube Shorts).

Fully offline: no network, no credentials, no MCP session.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

import pytest

from engine.content_jobs import COMPLIANCE_TR
from scripts.lane_e.publishers.base import PublishResult
from scripts.lane_g_publish import (
    DryRunPublisher,
    PlatformClientPublisher,
    build_publishers,
    run,
)

DATE = "2026-07-26"


def _write_bundle(out_dir: Path, event_id: str, platform: str, *,
                  state: str = "approved", caption: Optional[str] = None,
                  media: Optional[list[str]] = None) -> Path:
    d = out_dir / DATE / "bundles"
    d.mkdir(parents=True, exist_ok=True)
    p = d / f"{event_id}.{platform}.json"
    p.write_text(json.dumps({
        "draft_id": f"{event_id}:{platform}",
        "event_id": event_id,
        "platform": platform,
        "symbol": "BTC/USDT",
        "state": state,
        "violations": [],
        "payload": {
            "caption": caption if caption is not None
                       else f"BTC/USDT · 15m · LONG\nRisk ~2.0%\n\n{COMPLIANCE_TR}",
            "media": media if media is not None else ["/tmp/chart.still.png"],
            "thread": [],
            "alt_text": "chart",
        },
    }, ensure_ascii=False), encoding="utf-8")
    return p


class _FakeClient:
    """Stands in for a backend/social client (XurlClient / InstagramClient / …)."""

    def __init__(self, *, active: bool = True, ok: bool = True, raises: bool = False):
        self._active = active
        self._ok = ok
        self._raises = raises
        self.seen: list[object] = []

    def is_active(self) -> bool:
        return self._active

    def post_draft(self, draft):
        self.seen.append(draft)
        if self._raises:
            raise RuntimeError("api exploded")
        return type("Resp", (), {
            "ok": self._ok,
            "post_url": "https://x.com/u2algo/status/1" if self._ok else None,
            "post_id": "1" if self._ok else None,
            "stderr": None if self._ok else "rate limited",
        })()


class TestApprovalGate:
    def test_pending_review_bundles_are_never_dispatched(self, tmp_path):
        _write_bundle(tmp_path, "ev-1", "x", state="pending_review")
        pub = DryRunPublisher()
        s = run(bundle_dir=tmp_path, date=DATE, state_path=tmp_path / "st.json",
                publishers=[pub])
        assert s["approved"] == 0 and s["published"] == 0
        assert pub.calls == []

    def test_blocked_compliance_bundles_are_never_dispatched(self, tmp_path):
        _write_bundle(tmp_path, "ev-1", "x", state="blocked_compliance")
        pub = DryRunPublisher()
        run(bundle_dir=tmp_path, date=DATE, state_path=tmp_path / "st.json",
            publishers=[pub])
        assert pub.calls == []

    def test_approved_bundle_is_dispatched(self, tmp_path):
        _write_bundle(tmp_path, "ev-1", "x")
        pub = DryRunPublisher()
        s = run(bundle_dir=tmp_path, date=DATE, state_path=tmp_path / "st.json",
                publishers=[pub])
        assert s["published"] == 1 and len(pub.calls) == 1

    def test_no_bundles_is_a_clean_noop(self, tmp_path):
        s = run(bundle_dir=tmp_path, date=DATE, state_path=tmp_path / "st.json",
                publishers=[DryRunPublisher()])
        assert s == {"date": DATE, "approved": 0, "published": 0, "failed": 0,
                     "skipped": 0, "dry_run": True, "results": []}


class TestComplianceAtPublishTime:
    def test_non_compliant_caption_is_blocked_even_if_marked_approved(self, tmp_path):
        # Defence in depth: an operator (or a bug) approving bad copy must still
        # not reach a platform — Lane E re-runs find_violations on the envelope.
        _write_bundle(tmp_path, "ev-1", "x",
                      caption=f"Garantili getiri, $500 kâr\n\n{COMPLIANCE_TR}")
        pub = DryRunPublisher()
        s = run(bundle_dir=tmp_path, date=DATE, state_path=tmp_path / "st.json",
                publishers=[pub])
        assert s["published"] == 0
        assert pub.calls == []
        assert s["results"][0]["status"] == "blocked_compliance"

    def test_disclaimer_is_injected_into_the_envelope_when_absent(self, tmp_path):
        _write_bundle(tmp_path, "ev-1", "x", caption="BTC/USDT LONG setup")
        pub = DryRunPublisher()
        run(bundle_dir=tmp_path, date=DATE, state_path=tmp_path / "st.json",
            publishers=[pub])
        assert COMPLIANCE_TR in pub.calls[0]["text"]


class TestPublisherFlagGate:
    def test_disabled_publisher_publishes_nothing(self, tmp_path):
        _write_bundle(tmp_path, "ev-1", "x")
        client = _FakeClient(active=False)
        s = run(bundle_dir=tmp_path, date=DATE, state_path=tmp_path / "st.json",
                dry_run=False, publishers=[PlatformClientPublisher("x", client)])
        assert s["published"] == 0
        assert s["results"][0]["status"] == "no_publishers"
        assert client.seen == []

    def test_enabled_publisher_receives_the_envelope(self, tmp_path):
        _write_bundle(tmp_path, "ev-1", "x")
        client = _FakeClient(active=True)
        s = run(bundle_dir=tmp_path, date=DATE, state_path=tmp_path / "st.json",
                dry_run=False, publishers=[PlatformClientPublisher("x", client)])
        assert s["published"] == 1 and len(client.seen) == 1

    def test_client_failure_is_reported_not_raised(self, tmp_path):
        _write_bundle(tmp_path, "ev-1", "x")
        s = run(bundle_dir=tmp_path, date=DATE, state_path=tmp_path / "st.json",
                dry_run=False,
                publishers=[PlatformClientPublisher("x", _FakeClient(ok=False))])
        assert s["failed"] == 1 and s["published"] == 0

    def test_client_exception_is_contained(self, tmp_path):
        _write_bundle(tmp_path, "ev-1", "x")
        s = run(bundle_dir=tmp_path, date=DATE, state_path=tmp_path / "st.json",
                dry_run=False,
                publishers=[PlatformClientPublisher("x", _FakeClient(raises=True))])
        assert s["failed"] == 1

    def test_is_active_raising_counts_as_disabled(self, tmp_path):
        class Broken:
            def is_active(self):
                raise RuntimeError("creds backend down")

            def post_draft(self, draft):  # pragma: no cover - must never run
                raise AssertionError("must not publish when is_active() failed")

        _write_bundle(tmp_path, "ev-1", "x")
        s = run(bundle_dir=tmp_path, date=DATE, state_path=tmp_path / "st.json",
                dry_run=False, publishers=[PlatformClientPublisher("x", Broken())])
        assert s["published"] == 0


class TestMediaRouting:
    def test_image_bundle_reaches_the_client_as_media(self, tmp_path):
        _write_bundle(tmp_path, "ev-1", "instagram", media=["/tmp/c.still.png"])
        client = _FakeClient()
        run(bundle_dir=tmp_path, date=DATE, state_path=tmp_path / "st.json",
            dry_run=False, publishers=[PlatformClientPublisher("instagram", client)])
        assert client.seen[0].meta["media"] == ["/tmp/c.still.png"]

    def test_clip_bundle_reaches_the_client_as_media(self, tmp_path):
        _write_bundle(tmp_path, "ev-1", "youtube", media=["/tmp/c.vertical.mp4"])
        client = _FakeClient()
        run(bundle_dir=tmp_path, date=DATE, state_path=tmp_path / "st.json",
            dry_run=False, publishers=[PlatformClientPublisher("youtube", client)])
        assert client.seen[0].meta["media"] == ["/tmp/c.vertical.mp4"]


class TestIdempotency:
    def test_rerun_does_not_double_publish(self, tmp_path):
        _write_bundle(tmp_path, "ev-1", "x")
        state = tmp_path / "st.json"
        first = run(bundle_dir=tmp_path, date=DATE, state_path=state,
                    publishers=[DryRunPublisher()])
        second = run(bundle_dir=tmp_path, date=DATE, state_path=state,
                     publishers=[DryRunPublisher()])
        assert first["published"] == 1
        assert second["published"] == 0 and second["skipped"] == 1

    def test_each_platform_bundle_is_tracked_separately(self, tmp_path):
        for platform in ("x", "instagram", "youtube"):
            _write_bundle(tmp_path, "ev-1", platform)
        s = run(bundle_dir=tmp_path, date=DATE, state_path=tmp_path / "st.json",
                publishers=[DryRunPublisher()])
        assert s["approved"] == 3 and s["published"] == 3


class TestBuildPublishers:
    def test_dry_run_returns_a_single_recording_publisher(self):
        pubs = build_publishers(dry_run=True)
        assert len(pubs) == 1 and isinstance(pubs[0], DryRunPublisher)
        assert pubs[0].enabled is True

    def test_live_mode_wires_real_clients_but_they_self_gate(self):
        # With no platform env flags set every client reports inactive, so a live
        # run is still a no-op — this is the posture a fresh deploy must have.
        pubs = build_publishers(dry_run=False)
        assert all(not p.enabled for p in pubs)


class TestNotifier:
    def test_notifier_gets_a_summary(self, tmp_path):
        _write_bundle(tmp_path, "ev-1", "x")
        seen: list[str] = []
        run(bundle_dir=tmp_path, date=DATE, state_path=tmp_path / "st.json",
            publishers=[DryRunPublisher()], notifier=seen.append)
        assert seen and "DRY-RUN" in seen[0]

    def test_broken_notifier_does_not_fail_the_run(self, tmp_path):
        _write_bundle(tmp_path, "ev-1", "x")

        def bad(_):
            raise RuntimeError("telegram down")

        s = run(bundle_dir=tmp_path, date=DATE, state_path=tmp_path / "st.json",
                publishers=[DryRunPublisher()], notifier=bad)
        assert s["published"] == 1

    def test_live_mode_is_labelled_in_the_notification(self, tmp_path):
        _write_bundle(tmp_path, "ev-1", "x")
        seen: list[str] = []
        run(bundle_dir=tmp_path, date=DATE, state_path=tmp_path / "st.json",
            dry_run=False, publishers=[PlatformClientPublisher("x", _FakeClient())],
            notifier=seen.append)
        assert seen and "LIVE" in seen[0]
