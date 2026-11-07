---
id: T-20261107-10
title: frontend npm — majör olmayan güvenlik güncellemeleri (next 15.5.29, sharp, postcss, source-map-js)
from: claude-code
to: claude-code
status: in-review
claimed_by: claude-code
reviewer: null
parent: T-20261106-06
created: 2026-11-07
touches_live: false
---

## Amaç
Güvenlik denetimi (T-20261106-06) fix #7. Günlük CI npm audit'i: 11 açık (3 critical, 4 high, 4 moderate).
Frontend `output: "export"` (statik) → prod'da Next sunucusu yok; risk build/dev ortamında.

## Değişiklik (yalnız `package-lock.json`, `npm audit fix --package-lock-only`; package.json aynı)
- next 15.x → **15.5.29** (Next'in kendi advisory'leri — image-opt RCE, ISR cache poisoning, server actions DoS — artık listelenmiyor)
- sharp → 0.35.5, postcss → 8.5.28, postcss-selector-parser → 6.1.5, source-map-js → 1.2.2
- Sonuç: 11 → 8 (kalanlar aşağıda)

## Kalan (bilinçli, ayrı iş)
- **vitest 2 → 5 majör** (tinypool / vite / vite-node / esbuild / @vitest/mocker): yalnız dev/test; kırıcı değişiklik → ayrı task.
- **next'in gömülü postcss 8.4.31'i**: tek düzeltme next 16 majör; yalnız build sırasında kendi CSS'imizi işler (saldırgan girdisi yok) → ayrı task.

## Beklenen çıktı (Definition of Done)
- [x] `npm ci --ignore-scripts` + `typecheck` (0 hata) + `vitest` (5/5) + `next build` (statik export) — CI frontend job'unun 3 adımı yerelde geçti
- [ ] CI

## Log
- 2026-11-07 claude-code: lockfile güncellendi; typecheck/test/build OK.

## Review
<!-- reviewer buraya yazar: VERDICT: APPROVE | CHANGES | REJECT + gerekçe -->
