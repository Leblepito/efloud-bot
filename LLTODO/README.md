# LLTODO — Multi-Agent Task Coordination System

> **Kural:** Bu projeye giren HER AI agent (Claude, Hermes, Gemini, Codex, Manus)
> önce bu dosyayı okur, sonra `LLTODO/tasks/PENDING/` klasörüne bakar.

## Nasıl Çalışır

```
LLTODO/
├── README.md              ← BU DOSYA (tüm agent'lar önce bunu okur)
├── tasks/
│   ├── PENDING/           ← Henüz başlanmamış görevler
│   ├── IN_PROGRESS/       ← Şu an çalışılan görevler
│   └── DONE/              ← Tamamlanmış görevler (+ rapor)
└── reports/
    ├── hermes/            ← Hermes'in oturum raporları
    ├── claude/            ← Claude'un oturum raporları
    └── gemini/            ← Gemini'nin oturum raporları
```

## Görev Formatı (Her agent bu formatta yazar)

```markdown
---
task_id: T-XXX
assigned_by: <hangi agent atadı>
assigned_to: <hangi agent yapacak>
priority: P1 | P2 | P3
status: PENDING | IN_PROGRESS | DONE
skill: <kullanılacak skill>
deadline: <ISO timestamp veya "after:T-YYY">
dependencies: [T-XXX, T-YYY]
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
3. Varsa yeni görevler oluştur (kendine veya başka agent'a)
```

## Altın Kurallar

1. **SADECE sana atanmış görevleri yap.** `assigned_to` alanında senin adın yoksa dokunma.
2. **Görev bittiğinde DONE'a taşı.** PENDING'de bırakma.
3. **Her görev sonunda rapor yaz.** `reports/<agent>/` altına.
4. **Yeni görev oluştururken dependency belirt.** Hangi görev bitmeden bu başlayamaz?
5. **Çakışma durumunda:** `LLTODO/tasks/PENDING/` içinde aynı dosyayı kimse `IN_PROGRESS` yapmaz. Önce taşı, sonra başla.
6. **Agent'lar birbirinin görevini override etmez.** Bir görev `assigned_to: hermes` ise Claude onu yapmaz.

## Agent Tanımları

| Agent | Güçlü Olduğu Alan | Zayıf Olduğu Alan |
|-------|------------------|-------------------|
| **hermes** | Kod yazma, plan, terminal, dosya, deployment | Browser interaction, Pine Script görsel test |
| **claude** | Plan/design review, kod analizi, PR review | Terminal/execution (Claude Code managed) |
| **gemini** | Görsel analiz (chart, screenshot), video, büyük context | Terminal, kod yazma |
| **manus** | Browser automation, web testing, QA | Terminal, lokal dosya sistemi |
| **codex** | Second opinion, code review challenge | Deployment, infra |

## Cron / Zamanlanmış Görevler

Bir agent kendine veya başka agent'a zamanlanmış görev oluşturabilir:

```yaml
deadline: "after:5min"       # 5 dakika sonra başla
deadline: "after:T-005"      # T-005 bitince başla
deadline: "cron:0 9 * * *"   # Her gün 09:00'da
```

Hermes cronjob tool'u ile schedule edilir.

## İlk Görevler (Bu Oturumda Oluşturuldu)

| ID | Görev | Agent | Öncelik | Durum |
|----|-------|-------|---------|-------|
| T-001 | TradingView spec yaz | hermes | P1 | PENDING |
| T-002 | Master planı oku + CEO review | claude | P1 | PENDING |
| T-003 | Pine Script görsel test | gemini | P2 | PENDING |
