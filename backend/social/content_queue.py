"""
Content Approval Queue — skeleton (P-002 M6).

Generic draft → pending_review → approved/rejected state machine.
Tier2 renderers (signal/educational/recap/promo/market_update) operatör
template'lerine bağlanacak (M6 deliverable).

NOT production-ready: Telegram gateway hook, xurl/Manus gönderimi
T-026/T-025 entegrasyonunda gelecek.
"""
from __future__ import annotations

import logging
import secrets
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


class ContentStatus(str, Enum):
    DRAFT = "draft"
    PENDING_REVIEW = "pending_review"
    APPROVED = "approved"
    REJECTED = "rejected"
    SENT = "sent"            # T-026/T-025 entegrasyonu sonrası
    FAILED = "failed"


@dataclass
class ContentDraft:
    draft_id: str                       # 16-char token
    body: str                           # post text (TR/EN/RU/KZ)
    lang: str                           # "en" | "tr" | "ru" | "kz" | "all"
    post_type: str                      # "signal" | "educational" | "performance_recap" | "promo" | "market_update"
    meta: dict[str, Any] = field(default_factory=dict)  # chart_url, signal_id, side, entry, sl, tp1, tp2 vs.
    status: ContentStatus = ContentStatus.DRAFT
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    reviewed_at: datetime | None = None
    reviewer_id: str | None = None
    rejection_reason: str | None = None
    compliance_report: dict[str, Any] | None = None  # scripts.content_compliance.find_violations çıktısı

    def to_dict(self) -> dict[str, Any]:
        return {
            "draft_id": self.draft_id,
            "body": self.body,
            "lang": self.lang,
            "post_type": self.post_type,
            "meta": self.meta,
            "status": self.status.value,
            "created_at": self.created_at.isoformat(),
            "reviewed_at": self.reviewed_at.isoformat() if self.reviewed_at else None,
            "reviewer_id": self.reviewer_id,
            "rejection_reason": self.rejection_reason,
            "compliance_report": self.compliance_report,
        }


class ContentQueueError(Exception):
    """Base error for content queue."""


class InvalidTransitionError(ContentQueueError):
    """Geçersiz state transition."""


class ComplianceGateError(ContentQueueError):
    """Compliance gate 0-ihlal kanıtı yok."""


# İzin verilen transition'lar
_ALLOWED_TRANSITIONS: dict[ContentStatus, set[ContentStatus]] = {
    ContentStatus.DRAFT: {ContentStatus.PENDING_REVIEW, ContentStatus.REJECTED},
    ContentStatus.PENDING_REVIEW: {ContentStatus.APPROVED, ContentStatus.REJECTED},
    ContentStatus.APPROVED: {ContentStatus.SENT, ContentStatus.FAILED, ContentStatus.REJECTED},
    ContentStatus.REJECTED: {ContentStatus.DRAFT},  # revise → re-draft
    ContentStatus.SENT: set(),  # terminal
    ContentStatus.FAILED: {ContentStatus.DRAFT},  # retry → re-draft
}


def make_draft_id() -> str:
    """16-char URL-safe token."""
    return secrets.token_urlsafe(12)


def validate_draft(body: str, lang: str, post_type: str) -> None:
    """Skeleton doğrulama — genişletilebilir."""
    if not body or not body.strip():
        raise ContentQueueError("body boş olamaz")
    if len(body) > 4000:
        raise ContentQueueError(f"body çok uzun: {len(body)} > 4000 char (X premium 25k, default güvenli)")
    if lang not in ("en", "tr", "ru", "kz", "all"):
        raise ContentQueueError(f"desteklenmeyen lang: {lang}")
    if post_type not in ("signal", "educational", "performance_recap", "promo", "market_update"):
        raise ContentQueueError(f"desteklenmeyen post_type: {post_type}")


