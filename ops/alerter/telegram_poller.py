"""Telegram approval poller + draft FSM — Phase 5 (PR #17), the publish gate.

`DraftStore` is a small file-backed finite-state machine for content drafts:

    pending ──approve──▶ approved ──publish──▶ published
       │  ├─reject──▶ rejected            └─fail──▶ failed
       │  ├─edit────▶ edited ──approve──▶ approved / ──reject──▶ rejected
       └──expire───▶ expired   (TTL only; never publishes)

Idempotent on ``draft_id``; stale/duplicate callbacks are FSM no-ops. Fail-safe:
drafts stay ``pending`` indefinitely and the optional TTL only ever moves them to
``expired`` — it never auto-publishes. Only ``approved`` drafts feed Lane E.

`ApprovalPoller` long-polls ``getUpdates`` through an injected ``transport``
callable (urllib in prod, a fake in tests), answers the callback within
Telegram's 10s window, applies the FSM transition, and edits the message.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Callable, Optional

log = logging.getLogger("efloud.alerter.poller")

TRANSITIONS: dict[str, dict[str, str]] = {
    "pending": {"approve": "approved", "reject": "rejected",
                "edit": "edited", "expire": "expired"},
    "edited": {"approve": "approved", "reject": "rejected"},
    "approved": {"publish": "published", "fail": "failed"},
}
TERMINAL_STATES = {"rejected", "published", "failed", "expired"}

Transport = Callable[[str, dict], dict]


def _now() -> datetime:
    return datetime.now(timezone.utc)


class DraftStore:
    """Durable FSM store for content drafts (JSON file, atomic write)."""

    def __init__(self, path):
        self.path = Path(path)
        self._data: dict[str, dict] = self._load()

    def _load(self) -> dict:
        if not self.path.exists():
            return {}
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else {}
        except (OSError, json.JSONDecodeError) as e:
            log.warning("draftstore_load_failed err=%s", e)
            return {}

    def _save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = Path(str(self.path) + ".tmp")
        tmp.write_text(json.dumps(self._data, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(self.path)

    def add(self, draft_id: str, payload: dict,
            created_at: Optional[datetime] = None) -> dict:
        if draft_id in self._data:  # idempotent — never clobber an existing draft
            return self._data[draft_id]
        ts = (created_at or _now()).isoformat()
        self._data[draft_id] = {
            "draft_id": draft_id, "state": "pending", "payload": payload,
            "created_at": ts, "updated_at": ts, "message_id": None,
        }
        self._save()
        return self._data[draft_id]

    def get(self, draft_id: str) -> Optional[dict]:
        return self._data.get(draft_id)

    def transition(self, draft_id: str, action: str) -> tuple[Optional[str], bool]:
        """Apply ``action``. Returns ``(new_state, changed)``; invalid/duplicate
        actions are no-ops returning ``(current_state, False)``."""
        d = self._data.get(draft_id)
        if d is None:
            return None, False
        nxt = TRANSITIONS.get(d["state"], {}).get(action)
        if nxt is None:
            return d["state"], False
        d["state"] = nxt
        d["updated_at"] = _now().isoformat()
        self._save()
        return nxt, True

    def list(self, state: Optional[str] = None) -> list[dict]:
        items = list(self._data.values())
        return [d for d in items if d["state"] == state] if state else items

    def set_message_id(self, draft_id: str, message_id: int) -> None:
        d = self._data.get(draft_id)
        if d is not None:
            d["message_id"] = message_id
            self._save()

    def expire_stale(self, now: datetime, ttl_hours: Optional[float]) -> int:
        """Move ``pending`` drafts older than the TTL to ``expired``. TTL of
        ``None`` (default) disables expiry. Never touches non-pending drafts and
        never publishes."""
        if ttl_hours is None:
            return 0
        cutoff = now - timedelta(hours=ttl_hours)
        n = 0
        for d in self._data.values():
            if d["state"] != "pending":
                continue
            if datetime.fromisoformat(d["created_at"]) < cutoff:
                d["state"] = "expired"
                d["updated_at"] = now.isoformat()
                n += 1
        if n:
            self._save()
        return n


class ApprovalPoller:
    """Long-poll getUpdates and drive the DraftStore FSM from callback_query."""

    def __init__(self, store: DraftStore, transport: Transport,
                 token: Optional[str] = None, offset_path=None):
        self.store = store
        self.transport = transport
        self.token = token
        self.offset_path = Path(offset_path) if offset_path else (store.path.parent / "tg_offset.txt")
        self._offset = self._load_offset()

    def _load_offset(self) -> int:
        if not self.offset_path.exists():
            return 0
        try:
            return int(self.offset_path.read_text(encoding="utf-8").strip() or 0)
        except (OSError, ValueError):
            return 0

    def _save_offset(self) -> None:
        self.offset_path.parent.mkdir(parents=True, exist_ok=True)
        self.offset_path.write_text(str(self._offset), encoding="utf-8")

    def poll_once(self, timeout: int = 25) -> int:
        params: dict = {"timeout": timeout}
        if self._offset:
            params["offset"] = self._offset
        try:
            resp = self.transport("getUpdates", params)
        except Exception as e:  # transport hiccup must not kill the loop
            log.warning("poller_getupdates_failed err=%s", e)
            return 0
        updates = resp.get("result", []) if resp.get("ok") else []
        processed = 0
        for u in updates:
            self._offset = max(self._offset, int(u["update_id"]) + 1)
            if u.get("callback_query"):
                self._handle_callback(u["callback_query"])
                processed += 1
        if updates:
            self._save_offset()
        return processed

    def _handle_callback(self, cbq: dict) -> None:
        msg = cbq.get("message", {}) or {}
        message_id = msg.get("message_id")
        chat_id = (msg.get("chat") or {}).get("id")
        draft_id, _, action = (cbq.get("data", "") or "").partition("|")

        # Answer first (<10s) so the button stops spinning, before any mutation.
        try:
            self.transport("answerCallbackQuery", {"callback_query_id": cbq.get("id")})
        except Exception as e:
            log.warning("poller_answer_failed err=%s", e)

        new_state, changed = self.store.transition(draft_id, action)
        label = new_state or "bilinmeyen taslak"
        if chat_id is not None and message_id is not None:
            try:
                self.transport("editMessageText", {
                    "chat_id": chat_id, "message_id": message_id,
                    "text": f"Taslak {draft_id}: {label}",
                })
            except Exception as e:
                log.warning("poller_edit_failed err=%s", e)
        log.info("poller_callback draft=%s action=%s -> %s changed=%s",
                 draft_id, action, new_state, changed)


def make_transport(token: str) -> Transport:  # pragma: no cover - real network
    """urllib-based transport for prod (POST /bot<token>/<method>)."""
    import urllib.parse
    import urllib.request

    def _t(method: str, params: dict) -> dict:
        url = f"https://api.telegram.org/bot{token}/{method}"
        data = urllib.parse.urlencode(
            {k: (json.dumps(v) if isinstance(v, (dict, list)) else v)
             for k, v in params.items()}).encode("utf-8")
        req = urllib.request.Request(url, data=data, method="POST")
        with urllib.request.urlopen(req, timeout=max(30, int(params.get("timeout", 25)) + 5)) as r:
            return json.loads(r.read().decode("utf-8"))
    return _t


__all__ = ["DraftStore", "ApprovalPoller", "TRANSITIONS", "TERMINAL_STATES", "make_transport"]
