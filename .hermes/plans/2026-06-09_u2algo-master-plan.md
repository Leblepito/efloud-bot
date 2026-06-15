# u2algo Startup Master Plan — Skill-Driven Development Pipeline

> **Goal:** efloud-bot kod tabanından 5 satılabilir ürün çıkar, 3 ayda $14K MRR hedefine ulaş.
> **Method:** gstack workflow pipeline — her adım skill ile, her rol AI agent ile.
> **Date:** 2026-06-09

---

## Skill Pipeline (Her Aşamada Hangi Skill Çalışacak)

```
FİKİR           → office-hours       (6 forcing question, problem validation)
  ↓
CEO REVIEW      → plan-ceo-review    (strateji, scope, 10-star vizyon)
  ↓
DESIGN REVIEW   → plan-design-review (UX, dashboard, TradingView UI — sadece UI'lı ürünler)
  ↓
ENG REVIEW      → plan-eng-review    (mimari, edge case, test planı)
  ↓
DX REVIEW       → plan-devex-review  (API ergonomisi, TTHW, dokümantasyon)
  ↓
SPEC            → spec               (5-faz executable spec → GitHub issue)
  ↓
IMPLEMENT       → writing-plans      (bite-sized task planı)
  ↓               → subagent-driven-development (task başına subagent + 2-stage review)
  ↓               → test-driven-development    (RED-GREEN-REFACTOR)
  ↓
CODE REVIEW     → review             (pre-landing PR review)
  ↓
SHIP            → ship               (PR aç, CI bekle)
  ↓
DEPLOY          → land-and-deploy    (merge, deploy, production health)
  ↓
MONITOR         → canary             (post-deploy monitoring)
  ↓
RETRO           → retro              (haftalık: ne işe yaradı, ne yaramadı)
```

---

## AI Agent Rolleri (Kim Ne Yapacak)

| Rol | Skill / Araç | Sorumluluk |
|-----|-------------|-----------|
| **CEO** | `office-hours` + `plan-ceo-review` | Strateji, scope, "bu ürün satar mı?" |
| **CTO** | `plan-eng-review` | Mimari, tech stack, edge case'ler |
| **Designer** | `plan-design-review` | Dashboard UX, TradingView UI, landing page |
| **DX Engineer** | `plan-devex-review` | API ergonomisi, onboarding, doküman |
| **Backend Dev** | `writing-plans` + `delegate_task` | API endpoint'leri, servis kodları |
| **Frontend Dev** | `delegate_task` (Next.js) | Dashboard, landing page, TradingView |
| **QA Engineer** | `review` + `investigate` | PR review, bug bulma, regression test |
| **DevOps** | `land-and-deploy` + `canary` | Railway deploy, health check, monitoring |
| **Content** | `delegate_task` (creative) | TradingView kopyası, sosyal medya postları |
| **Community** | `delegate_task` + Telegram | Kullanıcı iletişimi, sinyal dağıtımı |

---

## Ürün Yol Haritası

### 🟢 WAVE 1: Quick Win (Hafta 1-2) — TradingView İndikatörü

**Hedef:** 2 haftada publish, ilk kullanıcılar, sıfır altyapı maliyeti.

| Gün | Adım | Skill | AI Agent | Çıktı |
|-----|------|-------|----------|-------|
| 1 | Fikri validate et | `office-hours` (builder mode) | CEO | Design doc |
| 2 | Strateji review | `plan-ceo-review` | CEO | Scope onayı |
| 3 | SPEC yaz | `spec` | CTO | GitHub issue #1 |
| 4 | Pine Script publish paketi hazırla | `writing-plans` | Backend Dev | Task planı |
| 5 | TradingView publish | `delegate_task` | Frontend Dev | Published script |
| 6 | Açıklama + görsel hazırla | `delegate_task` (creative) | Content | TV description + chart |
| 7 | Landing page CTA ekle | `delegate_task` | Frontend Dev | u2algo.com/tradingview |
| 8 | PR review + merge | `review` → `ship` | QA + DevOps | PR merged |
| 9 | Sosyal medya duyurusu | `delegate_task` | Content | X, IG, TG, YT postları |
| 10 | İlk hafta metrikleri | `retro` | CEO | Kullanıcı sayısı, feedback |

**Skill çağrı sırası (her biri ayrı oturum):**
```
SKILL: office-hours     → "TradingView'de SMC v2 indikatörü yayınlayacağız. Builder mode."
SKILL: plan-ceo-review  → "Bu ürünün 10-star versiyonu ne?"
SKILL: spec             → "TradingView publish için executable spec yaz."
SKILL: writing-plans    → "Publish paketi için implementasyon planı."
SKILL: subagent-driven-development → "Planı task task uygula."
SKILL: review           → "PR'ı review et."
SKILL: ship             → "PR aç ve merge et."
SKILL: retro            → "İlk hafta: ne öğrendik?"
```

