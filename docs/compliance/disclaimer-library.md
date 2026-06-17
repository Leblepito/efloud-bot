# CMP-1 — Bilingual Disclaimer Library (+ live-string reconcile)

| Field | Value |
|---|---|
| Task | CMP-1 (gates CMP-5 wiring, CON copy, has_disclaimer integrity) |
| Owner | @claude |
| Status | v1 2026-06-17 |
| Spec | §4.5 CMP-1 |

## 0. Canonical byte-anchors (DO NOT edit — `has_disclaimer` matches these)

`scripts/content_compliance.has_disclaimer()` byte-matches the constants in `engine/content_jobs.py`:

```
COMPLIANCE_TR = "Bu yatırım tavsiyesi değildir. Trade kendi riskinizdir."
COMPLIANCE_EN = "Not investment advice. Trade at your own risk."
```

**Reconcile decision (resolves the verified live drift):** the live pages use a *shorter* form ("Yatırım tavsiyesi değildir") that does **NOT** byte-match `COMPLIANCE_TR`, so `has_disclaimer('tr')` returns False on every live page today. Fix direction = **embed the exact constant string in each page's disclaimer block** (keep the human-friendly longer prose too). Do **NOT** widen/relax `has_disclaimer()` — CMP-3 leaves it untouched; the gate stays strict and we make the content conform. CMP-5 (Hermes) applies this to live HTML; an end-to-end test asserts `has_disclaimer(page_text, lang) == True` per surface.

Rule per surface language:
- TR page/asset → must contain `COMPLIANCE_TR` verbatim.
- EN page/asset → must contain `COMPLIANCE_EN` verbatim. (EN-first assets use `lang='en'`, never `'both'`.)
- Bilingual page → may contain both.

## 1. Disclaimer blocks (6 × EN/TR × long / short / social)

### B1 — Not financial advice (NFA) — carries the canonical anchor
- **EN long:** "u2algo is an educational decision-support / charting tool. Not investment advice. Trade at your own risk."
- **EN short:** "Not investment advice. Trade at your own risk."
- **EN social (≤120):** "Educational tool. Not investment advice. Trade at your own risk. DYOR."
- **TR long:** "u2algo bir eğitim/karar-destek ve analiz aracıdır. Bu yatırım tavsiyesi değildir. Trade kendi riskinizdir."
- **TR short:** "Bu yatırım tavsiyesi değildir. Trade kendi riskinizdir."
- **TR social (≤120):** "Eğitim aracı. Bu yatırım tavsiyesi değildir. Trade kendi riskinizdir. DYOR."

### B2 — Risk warning (capital at risk)
- **EN:** "Trading carries a high level of risk to your capital. Only trade with money you can afford to lose."
- **TR:** "Trade, sermayeniz için yüksek risk taşır. Yalnızca kaybetmeyi göze alabileceğiniz parayla işlem yapın."

### B3 — Past performance
- **EN:** "Past performance does not guarantee future results."
- **TR:** "Geçmiş performans gelecekteki sonuçların garantisi değildir."

### B4 — Simulation / backtest labeling
- **EN:** "[BACKTEST] Results shown are simulated / hypothetical, not live trading."
- **TR:** "[BACKTEST] Gösterilen sonuçlar simülasyon/hipotetiktir, canlı işlem değildir."

### B5 — Proof ≠ Product (the research-log frame, §2.1b)
- **EN:** "The performance snapshot reflects a naive single-config auto-bot research log — NOT the indicator and NOT a return promise. Values are normalized to %, no absolute balances; negative results are shown as-is."
- **TR:** "Performans anlık görüntüsü, naif tek-config bir oto-bot araştırma günlüğüdür — indikatörün kendisi veya bir getiri vaadi DEĞİLDİR. Değerler %'ye normalize edilmiştir, mutlak bakiye yoktur; negatif sonuçlar olduğu gibi gösterilir."

### B6 — Jurisdiction / licensing
- **EN:** "u2algo is operated by a Turkish joint-stock company (A.Ş.). We are not a licensed broker, investment advisor, or fund. No solicitation to invest."
- **TR:** "u2algo bir Türk Anonim Şirketi (A.Ş.) tarafından işletilir. Lisanslı aracı kurum, yatırım danışmanı veya fon değiliz. Yatırıma çağrı yoktur."

## 2. Surface → required blocks
| Surface | Required |
|---|---|
| Landing (index) footer | B1(anchor) + B2 + B6 |
| premium.html | B1(anchor) + B2 + B3 + B5 + B6 |
| quickstart.html | B1(anchor) + B2 |
| Proof block | B5 + B4(if sim) |
| Video (CON) | B1 short (EN, `lang='en'`) on-screen + spoken |
| Social post | B1 social + (B4 if backtest shown) |
| Email (Resend) | B1 + B6 footer |
| Google Ads US landing (parked) | + CFTC 4.41 (see ADS-0) |

## 3. Sub-processors (feeds CMP-6 KVKK/GDPR map)
Manus.im (automation/SEO, data residency TBD), Higgsfield (media gen, US), GA4 (US — consent-gated), Plausible (EU, cookieless), Resend (email), Supabase (`kjaicqpqfwnfbioofdib`, ap-southeast-1), Lemon Squeezy (payments, MoR). CMP-6 enumerates cross-border + retention.

## Acceptance (CMP-1)
- [x] 6 blocks × EN/TR × long/short/social.
- [x] Canonical anchor strings byte-match `COMPLIANCE_TR/EN`; `has_disclaimer` untouched.
- [x] Live-drift reconcile decision = embed constant (CMP-5 applies + render-parity test).
- [x] Sub-processor list handed to CMP-6.
