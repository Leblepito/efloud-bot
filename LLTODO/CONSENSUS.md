# LLTODO Consensus v3 — Plan · Split · Test 3-Ajan Protokolü

> Append-only. Son güncelleme: 2026-06-13 @claude
> Bu dosya, LLTODO'nun consensus (teyitleşme) kurallarını tanımlar. README.md genel
> sistemi; bu dosya **3 ajanın plan/görev-dağıtımı/test üzerinde nasıl teyitleştiğini** anlatır.

## 0. Neden

Üç ajan paralel çalışıyor: `@hermes` (insan operatör + implementor, VPS erişimi),
`@claude` (Claude Code oturumu), `@gemini` (harici Google modeli, operatör prompt taşır).
**Ajanlar arası RPC YOK** — koordinasyon tamamen **git + LLTODO markdown dosyaları +
kopyala-yapıştır prompt** ile yürür. Bu yüzden sistem bir "kara tahta + yokla" (blackboard
+ poll) modelidir; otomatik tetikleme yoktur (bkz. §6).

v2'de yalnızca **plan** review'dan geçiyordu. v3, aynı teyit disiplinini **görev dağıtımına
(SPLIT)** ve **teste (CROSS-TEST)** genişletir. Amaç: hiçbir ajan açıklanmamış bir mantıkla
iş yapmasın — *planın*, *kimin neyi yaptığının* ve *kimin kimi test ettiğinin* hepsi git'te
görünür, onaylı birer artefakt olsun.

## 1. Pipeline

```
PLAN → PLAN-CONSENSUS → SPLIT → IMPLEMENT → ULTRAREVIEW → CROSS-TEST → TEST-CONSENSUS → DONE
```

STATE.md durum kümesi (README ile senkron, lint ile doğrulanır):
`DRAFT → REVIEW_OPEN → CHANGES_REQUESTED → CONSENSUS_REACHED → SPLIT_AGREED →
IN_PROGRESS → ULTRA_REVIEW → CROSS_TEST → TEST_CONSENSUS → DONE`

## 2. Gate 1 — PLAN-CONSENSUS (v2'den, formalize)

1. Yazar `plans/P-XXX-<slug>.md` yazar → durum `DRAFT`.
2. İki reviewer `reviews/R-XXX-<reviewer>-review.md` yazar (template: `templates/review.md`).
   Durum `REVIEW_OPEN`.
3. **Confidence eşiği:** `@claude ≥ 7`, `@gemini ≥ 9` (Gemini daha sıkı). Eşik altı = revizyon iste.
4. **Karar tablosu:**

   | Oylar | Sonuç |
   |---|---|
   | 2/3 APPROVE | `CONSENSUS_REACHED` → SPLIT'e geç |
   | 3/3 APPROVE | STRONG_CONSENSUS → direkt SPLIT |
   | 1 APPROVE + 2 CHANGES_REQUESTED | Yazar düzeltir, tekrar review |
   | Herhangi bir REJECT | Major revizyon, baştan review |

## 3. Gate 2 — SPLIT (yeni)  ⭐ "mantığı açıkla" kuralı

Implementasyondan **önce** plan yazarı `splits/S-XXX-<epic>.md` oluşturur (template:
`templates/split.md`). Bu dosya **her görevi/PR'ı tek bir sahibe** atar ve **mantığını yazar**:

| Görev | owner | tester | Atama gerekçesi (tek cümle) |
|---|---|---|---|
| T-0xx ... | @agent | @agent (≠owner) | neden bu ajan |

Kurallar:
- `tester` **owner'dan farklı** olmak zorunda (kimse kendi işini onaylamaz).
- Diğer iki ajan dosyaya `ACK @agent @ <ts>` satırı ekler (tam review değil, hafif teyit).
- **3/3 ACK** (veya 2/3 ACK + operatör onayı) → durum `SPLIT_AGREED`.
- Bu artefakt, operatörün şikâyetini çözer: *"görevleri hangi mantıkla dağıttığını bilmiyorum"*.
  Artık dağıtım mantığı git'te yazılı ve teyitli.

## 4. IMPLEMENT — sahiplik ve self-only kuralı

- Ajan **yalnızca `owner == kendisi`** olan görevi claim eder (`tasks/IN_PROGRESS/T-XXX-*.md`,
  `Claimed by: @agent @ <ts>`).
