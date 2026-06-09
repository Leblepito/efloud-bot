---
review_id: R-XXX-{agent}
plan_id: P-XXX
reviewer: hermes | claude | gemini
verdict: APPROVE | CHANGES_REQUESTED | REJECT
confidence: 0-10
prior_reviews_read: []
created: YYYY-MM-DDTHH:MM:SS+03:00
# --- proxy alanları: yalnızca bu bir proxy oy ise doldur (bkz. README §Proxy Oy) ---
proxy: false
proxy_by: null            # proxy'yi üreten agent
proxy_engine: null        # subagent | ollama | <model>
provisional: false
---

# Review: [Plan Başlığı]

## Genel Değerlendirme
[Plana dair genel görüşler]

## Bulgular
| # | Konu | Severity | Açıklama | Öneri |
|---|------|---------|---------|-------|
| 1 | ... | HIGH | ... | ... |

## Dağıtım Adil mi? (ZORUNLU satır)
[Plandaki task→agent dağıtımı SCOREBOARD'a göre gerekçeli mi? Onayla ya da itiraz et — rakam ver.]

## Karar
[APPROVE | CHANGES_REQUESTED | REJECT gerekçesi]
> Not: CONSENSUS için en az 1 GERÇEK (non-author) APPROVE şart; yazar+proxy ile geçmez.
