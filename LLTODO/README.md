# LLTODO — Multi-Agent Consensus Pipeline

> **Kural:** Bu projeye giren HER AI agent (Claude, Hermes, Gemini, Codex, Manus)
> önce bu dosyayı okur, sonra kendine atanmış görevleri `tasks/PENDING/`'de arar.

---

## Dizin Yapısı

```
LLTODO/
├── README.md              ← BU DOSYA (tüm agent'lar önce bunu okur)
├── plans/                 ← Plan dokümanları (P-XXX.md)
├── reviews/               ← Review dokümanları (R-XXX-{agent}.md)
├── tasks/
│   ├── PENDING/           ← Henüz başlanmamış görevler
│   ├── IN_PROGRESS/       ← Şu an çalışılan görevler
│   └── DONE/              ← Tamamlanmış görevler
├── tests/                 ← Cross-test raporları
└── reports/
    ├── hermes/            ← Hermes'in oturum raporları
    ├── claude/            ← Claude'un oturum raporları
    └── gemini/            ← Gemini'nin oturum raporları
```

---

## 🔄 5-Faz Consensus Pipeline

Her büyük iş (yeni ürün, feature, refactor) bu 5 fazdan geçer:

```
PLAN ──→ CONSENSUS ──→ IMPLEMENT ──→ ULTRAREVIEW ──→ CROSSTEST
  │          │              │               │               │
  │    2/3 onay        görevler       Claude Code      agent'lar
  │    gerekli         dağıtılır      final review     birbirini
  │                                     + fix          test eder
```

---

## FAZ 1: PLAN (Tek Agent Başlatır)

Plan yazacak agent (genelde Hermes veya Claude):

1. `LLTODO/plans/P-XXX-<slug>.md` dosyasını oluştur
2. Plan içeriği: ne yapılacak, neden, nasıl, hangi skill'ler, kaç task
3. Diğer 2 agent için review görevi oluştur (`tasks/PENDING/R-XXX-{agent}.md`)

**Plan formatı:**

```markdown
---
plan_id: P-XXX
author: <hangi agent yazdı>
status: AWAITING_REVIEW
created: 2026-06-09T12:00:00+03:00
reviewers: [claude, gemini]
approvals_needed: 2
approvals_received: 0
---

# Plan: <başlık>

## Amaç
<1-2 cümle>

## Kapsam
<ne yapılacak, ne yapılmayacak>

## Task'lar
| ID | Görev | Agent | Tahmini Süre |
|----|-------|-------|-------------|
| T-XXX | ... | hermes | 30dk |
| T-YYY | ... | claude | 15dk |

## Skill Pipeline
1. `skill_view(name='...')` → ...
2. ...

## Riskler
- ...
```

---

## FAZ 2: CONSENSUS (3 Agent Teyitleşir)

Her reviewer agent:

1. Plan dosyasını oku (`LLTODO/plans/P-XXX.md`)
2. Varsa diğer reviewer'ın review'unu da oku
3. `LLTODO/reviews/R-XXX-{agent}.md` yaz
4. Karar: `APPROVE` | `CHANGES_REQUESTED` | `REJECT`

**Review formatı:**

```markdown
---
review_id: R-XXX-claude
plan_id: P-XXX
reviewer: claude
verdict: APPROVE | CHANGES_REQUESTED | REJECT
confidence: 0-10
created: 2026-06-09T13:00:00+03:00
---

# Review: <plan başlığı>

## Genel Değerlendirme
<2-3 cümle>

## Bulgular
| # | Konu | Severity | Açıklama | Öneri |
|---|------|---------|---------|-------|
| 1 | Scope | HIGH | ... | ... |

## Karar
APPROVE — <neden>
CHANGES_REQUESTED — <ne değişmeli>
REJECT — <neden, alternatif öneri>
```

**Consensus kuralları:**
- 2/3 `APPROVE` → **CONSENSUS_REACHED** → Faz 3'e geç
- 1/3 `APPROVE` + 2 `CHANGES_REQUESTED` → Plan yazarı düzeltme yapar, tekrar review
- Herhangi biri `REJECT` → Plan yazarı major revizyon yapar, sıfırdan review
- 3/3 `APPROVE` → **STRONG_CONSENSUS** → direkt implementasyon

---

## FAZ 3: IMPLEMENT (Görevler Dağıtılır)

Consensus sağlandıktan sonra plan yazarı:

1. Plandaki her task için `LLTODO/tasks/PENDING/T-XXX-{agent}-{iş}.md` oluştur
2. Her agent SADECE kendine atanan görevi yapar
3. Görev bittiğinde `DONE/` altına taşır, rapor yazar
4. Başka agent'ın görevine KARIŞMAZ

---

## FAZ 4: ULTRAREVIEW (Claude Code Final Check)

Tüm implementasyon görevleri DONE olduğunda:

1. Claude Code TÜM DONE görevlerini ve raporlarını okur
2. Kapsamlı final review yapar:
   - Eksik kalan iş var mı?
   - Yanlış yapılan bir şey var mı?
   - Task'lar arası tutarsızlık var mı?
   - Plan'dan sapan bir implementasyon var mı?
3. Varsa fix görevleri oluşturur (`tasks/PENDING/FIX-XXX-{agent}.md`)
4. Fix'ler de aynı implementasyon kurallarıyla yapılır

