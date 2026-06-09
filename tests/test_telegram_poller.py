"""Telegram approval poller + draft FSM — PR #17 (Phase 5 publish gate).

`DraftStore` is a file-backed FSM (pending → approved | rejected | edited |
published | failed | expired), idempotent on draft_id. `ApprovalPoller` long-polls
getUpdates via an injected transport, handles callback_query, answers within
Telegram's 10s window, transitions the draft, and edits the message. Fail-safe:
drafts stay `pending` indefinitely; the optional TTL only ever → `expired`
(never publishes). Only `approved` drafts feed Lane E.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from ops.alerter.telegram_poller import (
    TERMINAL_STATES,
    ApprovalPoller,
    DraftStore,
)


@pytest.fixture
def store(tmp_path):
    return DraftStore(tmp_path / "drafts.json")


# ── DraftStore FSM ───────────────────────────────────────────────────────────

def test_add_creates_pending(store):
    store.add("d1", {"caption": "hi"})
    assert store.get("d1")["state"] == "pending"


def test_approve_moves_pending_to_approved(store):
    store.add("d1", {})
    new, changed = store.transition("d1", "approve")
    assert new == "approved" and changed is True


def test_reject_and_edit_transitions(store):
    store.add("d1", {}); store.add("d2", {})
    assert store.transition("d1", "reject")[0] == "rejected"
    assert store.transition("d2", "edit")[0] == "edited"


def test_double_approve_is_idempotent_noop(store):
    store.add("d1", {})
    store.transition("d1", "approve")
    new, changed = store.transition("d1", "approve")  # stale/duplicate tap
    assert new == "approved" and changed is False


def test_invalid_transition_is_noop(store):
    store.add("d1", {})
    store.transition("d1", "reject")           # terminal
    new, changed = store.transition("d1", "approve")
    assert new == "rejected" and changed is False


def test_state_persists_across_instances(store, tmp_path):
    store.add("d1", {}); store.transition("d1", "approve")
    reopened = DraftStore(tmp_path / "drafts.json")
    assert reopened.get("d1")["state"] == "approved"


def test_only_approved_listed(store):
    store.add("d1", {}); store.add("d2", {})
    store.transition("d1", "approve")
    assert [d["draft_id"] for d in store.list(state="approved")] == ["d1"]


def test_ttl_off_by_default_keeps_pending(store):
    store.add("d1", {})
    expired = store.expire_stale(now=datetime(2099, 1, 1, tzinfo=timezone.utc), ttl_hours=None)
    assert expired == 0
    assert store.get("d1")["state"] == "pending"


def test_ttl_expires_only_old_pending_never_publishes(store):
    old = datetime(2026, 6, 1, tzinfo=timezone.utc)
    store.add("d1", {}, created_at=old)        # stale pending
    store.add("d2", {})                         # fresh pending
    store.transition("d2", "approve")           # approved fresh (must be untouched)
    store.add("d3", {}, created_at=old); store.transition("d3", "approve")  # old but approved
    now = old + timedelta(hours=72)
    n = store.expire_stale(now=now, ttl_hours=48)
    assert n == 1
    assert store.get("d1")["state"] == "expired"
    assert store.get("d3")["state"] == "approved"   # TTL never touches non-pending
    assert "expired" in TERMINAL_STATES


# ── ApprovalPoller ───────────────────────────────────────────────────────────

class _FakeTransport:
    """Records API calls; getUpdates returns scripted batches then empties."""

    def __init__(self, update_batches):
        self.batches = list(update_batches)
        self.calls: list[tuple[str, dict]] = []

    def __call__(self, method, params):
        self.calls.append((method, params))
        if method == "getUpdates":
            result = self.batches.pop(0) if self.batches else []
            return {"ok": True, "result": result}
        return {"ok": True, "result": True}

    def methods(self):
        return [m for m, _ in self.calls]


def _callback_update(update_id, draft_id, action, message_id=555):
    return {
        "update_id": update_id,
        "callback_query": {
            "id": f"cbq{update_id}",
            "data": f"{draft_id}|{action}",
            "message": {"message_id": message_id, "chat": {"id": 42}},
        },
    }


def test_poll_processes_approve_callback(store):
    store.add("d1", {})
    t = _FakeTransport([[_callback_update(10, "d1", "approve")]])
    poller = ApprovalPoller(store=store, transport=t, token="TOK")

    n = poller.poll_once()

    assert n == 1
    assert store.get("d1")["state"] == "approved"
    methods = t.methods()
    assert "answerCallbackQuery" in methods            # answered (<10s window)
    assert any(m.startswith("editMessage") for m in methods)  # message updated


def test_poll_answers_unknown_draft_without_crashing(store):
    t = _FakeTransport([[_callback_update(11, "ghost", "approve")]])
    poller = ApprovalPoller(store=store, transport=t, token="TOK")
    n = poller.poll_once()
    assert n == 1
    assert "answerCallbackQuery" in t.methods()        # still answered, no raise


def test_offset_advances_so_updates_not_reprocessed(store):
    store.add("d1", {})
    t = _FakeTransport([[_callback_update(20, "d1", "approve")], []])
    poller = ApprovalPoller(store=store, transport=t, token="TOK")
    poller.poll_once()
    poller.poll_once()
    # second getUpdates must pass offset = last_update_id + 1 = 21
    get_calls = [p for m, p in t.calls if m == "getUpdates"]
    assert get_calls[1]["offset"] == 21