---

### 🟢 WAVE 2: Core Services (Hafta 3-6) — Backend Ürünleri

**Hedef:** 3 backend servisi aynı anda develop et (paralel subagent'lar).

| # | Ürün | Skill Pipeline | AI Agent | Süre |
|---|------|---------------|----------|------|
| 2 | **Sinyal Servisi** (Telegram bot) | spec → writing-plans → subagent-driven-dev → review → ship → land-and-deploy | Backend Dev + DevOps + Community | 2 hafta |
| 3 | **OHLCV Veri API** | spec → writing-plans → subagent-driven-dev → review → ship → land-and-deploy | Backend Dev + DevOps | 1 hafta |
| 4 | **Backtest-as-a-Service** | spec → writing-plans → subagent-driven-dev → review → ship → land-and-deploy | Backend Dev + Quant + DevOps | 2 hafta |

**Paralel çalışma modeli:**
```
GÜN 1-3:   Tüm ürünler için paralel spec yaz (3 delegate_task)
GÜN 4-7:   Tüm ürünler için paralel writing-plans (3 delegate_task)
GÜN 8-14:  Paralel implementasyon (her ürün için 1 delegate_task)
GÜN 15-18: Paralel review + ship (her ürün için review → ship)
GÜN 19-21: land-and-deploy + canary (her ürün için)
```

**Skill çağrı sırası (her ürün için aynı pipeline):**
```
SKILL: spec              → "[Ürün adı] için executable spec."
SKILL: writing-plans     → "[Ürün adı] implementasyon planı."
SKILL: subagent-driven-development → "Planı uygula (TDD ile)."
SKILL: review            → "PR review (security + edge cases)."
SKILL: ship              → "PR aç, CI yeşilse merge et."
SKILL: land-and-deploy   → "Railway'e deploy et, health check yap."
SKILL: canary            → "Post-deploy: 24 saat monitoring."
```

---

### 🟡 WAVE 3: Premium Products (Hafta 7-10) — İleri Ürünler

| # | Ürün | Skill Pipeline | AI Agent | Süre |
|---|------|---------------|----------|------|
| 5 | **Strateji Audit** (danışmanlık) | office-hours → spec → plan → implement → ship | CEO + Quant + Backend | 2 hafta |
| 6 | **Multi-Exchange (MT5)** | eng-review → spec → plan → implement → ship | CTO + Backend + QA | 3 hafta |
| 7 | **AI Agent Team API** | eng-review → spec → plan → implement → ship | CTO + Backend | 2 hafta |
| 8 | **Kronos Tahmin** | spec → plan → implement → ship | Backend + ML | 1 hafta |

---

### 🔵 WAVE 4: Platform (Hafta 11-12) — Hepsi Bir Arada

| # | Ürün | Açıklama |
|---|------|---------|
| 9 | **EFloud Platform** | Tüm servisleri tek dashboard'da birleştir |
| 10 | **Safety Framework** | Açık kaynak Python kütüphanesi |
| 11 | **OrderManager OSS** | Enterprise-grade order execution |
| 12 | **Social-to-Strategy** | Araştırma pipeline'ı |

---

## Session Yönetimi

Her çalışma oturumu şu akışla başlar:

```
1. context-restore   → "Geçen oturumda nerede kalmıştık?"
2. Plan/AGENTS.md oku → Mevcut durumu hatırla
3. İlgili skill'i yükle → skill_view(name='...')
4. Skill'i uygula       → Workflow'u takip et
5. context-save         → "Bu oturumda ne yaptık, ne kaldı?"
```

---

## Metrikler & Gate'ler

Her ürün için:
- **Pre-launch gate:** Tests passing + code review approved + security scan clean
- **Post-launch gate (24h):** Health check green + 0 critical errors + canary clean
- **1-week gate:** User count > 0 + 0 crash loops + revenue (varsa)
- **1-month gate:** MRR hedefi vs gerçekleşen

---

## Riskler & Mitigasyon

| Risk | Olasılık | Etki | Mitigasyon |
|------|---------|------|-----------|
| TradingView reject | Düşük | Orta | House Rules önceden kontrol et |
| Railway cold start timeout | Orta | Düşük | Health check retry + uptime monitor |
| Binance API rate limit | Düşük | Yüksek | Rate limiter zaten kodda var |
| Multi-exchange adapter bug | Orta | Yüksek | Önce paper trading, sonra micro lot |
| LLM API outage (Gemini/Claude) | Orta | Düşük | Fail-safe: {} dön, trade'i bloklama |

---

## İlk Aksiyon (Bu Oturum)

Şimdi başlayalım:
1. `context-save` → Bu master planı kaydet
2. `office-hours` → TradingView indikatörü için builder mode
3. `spec` → Executable spec → GitHub issue

Başlayalım mı?
