"""Lane E multi-platform publisher tests — PR #13c (Phase 4b, gated activation).

Takes an *approved* draft, builds a common envelope (Lane C copy + Lane D media +
mandatory disclaimer), re-runs the compliance checker at publish time (defense in
depth), and dispatches to each *enabled* publisher. Every publisher is behind a
flag (default OFF); publishing is idempotent on (draft_id, platform); partial
success is allowed. Refuses to publish anything that is not `approved` or that
trips compliance.
"""
from __future__ import annotations

from engine.content_jobs import COMPLIANCE_TR
from scripts.lane_e.publisher import LaneEPublisher, PublishResult


class FakePublisher:
    def __init__(self, name, enabled=True, fail=False):
        self.name = name
        self.enabled = enabled
        self.fail = fail
        self.sent: list[dict] = []

    def publish(self, envelope) -> PublishResult:
        if self.fail:
            return PublishResult(platform=self.name, ok=False, error="boom")
        self.sent.append(envelope)
        return PublishResult(platform=self.name, ok=True, ref=f"{self.name}-id-1")


def _draft(draft_id="d1", state="approved", **payload):
    base = {"caption": f"BTC/USDT LONG setup. R:R 1:2. {COMPLIANCE_TR}",
            "media": ["/tmp/lane-d/d1.vertical.json"]}
    base.update(payload)
    return {"draft_id": draft_id, "state": state, "payload": base}


def _pub(tmp_path, publishers):
    return LaneEPublisher(publishers=publishers, state_path=tmp_path / "lane_e_state.json")


def test_publishes_to_enabled_platforms_only(tmp_path):
    tg = FakePublisher("telegram", enabled=True)
    x = FakePublisher("x", enabled=False)
    summary = _pub(tmp_path, [tg, x]).publish_draft(_draft())
    assert summary["status"] == "published"
    assert summary["published"] == ["telegram"]
    assert len(tg.sent) == 1 and len(x.sent) == 0


def test_idempotent_no_double_publish(tmp_path):
    tg = FakePublisher("telegram")
    pub = _pub(tmp_path, [tg])
    pub.publish_draft(_draft())
    second = pub.publish_draft(_draft())
    assert second["skipped"] == ["telegram"]
    assert len(tg.sent) == 1  # not sent twice


def test_partial_success_is_flagged(tmp_path):
    ok = FakePublisher("telegram")
    bad = FakePublisher("x", fail=True)
    summary = _pub(tmp_path, [ok, bad]).publish_draft(_draft())
    assert summary["status"] == "partially_published"
    assert summary["published"] == ["telegram"]
    assert summary["failed"] == ["x"]


def test_refuses_non_approved_draft(tmp_path):
    tg = FakePublisher("telegram")
    summary = _pub(tmp_path, [tg]).publish_draft(_draft(state="pending"))
    assert summary["status"] == "not_approved"
    assert tg.sent == []


def test_compliance_block_refuses_publish(tmp_path):
    tg = FakePublisher("telegram")
    bad = _draft()
    bad["payload"]["caption"] = f"Garantili getiri! {COMPLIANCE_TR}"
    summary = _pub(tmp_path, [tg]).publish_draft(bad)
    assert summary["status"] == "blocked_compliance"
    assert tg.sent == []


def test_envelope_carries_disclaimer_and_media(tmp_path):
    tg = FakePublisher("telegram")
    _pub(tmp_path, [tg]).publish_draft(_draft())
    env = tg.sent[0]
    assert COMPLIANCE_TR in env["text"]
    assert env["media"] == ["/tmp/lane-d/d1.vertical.json"]
    assert env["draft_id"] == "d1"


def test_no_enabled_publishers_is_noop(tmp_path):
    x = FakePublisher("x", enabled=False)
    summary = _pub(tmp_path, [x]).publish_draft(_draft())
    assert summary["status"] == "no_publishers"


def test_publish_state_persists_idempotency_across_instances(tmp_path):
    tg1 = FakePublisher("telegram")
    _pub(tmp_path, [tg1]).publish_draft(_draft())
    tg2 = FakePublisher("telegram")
    summary = _pub(tmp_path, [tg2]).publish_draft(_draft())  # fresh instance, same state file
    assert summary["skipped"] == ["telegram"]
    assert tg2.sent == []
