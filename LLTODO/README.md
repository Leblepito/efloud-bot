# LLTODO v2 — Task Tracking System

> Efloud-bot görev takip sistemi. Append-only, branch-aware, multi-agent.
> Son güncelleme: 2026-06-10

## Dizin Yapısı

```
LLTODO/
├── README.md              ← Bu dosya
├── STATE.md               ← Epic durumları (P-001, P-002, ...)
├── SCOREBOARD.md          ← Tamamlanma metrikleri, sprint görünümü
├── CONSENSUS.md           ← 3-ajan teyit protokolü (plan/split/test gate'leri) [v3]
├── PROMPT-*.md            ← Agent-spesifik prompt şablonları
├── templates/             ← Dosya şablonları (epic-plan, review, task, split, crosstest)
├── plans/                 ← Epic planları (P-001-*.md)
├── reviews/               ← Review dosyaları (R-001-*.md)
├── splits/                ← Görev dağıtımı dosyaları (S-001-*.md) [v3]
├── tasks/                 ← Görev dosyaları
│   ├── IN_PROGRESS/       ← Claim edilmiş, üstünde çalışılan
│   ├── DONE/              ← Tamamlanmış
│   └── BACKLOG/           ← Henüz başlanmamış
├── scripts/               ← Lint ve yardımcı araçlar
└── tests/                 ← Lint testleri + cross-test raporları (X-001-*.md) [v3]
```

> **Consensus v3 (2026-06-13):** Plan review'a ek olarak **görev dağıtımı (SPLIT)** ve **test
> (CROSS-TEST)** de 3-ajan teyidinden geçer. Tam protokol: [`CONSENSUS.md`](CONSENSUS.md).
> Hermes'in pre-LLTODO planlama artefaktları `.hermes/plans/2026-06-09_*` + `docs/ceo-product-portfolio-2026-06-09.md` (P-002/P-003 girdileri).

## Kurallar

### Append-Only Prensibi
- Dosyalar **sadece yeni içerik eklenerek** güncellenir.
- Mevcut satırlar **silinmez**, üstü çizilir (`~~silinen~~`).
- STATE.md'de durum geçişleri yeni satır olarak eklenir, eski durum korunur.
- Bu prensip sayesinde her değişikliğin tam geçmişi dosyanın kendisinde görünür.

### Atomic Commit Kuralı
- `git add -A` **KESİNLİKLE YASAK**.
- Her commit sadece ilgili LLTODO dosyalarını içerir.
- Commit mesajı `lltodo(<epic>): <açıklama>` formatında.

### Branch Modeli
- **Global `[M]` dosyalar** master'da yaşar: `README.md`, `STATE.md`, `SCOREBOARD.md`, `templates/`, `scripts/`, `tests/`, `PROMPT-*.md`
- **Epic-spesifik dosyalar** kendi branch'lerinde yaşar: `plans/P-001-*.md`, `reviews/R-00*-*.md`, `tasks/T-00*-*.md`
- PR açarken sadece ilgili dosyalar dahil edilir.

### Durum Geçişleri (STATE.md)

| Durum | Açıklama |
|---|---|
| `DRAFT` | Plan yazılıyor |
| `REVIEW_OPEN` | Review'a açık (R-001, R-002, ...) |
| `CHANGES_REQUESTED` | Reviewer değişiklik istedi |
| `CONSENSUS_REACHED` | Tüm review'ler onayladı (2/3 APPROVE) |
| `SPLIT_AGREED` | Görev dağıtımı (S-XXX) 3/3 ACK aldı [v3] |
| `IN_PROGRESS` | Implementasyon başladı |
| `ULTRA_REVIEW` | UR-001 @claude incelemesinde |
| `CROSS_TEST` | Çapraz test sürüyor (X-XXX, tester ≠ owner) [v3] |
| `TEST_CONSENSUS` | Tüm görevler bağımsız CROSS-TEST PASS aldı [v3] |
| `DONE` | Tamamlandı, master'a merge edildi |

### Claim Kuralı
- Görev claim ederken: `tasks/IN_PROGRESS/T-00X-<slug>.md` oluşturulur.
- Aynı anda sadece **tek bir T-XXX** IN_PROGRESS'te olabilir.
- Claim eden agent dosyanın başına `claimed_by: <agent> @ <timestamp>` yazar.

## Ajanlar

| ID | Rol | Sorumluluk |
|---|---|---|
| `@hermes` | Architect/Implementor | Kod, plan, terminal, deploy |
| `@claude` | Architect/Reviewer | Plan review, UR-001 ultra review |
| `@gemini` | Reviewer | Plan review, backtest analizi |

## Lint

```bash
python scripts/lltodo_lint.py
# 8 test: STATE tutarlılık, claim kuralları, isimlendirme, template uyumu, ...
```
