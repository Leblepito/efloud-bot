---
review_id: R-001-claude
plan_id: P-001
reviewer: claude
verdict: CHANGES_REQUESTED
confidence: 7
prior_reviews_read: []
created: 2026-06-09T15:30:00+03:00
proxy: false
proxy_by: null
proxy_engine: null
provisional: false
---

# Review: u2algo Master Plan — 12 Ürün, 4 Wave (P-001)

## Genel Değerlendirme
Stratejik yön sağlam ve **Wave-1 (TradingView indikatör publish) derhal GO** — gerçek bir production varlığını (452 satır derlenmiş Pine v6) sıfır altyapı maliyetiyle 50M+ kullanıcılı bir kanala sokuyor; funnel mantığı (free → $29 → $99) ve skill pipeline disiplini doğru. Ancak plan bir **master/strateji roadmap**'i; bir feature spec'i değil. Şu haliyle 12 ürünün tamamına "scope" olarak commit ediyor ve birkaç önemli boşluk taşıyor: müşteri-edinme motoru yok, scope tutarsız (destek dokümanı "5 ürün" diyor, P-001/portföy "12"), ve ücretli API'ler için ortak productization altyapısı (auth/billing/tenancy) adlandırılmamış. Wave-1 onaylanmalı; gerisi traction-gate'li ayrı plana bölünmeli.

## Bulgular
| # | Konu | Severity | Açıklama | Öneri |
|---|------|----------|----------|-------|
| 1 | Scope tutarsızlığı | HIGH | `.hermes/plans/2026-06-09_u2algo-master-plan.md` Goal'ü **"5 satılabilir ürün"** der; P-001 ve CEO portföyü **12 ürün**. Hangisi taahhüt? | Tek sayıya hizala. Öneri: P-001 yalnız **Wave-1**'i taahhüt etsin; Wave 2-4 roadmap (ayrı plan). |
| 2 | Müşteri edinme motoru yok | HIGH | $14K MRR ~225 ödeyen müşteri demek (50 TV + 40 sinyal + 100 veri + 5 audit + 30 backtest), sıfırdan 3 ayda. Plan ürünleri listeliyor ama **dağıtım/funnel/kanal/CAC** yok ("build it and they will come" riski). | Her wave'e somut **edinme kanalı + GO/NO-GO gelir gate'i** ekle (zaman değil, müşteri/gelir tetikli). |
| 3 | Productization altyapısı eksik | MEDIUM | "REST API'ye sarmala" (backtest/veri/agent-team) auth, rate-limit, billing, multi-tenancy, abuse koruması, SLA gerektirir — hiçbiri scope'ta. 1-2 haftalık tahminler bu yüzden ~2-3× iyimser. | Wave-2 öncesi **tek seferlik ortak "productization platform"** (auth+billing+tenancy+observability) task'ı ekle. |
| 4 | Canlı bot ile altyapı bağlaşımı | MEDIUM | Birden çok ürün canlı bot/veri/engine altyapısını paylaşıyor. Ürün kesintisi/yükü **canlı trading'i (mücevher) tehlikeye atabilir**. | Ürün altyapısını canlı trading bot'undan **izole et** (ayrı servis/kaynak). |
| 5 | Yasal/lisans riskleri | MEDIUM | (a) Binance türevli OHLCV'yi yeniden satmak Binance veri redistribütör şartlarını ihlal edebilir; (b) sinyal/audit satışı finansal-promosyon düzenlemelerine tabi olabilir; (c) canlı sinyal sızıntısı edge'i aşındırır. Risk tablosunda yok. | Veri lisansı + finansal-promosyon (jurisdiction) + sinyal-gecikme/karartma stratejisini risk tablosuna ekle. |
| 6 | Gelir projeksiyonu iyimser | LOW | Tablo dönüşüm oranı, churn, ramp süresi varsaymıyor; hepsi peak doluluk. | Konservatif/baz/iyimser 3 senaryo + ramp eğrisi ekle. |

## Dağıtım Adil mi? (teyit-2)
**APPROVE.** Dağıtım SCOREBOARD uzmanlıklarıyla tutarlı: T-001 publish→hermes (implementation+deploy), T-002 review→claude (review/kod-analizi), T-003 Pine görsel→gemini (visual-verification), UR-001→claude (UltraReview sürücüsü). İlk epic olduğu için statik uzmanlığa dayanması da uygun. İtirazım yok.

## Karar
**CHANGES_REQUESTED** — Plan stratejik olarak doğru ve **Wave-1 derhal uygulanabilir**, ancak tam 12-ürün taahhüdüne kaynak ayırmadan önce şu küçük-orta düzeltmeler yapılmalı:
1. (#1) 5-vs-12 ürün scope tutarsızlığını çöz; P-001'i Wave-1'e daralt, Wave 2-4'ü traction-gate'li ayrı plan(lar)a taşı.
2. (#2) Her wave'e müşteri-edinme kanalı + somut gelir GO/NO-GO gate'i ekle.
3. (#3) Wave-2 öncesi ortak productization platformu (auth/billing/tenancy) task'ı tanımla.
4. (#4/#5) Ürün altyapısını canlı bottan izole et + veri-lisansı/finansal-promosyon/sinyal-sızıntısı risklerini ekle.

> Not: Bu CHANGES_REQUESTED Wave-1'i **bloklamaz** — TradingView publish (T-001) paralel başlayabilir. Düzeltmeler esas olarak Wave 2-4 taahhüdünü sağlamlaştırmak içindir. Gemini'nin R-002 (pazar + görsel perspektif) tie-breaker'ı bekleniyor.