**UltraReview formatı:**

```markdown
---
ultrareview_id: UR-XXX
reviewer: claude
plan_id: P-XXX
status: PASS | FIXES_NEEDED
created: 2026-06-09T15:00:00+03:00
---

# UltraReview: <plan başlığı>

## Tamamlanan İşler (DONE)
| Task | Agent | Doğru mu? | Not |
|------|-------|----------|-----|
| T-001 | hermes | ✅ | ... |

## Eksik / Yanlış İşler (FIX)
| # | Task | Agent | Sorun | Fix Görevi |
|---|------|-------|-------|-----------|
| 1 | T-003 | gemini | ... | FIX-001 |

## Genel Değerlendirme
PASS — tüm işler doğru ve eksiksiz
FIXES_NEEDED — yukarıdaki fix'ler yapılmalı
```

---

## FAZ 5: CROSSTEST (Agent'lar Birbirini Test Eder)

UltraReview PASS olduktan sonra:

1. Her agent BAŞKA BİR agent'ın yaptığı işi test eder
2. Test planı: `LLTODO/tests/TEST-XXX-{tester}-tests-{testee}.md`
3. Test eden agent karar verir: `PASS` | `BUGS_FOUND`
4. BUGS_FOUND varsa → fix görevi → tekrar test → tekrar consensus

**Cross-test eşleşmesi (3 agent için rotasyon):**
```
hermes → claude'un işini test eder
claude → gemini'nin işini test eder
gemini → hermes'in işini test eder
```

**Test formatı:**

```markdown
---
test_id: TEST-XXX-hermes-tests-claude
plan_id: P-XXX
tester: hermes
testee: claude
verdict: PASS | BUGS_FOUND
created: 2026-06-09T16:00:00+03:00
---

# Cross-Test: hermes → claude

## Test Edilen Görevler
| Task | Açıklama | Test Sonucu |
|------|---------|------------|
| T-002 | ... | ✅ PASS |

## Bulunan Hatalar
| # | Task | Hata | Severity | Fix Önerisi |
|---|------|------|---------|------------|
| 1 | ... | ... | MEDIUM | ... |

## Karar
PASS — tüm testler başarılı
BUGS_FOUND — yukarıdaki hatalar düzeltilmeli
```

---

## Görev Formatı (Değişmedi)

```markdown
---
task_id: T-XXX
assigned_by: <hangi agent atadı>
assigned_to: <hangi agent yapacak>
priority: P1 | P2 | P3
status: PENDING | IN_PROGRESS | DONE
skill: <kullanılacak skill>
phase: PLAN | CONSENSUS | IMPLEMENT | ULTRAREVIEW | CROSSTEST
deadline: <ISO timestamp veya "after:T-YYY">
dependencies: [T-XXX, T-YYY]
plan_id: P-XXX
created: 2026-06-09T12:00:00+03:00
---

# Görev: <başlık>

## Ne Yapılacak
<net, spesifik talimat. Agent sadece bunu yapar, başka şey yapmaz.>

## Skill Pipeline
1. `skill_view(name='...')` — skill'i yükle
2. <adım adım ne yapılacağı>

## Çıktı
<ne üretilecek: dosya, PR, deploy, rapor>

## Bittiğinde
1. Bu dosyayı `LLTODO/tasks/DONE/` altına taşı
2. `LLTODO/reports/<agent>/YYYY-MM-DD-<özet>.md` raporunu yaz
3. Varsa yeni görevler oluştur
```

---

## Altın Kurallar

1. **SADECE sana atanmış görevleri yap.** `assigned_to` sen değilsen dokunma.
2. **Plan'lar CONSENSUS olmadan implemente edilmez.** 2/3 APPROVE şart.
3. **Her görev sonunda rapor yaz.** `reports/<agent>/` altına.
4. **Başka agent'ın görevini override etme.**
5. **Cross-test'te kendi işini test etme.** Rotasyonu takip et.
6. **UltraReview'de bulunan fix'ler önceliklidir.** FIX-XXX > T-XXX.
7. **Her fazın kendi ID prefix'i var:**
   - P-XXX = Plan
   - R-XXX = Review
   - T-XXX = Task
   - FIX-XXX = UltraReview fix
   - UR-XXX = UltraReview raporu
   - TEST-XXX = Cross-test

---

## Agent Tanımları

| Agent | Güçlü Olduğu Alan | Zayıf Olduğu Alan | Consensus Rolü |
|-------|------------------|-------------------|---------------|
| **hermes** | Kod, plan, terminal, deploy | Browser, görsel test | Plan Author + Implementer |
| **claude** | Review, kod analizi, PR | Terminal/execution | Reviewer + UltraReviewer |
| **gemini** | Görsel analiz, büyük context | Terminal, kod yazma | Reviewer + Görsel Test |
| **manus** | Browser automation, QA | Lokal dosya | QA + Browser Test |
| **codex** | Second opinion, challenge | Deployment | Optional 4th reviewer |

---

## Aktif Planlar

| Plan | Başlık | Yazar | Durum |
|------|--------|-------|-------|
| P-001 | u2algo Master Plan (Wave 1-4) | hermes | AWAITING_REVIEW |
