"""Lane E multi-platform publisher — Phase 4b (PR #13c), gated activation.

Takes an **approved** draft, builds a common envelope (Lane C copy + Lane D media
+ mandatory disclaimer), **re-runs the compliance checker at publish time**
(defense in depth), and dispatches to each **enabled** publisher. Publishers are
flag-gated (default OFF in prod); publishing is **idempotent on (draft_id,
platform)**; partial success is allowed. Refuses anything not `approved` or that
trips compliance.

Only `approved` drafts (from the Phase 5 DraftStore FSM) should reach here.
"""
from __future__ import annotations

import json
import logging
import sys
from pathlib import Path
from typing import Callable, Optional

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from engine.content_jobs import COMPLIANCE_TR
from scripts.content_compliance import find_violations
from scripts.lane_e.publishers.base import Publisher, PublishResult

log = logging.getLogger("efloud.lane_e")


class LaneEPublisher:
    def __init__(self, publishers: list[Publisher], state_path,
                 compliance_check: Callable[[str], list[str]] = find_violations):
        self.publishers = list(publishers)
        self.state_path = Path(state_path)
        self.compliance_check = compliance_check

    # ── idempotency state: {draft_id: {platform: {ok, ref}}} ─────────────────
    def _load(self) -> dict:
        if not self.state_path.exists():
            return {}
        try:
            data = json.loads(self.state_path.read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else {}
        except (OSError, json.JSONDecodeError):
            return {}

    def _save(self, data: dict) -> None:
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        tmp = Path(str(self.state_path) + ".tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(self.state_path)

    def _build_envelope(self, draft: dict) -> dict:
        payload = draft.get("payload", {}) or {}
        text = payload.get("caption", "") or ""
        if COMPLIANCE_TR not in text:
            text = (text + "\n\n" + COMPLIANCE_TR).strip()
        return {
            "draft_id": draft.get("draft_id"),
            "text": text,
            "media": payload.get("media", []),
            "disclaimer": COMPLIANCE_TR,
        }

    def publish_draft(self, draft: dict) -> dict:
        draft_id = draft.get("draft_id")
        if draft.get("state") != "approved":
            return {"draft_id": draft_id, "status": "not_approved",
                    "published": [], "skipped": [], "failed": []}

        envelope = self._build_envelope(draft)
        violations = self.compliance_check(envelope["text"])
        if violations:
            log.warning("lane_e_blocked draft=%s violations=%s", draft_id, violations)
            return {"draft_id": draft_id, "status": "blocked_compliance",
                    "published": [], "skipped": [], "failed": [], "violations": violations}

        enabled = [p for p in self.publishers if getattr(p, "enabled", False)]
        if not enabled:
            return {"draft_id": draft_id, "status": "no_publishers",
                    "published": [], "skipped": [], "failed": []}

        state = self._load()
        done = state.setdefault(draft_id, {})
        published, skipped, failed = [], [], []

        for p in enabled:
            if done.get(p.name, {}).get("ok"):  # idempotent on (draft_id, platform)
                skipped.append(p.name)
                continue
            try:
                res = p.publish(envelope)
            except Exception as e:  # a publisher must never crash the batch
                failed.append(p.name)
                log.warning("lane_e_publish_raised platform=%s err=%s", p.name, e)
                continue
            if res.ok:
                published.append(p.name)
                done[p.name] = {"ok": True, "ref": res.ref}
            else:
                failed.append(p.name)
                log.warning("lane_e_publish_failed platform=%s err=%s", p.name, res.error)

        self._save(state)

        if published and failed:
            status = "partially_published"
        elif published:
            status = "published"
        elif failed:
            status = "failed"
        elif skipped:
            status = "already_published"
        else:
            status = "no_publishers"

        return {"draft_id": draft_id, "status": status,
                "published": published, "skipped": skipped, "failed": failed}


__all__ = ["LaneEPublisher", "Publisher", "PublishResult"]