- **Self-only kuralı:** Bir ajan, kendisine açıkça atanmamış (veya başkasına atanmış) görevi
  ASLA üstlenmez. Atanmamış işe inisiyatifle girmek yasak. → Zamanla her ajan belli alanlarda
  uzmanlaşır. ("Kendine açıkça talimat verilmeyen görevleri yapma.")
- İş bitince ajan: (a) görevi `tasks/DONE/`'a taşır, (b) **rapor** yazar (§5),
  (c) gerekiyorsa yeni görevleri `tasks/BACKLOG/`'a **owner/tester etiketli** ekler.

## 5. Raporlama + Görev-Atama Kuralı (HER ajan, HER iş birimi)

İş biten her birimde ajan `reports/<agent>/YYYY-MM-DD-<slug>.md` dosyasına ekler:

```
- Ne yapıldı:
- Kullanılan skill/araç:
- Görev ID:
- Sonuç:
- Sıradaki planlanan adım (self-owned BACKLOG task olarak da yaz):
```

Takip görevleri `tasks/BACKLOG/T-XXX-*.md` olarak, açık `owner:` + `reviewer:`/`tester:`
alanlarıyla yazılır. Bir ajan kendine VE diğerlerine görev yazabilir; ama **uygulamayı yalnız
kendi owner'lı görevinde yapar.**

## 6. Self-Scheduling (dürüst sınır)

Ajan, sıradaki adımını self-owned bir BACKLOG görevi olarak kaydeder. **Yeniden tetikleme**
operatör eliyle ya da Claude Code `/loop 5m` skill'i ile olur. **Repo içi cron/RPC YOKTUR**
(scheduling VPS crontab veya `loop` skill'i; bkz. `docs/runbooks/*-cron-setup.md`). Bunu
otomatikmiş gibi göstermeyin — bilinen bir sınırdır.

## 7. Gate 3 — CROSS-TEST + TEST-CONSENSUS (yeni)

IMPLEMENT + ULTRAREVIEW bittikten sonra:
- Her görev, **owner'dan farklı** `tester` ajan tarafından test edilir (SPLIT'teki `tester`).
- Tester `tests/X-XXX-<tester>.md` yazar (template: `templates/crosstest.md`): çalıştırılan
  komutlar + kanıt (çıktı) + **PASS/FAIL**.
- Epic yalnızca **her görevin bağımsız bir CROSS-TEST PASS'ı varsa** `DONE` olur.
- Bir FAIL → owner'a fix-task açılır (geri IMPLEMENT). Test üzerinde anlaşmazlık → üçüncü ajan
  tie-break (aynı 2/3 mantığı).

> **ULTRAREVIEW (@claude):** FAZ sonunda, tüm implementasyon bitince Claude Code adversarial
> `UR-XXX` review çalıştırır; eksik/yanlış işleri bulur, owner'a fix-task açar. Bu, CROSS-TEST'ten
> önceki son bütünsel kontroldür.

## 8. Transport gerçeği (ajanlar nasıl konuşur)

| Ajan | Nasıl erişilir | Çıktısını nereye yazar |
|---|---|---|
| @claude | Bu Claude Code oturumu | Doğrudan commit |
| @gemini | Operatör `PROMPT-gemini.md`'yi yeni Gemini oturumuna yapıştırır | Gemini metni üretir → operatör commit'ler |
| @hermes | İnsan operatör + VPS | format-patch → operatör `git am` + push |

Rol kartları (`PROMPT-*.md`) bu yüzden **arayüzün kendisidir** — güncel tutulmalı.

## 9. Lint

`python LLTODO/scripts/lltodo_lint.py` — durum kümesi, claim, isimlendirme, template uyumu,
SCOREBOARD tutarlılığı ve kırık referansları doğrular. Her commit öncesi yeşil olmalı.

## 10. Örnek akış (P-XXX placeholder)

```
@hermes:  plans/P-XXX yazar               → DRAFT
@claude:  reviews/R-XXX-claude (conf 8 ✓) → REVIEW_OPEN
@gemini:  reviews/R-XXX-gemini (conf 9 ✓) → CONSENSUS_REACHED  (2/3 APPROVE)
@hermes:  splits/S-XXX yazar (owner/tester/gerekçe)
@claude+@gemini: ACK                       → SPLIT_AGREED
owner'lar: kendi T-XXX'lerini claim+impl   → IN_PROGRESS
@claude:  UR-XXX adversarial review        → ULTRA_REVIEW
tester'lar: tests/X-XXX (PASS)             → CROSS_TEST → TEST_CONSENSUS
hepsi PASS                                 → DONE
```
