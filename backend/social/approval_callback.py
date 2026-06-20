"""
Content approval callback handler — generic, transport-agnostic.

Telegram'ın callback_data mekanizmasıyla uyumlu (`approve:<draft_id>` /
`reject:<draft_id>`), ama Telegram API'sine bağlı değil. Aynı callback format
başka bir mesajlaşma kanalına (Slack, Discord, internal web UI) da uyarlanabilir.

Akış:
  1. render_and_enqueue() → pending_review
  2. Adapter (Telegram/Slack/web) draft preview + inline buttons gönderir
  3. User button basar → "approve:<draft_id>" veya "reject:<draft_id>" callback
  4. handle_callback(data, queue) → ContentQueue transition (approve/reject)
  5. Adapter reply olarak "✅ approved" / "❌ rejected" gösterir

Adapter yazma sorumluluğu dışarıda (lane_e içinde veya ayrı Telegram adapter).
Bu modül sadece business logic.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from enum import Enum
from typing import Any, Callable

from backend.social.content_queue import (  # type: ignore
    ContentDraft,
    ContentStatus,
    approve_draft,
    reject_draft,
)

logger = logging.getLogger(__name__)


class CallbackAction(str, Enum):
    APPROVE = "approve"
    REJECT = "reject"


# Callback data format: "approve:<draft_id>" veya "reject:<draft_id>"
# draft_id 16+ char URL-safe token (create_draft make_draft_id üretir)
_CALLBACK_PATTERN = re.compile(
    r"^(approve|reject):(?P<draft_id>[A-Za-z0-9_-]{12,64})$"
)


class CallbackError(Exception):
    """Base error for callback handling."""


class CallbackFormatError(CallbackError):
    """Callback data formatı tanınmadı."""


class CallbackStateError(CallbackError):
    """Draft state transition geçersiz."""


# ─────────────────────────────────────────────────────────────────────────────
# Parsing
# ─────────────────────────────────────────────────────────────────────────────


@dataclass
class ParsedCallback:
    """Parse edilmiş callback data."""

    action: CallbackAction
    draft_id: str
    raw: str

    @property
    def response_text(self) -> str:
        """Operator'e gösterilecek kısa yanıt."""
        if self.action == CallbackAction.APPROVE:
            return f"✅ approved: {self.draft_id[:8]}…"
        return f"❌ rejected: {self.draft_id[:8]}…"


def parse_callback(data: str) -> ParsedCallback:
    """Raw callback data → ParsedCallback.

    Examples:
        "approve:K2GRzo5K_x9z3abc" → ParsedCallback(action=APPROVE, draft_id=...)
        "reject:K2GRzo5K_x9z3abc" → ParsedCallback(action=REJECT, draft_id=...)
        "garbage" → CallbackFormatError
    """
    if not isinstance(data, str):
        raise CallbackFormatError(f"data string olmalı, bulundu: {type(data).__name__}")
    m = _CALLBACK_PATTERN.match(data.strip())
    if not m:
        raise CallbackFormatError(
            f"callback data formatı tanınmadı: {data!r} "
            f"(beklenen: approve:<draft_id> | reject:<draft_id>)"
        )
    return ParsedCallback(
        action=CallbackAction(m.group(1)),
        draft_id=m.group("draft_id"),
        raw=data,
    )


# ─────────────────────────────────────────────────────────────────────────────
# Queue integration
# ─────────────────────────────────────────────────────────────────────────────


def handle_callback(
    callback: ParsedCallback | str,
    reviewer_id: str,
    draft: ContentDraft,
) -> ContentDraft:
    """Callback'i draft'a uygula → state transition.

    Args:
        callback: ParsedCallback veya raw string ("approve:draft_id")
        reviewer_id: onaylayan/reddeden kullanıcı (Telegram user_id, vs.)
        draft: Mevcut ContentDraft (pending_review state olmalı)

    Returns:
        Güncellenmiş ContentDraft (APPROVED veya REJECTED state)

    Raises:
        CallbackFormatError: callback parse edilemedi
        InvalidTransitionError: draft pending_review değilse
    """
    if isinstance(callback, str):
        callback = parse_callback(callback)

    if callback.draft_id != draft.draft_id:
        # draft_id mismatch → güvenlik: reject et, log
        logger.warning(
            "callback draft_id mismatch: callback=%s draft=%s",
            callback.draft_id[:8], draft.draft_id[:8],
        )
        raise CallbackStateError(
            f"callback draft_id uyuşmuyor: callback={callback.draft_id} draft={draft.draft_id}"
        )

    if draft.status != ContentStatus.PENDING_REVIEW:
        raise CallbackStateError(
            f"draft pending_review değil: {draft.status} (draft_id={draft.draft_id[:8]}…)"
        )

    if callback.action == CallbackAction.APPROVE:
        updated = approve_draft(draft, reviewer_id=reviewer_id)
        logger.info(
            "draft approved via callback: %s by %s",
            draft.draft_id[:8], reviewer_id,
        )
        return updated

    # REJECT — operatörün red sebebini callback'e eklemesi için
    # burada sebep callback formatına dahil değil ("reject:<id>"). Red sebebi
    # opsiyonel olarak dışarıdan parametre olarak verilebilir, şu an default
    # "operator rejected via callback" kullanıyoruz.
    updated = reject_draft(
        draft,
        reviewer_id=reviewer_id,
        reason="rejected via inline callback",
    )
    logger.info(
        "draft rejected via callback: %s by %s",
        draft.draft_id[:8], reviewer_id,
    )
    return updated


def handle_callback_with_reason(
    callback: ParsedCallback | str,
    reviewer_id: str,
    draft: ContentDraft,
    reject_reason: str,
) -> ContentDraft:
    """Callback + custom reject reason (reject için)."""
    if isinstance(callback, str):
        callback = parse_callback(callback)

    if callback.action == CallbackAction.APPROVE:
        return handle_callback(callback, reviewer_id, draft)

    # REJECT: reason override
    if callback.draft_id != draft.draft_id:
        raise CallbackStateError(
            f"callback draft_id uyuşmuyor: callback={callback.draft_id} draft={draft.draft_id}"
        )
    if draft.status != ContentStatus.PENDING_REVIEW:
        raise CallbackStateError(
            f"draft pending_review değil: {draft.status}"
        )

    updated = reject_draft(
        draft,
        reviewer_id=reviewer_id,
        reason=reject_reason,
    )
    logger.info(
        "draft rejected with reason: %s by %s — %s",
        draft.draft_id[:8], reviewer_id, reject_reason,
    )
    return updated


# ─────────────────────────────────────────────────────────────────────────────
# Callback data üretici (adapter yazarlar için helper)
# ─────────────────────────────────────────────────────────────────────────────


def build_callback_data(action: CallbackAction | str, draft_id: str) -> str:
    """Adapter'lar için callback data string üret.

    Examples:
        build_callback_data("approve", "draft_001") → "approve:draft_001"
        build_callback_data(CallbackAction.REJECT, "draft_002") → "reject:draft_002"
    """
    if isinstance(action, CallbackAction):
        action = action.value
    if action not in ("approve", "reject"):
        raise CallbackError(f"action tanınmadı: {action!r}")
    if not draft_id or len(draft_id) < 12:
        raise CallbackError(f"draft_id çok kısa (min 12 char): {draft_id!r}")
    return f"{action}:{draft_id}"
