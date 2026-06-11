# T-023: CI Hardening — Secret Scan + Frontend Build + LLTODO Lint

**Epic:** P-003
**Claimed by:** @claude (2026-06-11, pre-UR-exempt — claim akışı bypass edildi, R-003 nice-to-have'de kayıtlı)
**Tahmini süre:** 1 gün
**Bağımlılık:** — ; **pre-UR-exempt** (CI-only, trade-path riski sıfır). P-002 M1-M4'ü G5 gate'i üzerinden BLOKLUYOR — önce bu.

## Hedef

CI'daki üç boşluğu kapatmak: (1) secret scanning yok — yeni ödeme/sosyal anahtarları çağında commit kazaları yakalanmalı; (2) frontend build CI'da doğrulanmıyor (yalnız Docker'da); (3) `lltodo_lint.py` CI'da canlı ağaca koşmuyor (naming/xref disiplini manuel).

## Çıktılar

- [ ] `.github/workflows/ci.yml`'e **gitleaks** job'ı (push+PR)
- [ ] Frontend job: `npm ci && npm run typecheck && npm run test && npm run build` (frontend/)
- [ ] LLTODO lint adımı: `python LLTODO/scripts/lltodo_lint.py` canlı ağaçta
- [ ] `LLTODO/scripts/lltodo_lint.py:143` — artık gereksiz `"P-002"` whitelist girdisini kaldır (P-002 plan dosyası mevcut; whitelist typo'ları maskeliyor)

## Acceptance Kriterleri

- [ ] Üç job da mevcut PR'larda yeşil; sahte-pozitif secret bulgusu yok (gerekirse `.gitleaksignore`)
- [ ] P-002 G5 gate'i ("secret-scan yeşil") otomatik doğrulanabilir hale gelir

## Log

| Zaman | Durum | Not |
|---|---|---|
| 2026-06-11 | BACKLOG | P-003 W-R — pre-UR-exempt, M1-M4 blokeri |
| 2026-06-11 | IMPL | @claude PR #182 (`feat/t023-ci-hardening`): 3 CI job + gitleaks triage (5/5 false-positive, gerçek secret YOK — doc placeholder fix + 4 fingerprint .gitleaksignore) |
| 2026-06-11 | ✅ DONE | PR #182 → master `63b9872`, CI 4/4 yeşil. P-002 G5 gate'i artık otomatik. KALAN follow-up'lardan whitelist temizliği + R2-per-agent PR #186'da yapıldı (2026-06-11); R1 vakum fix + R6/R7 genişletme hâlâ açık (R-003 nice-to-have) |
