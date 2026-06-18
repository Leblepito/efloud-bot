# T-028 — P-002 M6 second half: Tier-2 Content Renderers

Epic: P-002
Claimed by: @hermes
branch: feat/p002-m6-templates + merged feat/p002-m6-content-queue (T-027 dependency)
claimed_at: 2026-06-19T16:30:00Z
status: IN_PROGRESS

## Goal
M6 ikinci yarısı — `scripts/content_templates/templates.yaml` → render → pre-gate →
T-027 queue'ya enqueue köprüsü. Operatör mimari kararı: research lane (backend/social/)
publish lane'den (scripts/lane_e/) ayrı; renderer bridge.

## Scope (this PR)
- `backend/social/tier2_renderers.py` — load + render + pre_gate + enqueue
- `backend/tests/test_tier2_renderers.py` — 26 hermetic unit test
- `docs/runbooks/tier2-renderers.md` — operatör runbook
- `feat/p002-m6-content-queue` merge (T-027 dependency)

## Out of scope (deferred)
- Telegram inline approve/reject hook (sonraki sprint)
- xurl/Manus publisher wiring (T-026 + T-025 merge sonrası, lane_e içinde)
- M2 chart-export consumer (operatör M2 deliverable)

## Acceptance
- [x] 8/8 LLTODO lint PASS (placeholder bookkeeping)
- [x] ≥12 unit test PASS (achieved 26)
- [x] Gate live (negative control 4/4 PASS)
- [x] Lane topology: renderer publish lane'e dokunmuyor (module-level test)
- [x] Default flags OFF (renderer publish yapmaz, sadece enqueue)

## Risk
- **Düşük.** Sadece yeni modül + test + runbook. Mevcut bot akışına dokunmuyor.
- Gate bağımlılığı: `scripts.content_compliance.find_violations` lazy import —
  gate evolüsyonunda (PR #226 CMP-3/CMP-5) otomatik adapte olur.

## Blocked-by
- T-027 push (master'a merge bookkeeping)
- M2 chart-export URL consumer (M2 deliverable)
