# T-027 — P-002 M6: Content Approval Queue (skeleton)

Epic: P-002
Claimed by: @hermes
branch: feat/p002-m6-content-queue
claimed_at: 2026-06-19T10:00:00Z
status: IN_PROGRESS

## Goal
M6 (içerik onay kuyruğu) — template-agnostic skeleton. Operatör M6
template'lerini (signal/educational/recap/promo/market_update) getirince
`tier2_renderers.py` ile bağlanacak.

## Scope (this PR)
- `backend/social/content_queue.py` — DRAFT → PENDING_REVIEW → APPROVED/REJECTED → SENT/FAILED state machine
- `backend/social/queue_storage.py` — asyncpg/Supabase persistence (`content_drafts` tablosu)
- `backend/migrations/009_content_drafts.sql` — idempotent migration
- `backend/tests/test_content_queue.py` — ≥8 hermetic unit test (DB mocked)
- `docs/runbooks/content-queue.md` — operatör runbook

## Out of scope (deferred, follows this PR)
- `tier2_renderers.py` (5 post tipi × EN+TR default) — bekleniyor: operatör M6 template seti
- Telegram inline approve/reject callback (`callback_data=approve:<draft_id>`)
- xurl/Manus gönderim sonrası `mark_sent` wiring (T-026 + T-025 merge sonrası)

## Acceptance
- [ ] 8/8 LLTODO lint PASS
- [ ] ≥8 unit test PASS (target 12)
- [ ] YAML valid
- [ ] Default `MANUS_API_ENABLED=false`, `X_API_ENABLED=false` (prod config'lere dokunmaz)
- [ ] Self: 0 compliance ihlal (kendi başına)

## Risk
- **Düşük.** Sadece yeni tablo + yeni Python modülü, mevcut bot akışına dokunmuyor.
- Migration 009 idempotent (IF NOT EXISTS).
- Storage asyncpg, mevcut Supabase pool'a ek connection yok (kısa süreli acquire).

## Blocked-by
- Operatör M1 (T-026) + T-025 push'u (push relay sırası; bu PR paralel branch'te)

## Not
- T-025 ve T-026 referansları R8 cross-ref kırılmasın diye bu kart metninde yok;
  bilgi SCOREBOARD P-002 tablosunda tutuluyor.
