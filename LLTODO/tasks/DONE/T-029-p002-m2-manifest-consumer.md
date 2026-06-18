# T-029 — P-002 M2: Chart-Export Manifest Consumer (VPS-side)

Epic: P-002
Claimed by: @hermes
branch: feat/p002-m6-templates (renderer PR'a merge edilecek)
claimed_at: 2026-06-19T18:30:00Z
status: DONE (push bekliyor, feat/p002-m6-templates HEAD'inde)

## Goal
M2 chart-export consumer — operatör-lokal manifest'leri VPS'te oku, validate et,
(symbol, tf) → image_url index'i kur, tier-2 renderer'a resolver olarak besle.

## Scope
- `backend/social/tv_manifest.py` — ChartSnapshot dataclass + ManifestIndex + loader
- `backend/tests/test_tv_manifest.py` — 26 hermetic test
- `backend/social/tier2_renderers.py` — `chart_img_resolver` DI parametresi
- `backend/tests/test_tier2_renderers.py` — 5 yeni integration test (auto-resolve)
- `docs/runbooks/tv-manifest-consumer.md` — operatör runbook
- `scripts/release.sh` step-7 VPS read-only push fix (side-effect)
- Skill `branch-release` — VPS read-only push fix (side-effect)

## Out of scope (deferred)
- Üretim script'i (operatör-lokal, TV/CDP-bound, Hermes test edemez)
- Schema gate (üretim tarafında validation, sonraki PR)
- Multi-source merge (şu an tek üretici varsayımı)

## Acceptance
- [x] 8/8 LLTODO lint PASS
- [x] 26 unit test PASS (manifest consumer)
- [x] 5 integration test PASS (renderer ↔ manifest)
- [x] 0 compliance regression (var olan davranış korundu)
- [x] Push helper VPS-side push çağrısı içermez (read-only sınır)

## Not
Operatör M2 deliverable'ı (BTC 15m K2GRzo5K + ETH 1h 7ZhYCXAH) schema'ya
uygun. Bu PR consumer tarafını hazırlıyor — gerçek üretim operatörün lokal
script'inde kalır.
