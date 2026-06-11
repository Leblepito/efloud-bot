# T-023: CI Hardening — Secret Scan + Frontend Build + LLTODO Lint

**Epic:** P-003
**Claimed by:** — (henüz claim edilmedi)
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
