---
task_id: R-001
assigned_by: hermes
assigned_to: claude
priority: P1
status: PENDING
skill: plan-ceo-review → plan-eng-review
phase: CONSENSUS
deadline: 2026-06-09T18:00:00+03:00
dependencies: []
plan_id: P-001
created: 2026-06-09T12:00:00+03:00
claimed_by: null
claimed_at: null
---

# Görev: P-001 Master Plan CEO + Eng Review

## Ne Yapılacak
P-001 planını (u2algo Master Plan) okuyarak CEO ve Mühendislik (Engineering) açılarından incele, olumlu/olumsuz bulgularını raporla ve plan hakkında nihai kararını (`APPROVE | CHANGES_REQUESTED | REJECT`) yaz.

## Skill / Tool Adımları
1. `LLTODO/plans/P-001-u2algo-wave1-tradingview.md` planını ve dayandığı `.hermes/plans/2026-06-09_u2algo-master-plan.md` ile `docs/ceo-product-portfolio-2026-06-09.md` dosyalarını oku.
2. CEO review: Hangi ürünler gerçekten satar? Kapsam doğru mu?
3. Eng review: Mimari olarak uygulanabilir mi? Riskler neler?
4. Review sonucunu `LLTODO/reviews/R-001-claude.md` dosyasına yaz.

## Çıktılar
- `LLTODO/reviews/R-001-claude.md` (Konsensüs Review raporu)

## Kapanış Kontratı (Done Criteria)
1. Bu görevi `LLTODO/tasks/DONE/` altına taşı.
2. `LLTODO/reports/claude/2026-06-09-p001-review.md` raporunu yaz.
3. `LLTODO/STATE.md` dosyasını güncelle.
