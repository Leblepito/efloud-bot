# T-030 — P-002 M6 follow-up: Approval Callback Handler

Epic: P-002
Claimed by: @hermes
branch: feat/p002-m6-templates (renderer PR'a merge edilecek)
claimed_at: 2026-06-19T18:50:00Z
status: DONE (push bekliyor)

## Goal
Telegram/Slack/web UI inline button callback'lerini queue state transition'a
bağlayan generic handler. Telegram API'ye bağlı değil (transport-agnostic).

## Scope
- `backend/social/approval_callback.py` — ParsedCallback + parse + handle + build
- `backend/tests/test_approval_callback.py` — 23 hermetic test
- Transport-agnostic: Slack/Discord/web UI da aynı callback data formatını kullanabilir

## Acceptance
- [x] 8/8 LLTODO lint PASS
- [x] 23 unit test PASS (parse + build + handle + mismatch + wrong-state)
- [x] Lane topology: modül Telegram import etmiyor (module-level test)
- [x] draft_id mismatch güvenlik reject (raise)
- [x] Default OFF (publisher'lara dokunmaz)
