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
---

# Görev: P-001 Master Plan CEO + Eng Review

## Sistem Açıklaması (Claude için)

Sen şu an **LLTODO multi-agent consensus pipeline**'ında çalışıyorsun. Bu sistemde
3 AI agent (Hermes, Claude, Gemini) birlikte çalışıyor. İşleyiş:

```
PLAN → CONSENSUS → IMPLEMENT → ULTRAREVIEW → CROSSTEST
```

Şu an **CONSENSUS fazındasın**. Hermes bir plan yazdı (P-001), senden ve Gemini'den
review bekliyor. 2/3 APPROVE olursa plan uygulamaya geçecek.

**Senin rolün (Claude):** Plan/design review + kod analizi. Güçlü yanların: CEO
stratejisi, engineering derinliği, PR review. Bu görevde CEO + Eng review yapacaksın.

## Ne Yapılacak

1. `LLTODO/plans/P-001-u2algo-wave1-tradingview.md` dosyasını oku
2. Dayandığı dosyaları da oku:
   - `.hermes/plans/2026-06-09_u2algo-master-plan.md`
   - `docs/ceo-product-portfolio-2026-06-09.md`
3. CEO review yap: 12 üründen hangileri gerçekten satar? Scope doğru mu? Eksik ne var?
4. Eng review yap: Mimari olarak uygulanabilir mi? Riskler? Eksik edge case?
5. Review'unu `LLTODO/reviews/R-001-claude.md` dosyasına yaz

## Review Formatı

```markdown
---
review_id: R-001-claude
plan_id: P-001
reviewer: claude
verdict: APPROVE | CHANGES_REQUESTED | REJECT
confidence: 0-10
created: <timestamp>
---

# Review: u2algo Master Plan

## Genel Değerlendirme
<2-3 cümle>

## Bulgular
| # | Konu | Severity | Açıklama | Öneri |
|---|------|---------|---------|-------|
| 1 | ... | HIGH/MEDIUM/LOW | ... | ... |

## Karar
APPROVE — <neden>
CHANGES_REQUESTED — <ne değişmeli, hangi satır>
REJECT — <neden, alternatif öneri>
```

## Consensus Kuralları
- APPROVE: Plan olduğu gibi uygulanabilir
- CHANGES_REQUESTED: Küçük değişikliklerle uygulanabilir (belirt)
- REJECT: Major revizyon gerekir (alternatif öner)

## Bittiğinde
1. `LLTODO/reviews/R-001-claude.md` yaz
2. Bu görevi `LLTODO/tasks/DONE/` altına taşı
3. `LLTODO/reports/claude/2026-06-09-p001-review.md` raporunu yaz
4. Başka görev bekleme — Gemini'nin review'unu ve Hermes'in sonraki adımını bekle
