---
task_id: R-002
assigned_by: hermes
assigned_to: gemini
priority: P1
status: PENDING
skill: vision + analytical review
phase: CONSENSUS
deadline: 2026-06-09T18:00:00+03:00
dependencies: [R-001]
plan_id: P-001
created: 2026-06-09T12:00:00+03:00
---

# Görev: P-001 Master Plan Review (Gemini Perspective)

## Sistem Açıklaması (Gemini için)

Sen şu an **LLTODO multi-agent consensus pipeline**'ında çalışıyorsun. Bu sistemde
3 AI agent (Hermes, Claude, Gemini) birlikte çalışıyor. İşleyiş:

```
PLAN → CONSENSUS → IMPLEMENT → ULTRAREVIEW → CROSSTEST
```

Şu an **CONSENSUS fazındasın**. Hermes bir plan yazdı (P-001), senden ve Claude'dan
review bekliyor. 2/3 APPROVE olursa plan uygulamaya geçecek.

**Senin rolün (Gemini):** Görsel analiz + büyük context değerlendirmesi. Güçlü
yanların: chart/screenshot analizi, geniş context penceresi, farklı perspektif.
Bu görevde planı stratejik ve görsel açıdan review edeceksin.

**ÖNEMLİ:** Claude'un review'unu (R-001) bekleyip OKU, sonra kendi review'unu yaz.
Çünkü Gemini 3. reviewer — ilk 2 reviewer'ın görüşlerini görüp son kararı
veren sensin (tie-breaker rolü).

## Ne Yapılacak

1. `LLTODO/plans/P-001-u2algo-wave1-tradingview.md` dosyasını oku
2. Dayandığı dosyaları da oku:
   - `.hermes/plans/2026-06-09_u2algo-master-plan.md`
   - `docs/ceo-product-portfolio-2026-06-09.md`
3. **Claude'un review'unu bekle ve oku** (`LLTODO/reviews/R-001-claude.md`)
4. Şu açılardan değerlendir:
   - Pazar perspektifi: Bu ürünler gerçekten tutar mı? Hangi sırayla çıkmalı?
   - Görsel/içerik perspektifi: TradingView indikatörü görsel olarak yeterli mi?
   - Risk perspektifi: Hermes ve Claude'un görmediği riskler var mı?
   - Kullanıcı perspektifi: Son kullanıcı ne düşünür?
5. Review'unu `LLTODO/reviews/R-002-gemini.md` dosyasına yaz

## Review Formatı

```markdown
---
review_id: R-002-gemini
plan_id: P-001
reviewer: gemini
verdict: APPROVE | CHANGES_REQUESTED | REJECT
confidence: 0-10
prior_reviews_read: [R-001-claude]
created: <timestamp>
---

# Review: u2algo Master Plan (Gemini Perspective)

## Genel Değerlendirme
<2-3 cümle — Hermes ve Claude'dan farklı ne görüyorsun?>

## Hermes + Claude ile Hemfikir Olduklarım
| Konu | Hermes | Claude | Ben |
|------|--------|--------|-----|
| ... | ✅ | ✅ | ✅ |

## Sadece Benim Gördüklerim (Unique Gemini Perspective)
| # | Konu | Severity | Açıklama | Öneri |
|---|------|---------|---------|-------|
| 1 | ... | HIGH | ... | ... |

## Tie-Breaker (Claude ile Hermes ayrışırsa)
<Claude APPROVE ama Hermes emin değilse senin kararın ne?>

## Karar
APPROVE | CHANGES_REQUESTED | REJECT
```

## Consensus Kuralları
- APPROVE: Plan uygulanabilir. Hermes ve Claude hemfikirse sen de onayla.
- CHANGES_REQUESTED: Küçük değişikliklerle uygulanabilir.
- REJECT: Major sorun var. Ama önce Claude'un review'unu gör.

## Bittiğinde
1. `LLTODO/reviews/R-002-gemini.md` yaz
2. Bu görevi `LLTODO/tasks/DONE/` altına taşı
3. `LLTODO/reports/gemini/2026-06-09-p001-review.md` raporunu yaz
4. Eğer 2/3 APPROVE olduysa → CONSENSUS_REACHED → Hermes implementasyona başlayacak
