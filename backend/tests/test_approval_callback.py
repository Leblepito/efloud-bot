"""
Approval callback handler — hermetic unit tests.

Draft mock'lanmaz — gerçek content_queue kullanılır (hermetic, DB yok).
"""
from __future__ import annotations

from datetime import datetime, timezone

import pytest

from backend.social.approval_callback import (
    CallbackAction,
    CallbackError,
    CallbackFormatError,
    CallbackStateError,
    ParsedCallback,
    build_callback_data,
    handle_callback,
    handle_callback_with_reason,
    parse_callback,
)
from backend.social.content_queue import (
    ContentDraft,
    ContentStatus,
    create_draft,
    submit_for_review,
)


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────


def _pending_draft(draft_id: str = "test_draft_001234") -> ContentDraft:
    """pending_review state'te bir draft üret."""
    d = create_draft(
        body="hello world",
        lang="en",
        post_type="signal",
        meta={"symbol": "BTCUSDT"},
    )
    # create_draft random id üretir — test için override
    d.draft_id = draft_id
    return submit_for_review(d, {"violation_count": 0, "violations": []})


# ─────────────────────────────────────────────────────────────────────────────
# parse_callback
# ─────────────────────────────────────────────────────────────────────────────


def test_parse_approve_callback():
    cb = parse_callback("approve:draft_001_xyz12")
    assert cb.action == CallbackAction.APPROVE
    assert cb.draft_id == "draft_001_xyz12"
    assert cb.raw == "approve:draft_001_xyz12"


def test_parse_reject_callback():
    cb = parse_callback("reject:K2GRzo5K_x9z3abc123456")
    assert cb.action == CallbackAction.REJECT
    assert cb.draft_id == "K2GRzo5K_x9z3abc123456"


def test_parse_callback_response_text_approve():
    cb = parse_callback("approve:draft_001_xyz12")
    assert "✅" in cb.response_text
    # draft_id[:8] = "draft_00" (ilk 8 char)
    assert "draft_00" in cb.response_text


def test_parse_callback_response_text_reject():
    cb = parse_callback("reject:draft_001_xyz12")
    assert "❌" in cb.response_text
    assert "draft_00" in cb.response_text


def test_parse_callback_invalid_format():
    with pytest.raises(CallbackFormatError, match="formatı tanınmadı"):
        parse_callback("garbage")


def test_parse_callback_missing_action():
    with pytest.raises(CallbackFormatError):
        parse_callback(":draft_001_xyz12")


def test_parse_callback_short_id():
    with pytest.raises(CallbackFormatError, match="tanınmadı"):
        parse_callback("approve:abc")  # 12 char'dan kısa


def test_parse_callback_empty_string():
    with pytest.raises(CallbackFormatError):
        parse_callback("")


def test_parse_callback_non_string():
    with pytest.raises(CallbackFormatError, match="string olmalı"):
        parse_callback(123)  # type: ignore


# ─────────────────────────────────────────────────────────────────────────────
# build_callback_data
# ─────────────────────────────────────────────────────────────────────────────


def test_build_approve_callback_data():
    assert build_callback_data("approve", "draft_001_xyz12") == "approve:draft_001_xyz12"


def test_build_reject_callback_data_with_enum():
    assert build_callback_data(CallbackAction.REJECT, "draft_001_xyz12") == "reject:draft_001_xyz12"


def test_build_callback_roundtrip():
    raw = build_callback_data(CallbackAction.APPROVE, "draft_001_xyz12")
    parsed = parse_callback(raw)
    assert parsed.action == CallbackAction.APPROVE
    assert parsed.draft_id == "draft_001_xyz12"


def test_build_callback_invalid_action():
    with pytest.raises(CallbackError, match="action tanınmadı"):
        build_callback_data("delete", "draft_001_xyz12")


def test_build_callback_short_id():
    with pytest.raises(CallbackError, match="draft_id çok kısa"):
        build_callback_data("approve", "abc")


