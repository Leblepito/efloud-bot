# LLTODO v2 — Task Tracking System

> Efloud-bot görev takip sistemi. Append-only, branch-aware, multi-agent.
> Son güncelleme: 2026-06-10

## Dizin Yapısı

```
LLTODO/
├── README.md              ← Bu dosya
├── STATE.md               ← Epic durumları (P-001, P-002, ...)
├── SCOREBOARD.md          ← Tamamlanma metrikleri, sprint görünümü
├── PROMPT-*.md            ← Agent-spesifik prompt şablonları
├── templates/             ← Dosya şablonları (epic-plan, review, task)
├── plans/                 ← Epic planları (P-001-*.md)
├── reviews/               ← Review dosyaları (R-001-*.md)
├── tasks/                 ← Görev dosyaları
│   ├── IN_PROGRESS/       ← Claim edilmiş, üstünde çalışılan
│   ├── DONE/              ← Tamamlanmış
│   └── BACKLOG/           ← Henüz başlanmamış
├── scripts/               ← Lint ve yardımcı araçlar
└── tests/                 ← Lint testleri
```

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
| `CONSENSUS_REACHED` | Tüm review'ler onayladı |
| `IN_PROGRESS` | Implementasyon başladı |
| `ULTRA_REVIEW` | UR-001 @claude incelemesinde |
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