def create_draft(body: str, lang: str, post_type: str, meta: dict[str, Any] | None = None) -> ContentDraft:
    """Yeni draft oluştur (DRAFT state)."""
    validate_draft(body, lang, post_type)
    return ContentDraft(
        draft_id=make_draft_id(),
        body=body.strip(),
        lang=lang,
        post_type=post_type,
        meta=meta or {},
        status=ContentStatus.DRAFT,
    )


def submit_for_review(draft: ContentDraft, compliance_report: dict[str, Any]) -> ContentDraft:
    """DRAFT → PENDING_REVIEW (compliance gate ile).

    compliance_report: scripts.content_compliance.find_violations çıktısı.
    violation_count == 0 olmalı, aksi halde ComplianceGateError.
    """
    if draft.status != ContentStatus.DRAFT:
        raise InvalidTransitionError(f"DRAFT → PENDING_REVIEW değil: {draft.status}")
    if compliance_report.get("violation_count", -1) != 0:
        raise ComplianceGateError(
            f"compliance gate ihlal buldu: {compliance_report.get('violation_count')} violations"
        )
    draft.compliance_report = compliance_report
    draft.status = ContentStatus.PENDING_REVIEW
    logger.info(
        "draft %s → pending_review (lang=%s type=%s)",
        draft.draft_id, draft.lang, draft.post_type,
    )
    return draft


def approve_draft(draft: ContentDraft, reviewer_id: str) -> ContentDraft:
    """PENDING_REVIEW → APPROVED."""
    if draft.status != ContentStatus.PENDING_REVIEW:
        raise InvalidTransitionError(f"PENDING_REVIEW → APPROVED değil: {draft.status}")
    draft.status = ContentStatus.APPROVED
    draft.reviewed_at = datetime.now(timezone.utc)
    draft.reviewer_id = reviewer_id
    draft.rejection_reason = None
    logger.info("draft %s approved by %s", draft.draft_id, reviewer_id)
    return draft


def reject_draft(draft: ContentDraft, reviewer_id: str, reason: str) -> ContentDraft:
    """PENDING_REVIEW veya APPROVED → REJECTED."""
    if draft.status not in (ContentStatus.PENDING_REVIEW, ContentStatus.APPROVED):
        raise InvalidTransitionError(f"REJECTED edilemez: {draft.status}")
    draft.status = ContentStatus.REJECTED
    draft.reviewed_at = datetime.now(timezone.utc)
    draft.reviewer_id = reviewer_id
    draft.rejection_reason = reason
    logger.info("draft %s rejected by %s: %s", draft.draft_id, reviewer_id, reason)
    return draft


def mark_sent(draft: ContentDraft) -> ContentDraft:
    """APPROVED → SENT (T-026/T-025 gönderim sonrası)."""
    if draft.status != ContentStatus.APPROVED:
        raise InvalidTransitionError(f"APPROVED → SENT değil: {draft.status}")
    draft.status = ContentStatus.SENT
    return draft


def mark_failed(draft: ContentDraft, error: str) -> ContentDraft:
    """APPROVED → FAILED."""
    if draft.status != ContentStatus.APPROVED:
        raise InvalidTransitionError(f"APPROVED → FAILED değil: {draft.status}")
    draft.status = ContentStatus.FAILED
    draft.rejection_reason = error  # burada error olarak kullanıyoruz
    return draft


def revise_rejected(draft: ContentDraft, new_body: str) -> ContentDraft:
    """REJECTED veya FAILED → DRAFT (yeni body ile yeniden taslak)."""
    if draft.status not in (ContentStatus.REJECTED, ContentStatus.FAILED):
        raise InvalidTransitionError(f"revise edilemez: {draft.status}")
    if not new_body or not new_body.strip():
        raise ContentQueueError("new_body boş olamaz")
    draft.body = new_body.strip()
    draft.status = ContentStatus.DRAFT
    draft.compliance_report = None
    draft.reviewed_at = None
    draft.reviewer_id = None
    draft.rejection_reason = None
    return draft
