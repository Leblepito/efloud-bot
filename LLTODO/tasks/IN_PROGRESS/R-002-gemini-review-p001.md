---
task_id: R-002
assigned_by: hermes
assigned_to: gemini
priority: P1
status: IN_PROGRESS
skill: vision + analytical review
phase: CONSENSUS
deadline: 2026-06-09T18:00:00+03:00
dependencies: [R-001]
plan_id: P-001
created: 2026-06-09T12:00:00+03:00
claimed_by: gemini
claimed_at: 2026-06-09T20:15:00+07:00
---

# Görev: P-001 Master Plan Review (Gemini Perspective)

## Ne Yapılacak
Claude'un R-001 inceleme raporunu okuduktan sonra, P-001 planını kendi uzmanlık alanına göre (pazar ve görsel açıdan) incele, tie-breaker kararını vererek onay durumunu (`APPROVE | CHANGES_REQUESTED | REJECT`) yaz.

## Skill / Tool Adımları
1. `LLTODO/plans/P-001-u2algo-wave1-tradingview.md` planını ve dayandığı dosyaları oku.
2. Claude'un yazdığı `LLTODO/reviews/R-001-claude.md` incelemesini oku.
3. Şu açılardan değerlendir:
   - Pazar perspektifi: Bu ürünlerin sırası ve potansiyeli nedir?
   - Görsel perspektif: TradingView indikatör görselleştirmeleri yeterli mi?
   - Tie-breaker: Claude ile Hermes arasında uyuşmazlık olursa nihai kararınız.
4. Review sonucunu `LLTODO/reviews/R-002-gemini.md` dosyasına yaz.

## Çıktılar
- `LLTODO/reviews/R-002-gemini.md` (Konsensüs Review raporu)

## Kapanış Kontratı (Done Criteria)
1. Bu görevi `LLTODO/tasks/DONE/` altına taşı.
2. `LLTODO/reports/gemini/2026-06-09-p001-review.md` raporunu yaz.
3. `LLTODO/STATE.md` dosyasını güncelle.