# ─────────────────────────────────────────────────────────────────────────────
# handle_callback — happy path
# ─────────────────────────────────────────────────────────────────────────────


def test_handle_approve_callback():
    d = _pending_draft()
    updated = handle_callback(
        f"approve:{d.draft_id}", reviewer_id="utku", draft=d,
    )
    assert updated.status == ContentStatus.APPROVED
    assert updated.reviewer_id == "utku"
    assert updated.reviewed_at is not None


def test_handle_reject_callback():
    d = _pending_draft()
    updated = handle_callback(
        f"reject:{d.draft_id}", reviewer_id="utku", draft=d,
    )
    assert updated.status == ContentStatus.REJECTED
    assert updated.reviewer_id == "utku"
    assert updated.rejection_reason is not None
    assert "callback" in updated.rejection_reason


def test_handle_callback_with_parsed_object():
    d = _pending_draft()
    cb = parse_callback(f"approve:{d.draft_id}")
    updated = handle_callback(cb, reviewer_id="utku", draft=d)
    assert updated.status == ContentStatus.APPROVED


def test_handle_callback_with_custom_reject_reason():
    d = _pending_draft()
    updated = handle_callback_with_reason(
        f"reject:{d.draft_id}",
        reviewer_id="utku",
        draft=d,
        reject_reason="çok ajitatif, revize et",
    )
    assert updated.status == ContentStatus.REJECTED
    assert updated.rejection_reason == "çok ajitatif, revize et"


# ─────────────────────────────────────────────────────────────────────────────
# handle_callback — error paths
# ─────────────────────────────────────────────────────────────────────────────


def test_handle_callback_draft_id_mismatch_raises():
    """draft_id uyuşmazsa güvenlik reddi."""
    d = _pending_draft(draft_id="correct_draft_id_001234")
    with pytest.raises(CallbackStateError, match="draft_id uyuşmuyor"):
        handle_callback(
            "approve:wrong_draft_id_999999",
            reviewer_id="utku",
            draft=d,
        )


def test_handle_callback_wrong_state_raises():
    """pending_review değilse InvalidTransitionError."""
    d = _pending_draft()
    # Draft'ı DRAFT state'ine geri al
    d.status = ContentStatus.DRAFT
    with pytest.raises(CallbackStateError, match="pending_review değil"):
        handle_callback(
            f"approve:{d.draft_id}",
            reviewer_id="utku",
            draft=d,
        )


def test_handle_callback_approved_draft_cannot_approve_again():
    """Zaten approved olan draft'a tekrar approve gelirse fail."""
    d = _pending_draft()
    d = handle_callback(f"approve:{d.draft_id}", reviewer_id="utku", draft=d)
    # Şimdi tekrar approve deneyelim
    with pytest.raises(CallbackStateError, match="pending_review değil"):
        handle_callback(f"approve:{d.draft_id}", reviewer_id="utku2", draft=d)


def test_handle_callback_invalid_format_string_raises():
    d = _pending_draft()
    with pytest.raises(CallbackFormatError):
        handle_callback("not-a-valid-callback", reviewer_id="utku", draft=d)


# ─────────────────────────────────────────────────────────────────────────────
# Lane topology guard
# ─────────────────────────────────────────────────────────────────────────────


def test_module_no_telegram_import():
    """approval_callback Telegram API'ye bağlı değil — transport-agnostic."""
    import re
    from pathlib import Path
    src = Path(__file__).parent.parent / "social" / "approval_callback.py"
    text = src.read_text(encoding="utf-8")
    # Docstring ve yorumları çıkar
    code = re.sub(r'"""[\s\S]*?"""', '', text)
    code = re.sub(r"'''[\s\S]*?'''", '', code)
    code = re.sub(r"#.*$", "", code, flags=re.MULTILINE)
    # Telegram'a özgü import/call yok (python-telegram-bot, telebot, vb.)
    assert "telegram" not in code.lower()
    assert "telebot" not in code
    assert "Bot(" not in code  # telegram.Bot() çağrısı yok
