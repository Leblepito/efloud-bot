---
task_id: T-002
assigned_by: hermes
assigned_to: claude
priority: P1
status: PENDING
skill: plan-ceo-review → plan-eng-review
deadline: 2026-06-09T18:00:00+03:00
dependencies: []
created: 2026-06-09T11:00:00+03:00
---

# Görev: Master Plan CEO + Eng Review

## Ne Yapılacak
Hermes'in hazırladığı master planı oku ve CEO + Engineering review yap.
Plan: `.hermes/plans/2026-06-09_u2algo-master-plan.md`
CEO portföy: `docs/ceo-product-portfolio-2026-06-09.md`

## Skill Pipeline
1. `.hermes/plans/2026-06-09_u2algo-master-plan.md` dosyasını oku
2. `docs/ceo-product-portfolio-2026-06-09.md` dosyasını oku
3. CEO review yap: 12 üründen hangileri gerçekten satar? Scope doğru mu? Eksik ne var?
4. Eng review yap: Mimari olarak uygulanabilir mi? Riskler nerede?

## Çıktı
- `LLTODO/reports/claude/2026-06-09-ceo-eng-review.md` — review raporu
- Varsa düzeltme önerileri (Hermes'e yeni görev olarak)

## Bittiğinde
1. Bu dosyayı `LLTODO/tasks/DONE/` altına taşı
2. `LLTODO/reports/claude/2026-06-09-ceo-eng-review.md` raporunu yaz
3. Hermes için varsa düzeltme görevi oluştur
4. Gemini için T-003'ü review et (dependency chain)
