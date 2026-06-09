# Claude için LLTODO Prompt

> Bu dosyayı Claude Code / Claude.ai session'ına yapıştır.
> Claude'un yapması gereken: P-001 planını CEO + Eng review et.

---

Sen bir AI agent'sın. Şu an **LLTODO multi-agent consensus pipeline**'ın
CONSENSUS fazındasın. Bu projede 3 agent birlikte çalışıyor:

- **hermes**: Plan yazarı + implementer (ben)
- **claude**: Reviewer + UltraReviewer (sen)
- **gemini**: Reviewer + görsel test (3. taraf)

## İşleyiş

```
PLAN → CONSENSUS → IMPLEMENT → ULTRAREVIEW → CROSSTEST
  ↑        ↑
  |     ŞU ANDA BURADASIN
  |
hermes yazdı
```

Hermes (ben) `P-001` planını yazdı. Senden ve Gemini'den review bekliyorum.
**2/3 APPROVE olursa plan uygulamaya geçecek.**

## Senin Görevin

1. **Planı oku:** `LLTODO/plans/P-001-u2algo-wave1-tradingview.md`
2. **Destek dosyalarını oku:**
   - `.hermes/plans/2026-06-09_u2algo-master-plan.md`
   - `docs/ceo-product-portfolio-2026-06-09.md`
   - `LLTODO/README.md` (sistem kuralları)
3. **CEO + Eng review yap:**
   - Bu 12 üründen hangileri GERÇEKTEN satar?
   - Scope doğru mu? Eksik ne var?
   - Mimari olarak uygulanabilir mi?
   - Hangi riskler atlanmış?
4. **Review'unu yaz:** `LLTODO/reviews/R-001-claude.md`

## Review Formatı (bu formatta yaz)

```markdown
---
review_id: R-001-claude
plan_id: P-001
reviewer: claude
verdict: APPROVE | CHANGES_REQUESTED | REJECT
confidence: 0-10
created: 2026-06-09T<saat>:00+03:00
---

# Review: u2algo Master Plan

## Genel Değerlendirme
<2-3 cümle>

## Bulgular
| # | Konu | Severity | Açıklama | Öneri |
|---|------|---------|---------|-------|
| 1 | ... | HIGH/MEDIUM/LOW | ... | ... |

## CEO Perspektifi
<Stratejik değerlendirme: pazar, rekabet, fiyatlandırma, hedef kitle>

## Engineering Perspektifi
<Teknik değerlendirme: mimari, riskler, edge case'ler, bağımlılıklar>

## Karar
APPROVE — plan olduğu gibi uygulanabilir, çünkü...
CHANGES_REQUESTED — şu değişikliklerle uygulanabilir: ...
REJECT — major revizyon gerekir, alternatif öneri: ...
```

## Karar Kriterleri

- **APPROVE**: Plan stratejik olarak doğru, teknik olarak uygulanabilir, riskler yönetilebilir
- **CHANGES_REQUESTED**: Küçük düzeltmelerle onaylanır (belirt hangi satır/değişiklik)
- **REJECT**: Temel bir sorun var (belirt, alternatif öner)

## Bittiğinde

1. Review dosyasını oluştur
2. `LLTODO/tasks/PENDING/R-001-claude-review-p001.md` dosyasını `LLTODO/tasks/DONE/` altına taşı
3. `LLTODO/reports/claude/2026-06-09-p001-review.md` raporunu yaz
4. **Bekle.** Gemini review'unu yapacak, sonra Hermes sonraki adımı belirleyecek.

---

## Bağlam (Background)

efloud-bot: Binance USDT-M futures üzerinde SMC (Smart Money Concepts) stratejisiyle
çalışan canlı trading bot'u. Production'da ~$2000 ile çalışıyor. Kod tabanında 12
satılabilir ürün tespit edildi. İlk ürün TradingView Pine Script v6 indikatörü.

**Proje dosyaları GitHub'da:** `github.com/Leblepito/efloud-bot` (branch: feat/zone-touch-confirmation)
**LLTODO dizini:** `efloud-bot/LLTODO/`
