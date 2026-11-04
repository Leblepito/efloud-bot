---
id: T-20261104-06
title: Hermes — smc-concepts + smc-setup-rules v2 (rulebook + review bulgularıyla)
from: claude-code
to: hermes
status: blocked
claimed_by: null
reviewer: abacus
created: 2026-11-04
touches_live: false
---

## Amaç
Taslakların yazarı olarak Hermes, T-20261104-01 rulebook'u (repo'daki türetilmiş özet — ham
Telegram metni değil) ve `REVIEW.md` bulgularıyla v2 yazar.

## Girdi
- `collab/outputs/<model>/telegram-rulebook-2023-2025.md` (T-01 çıktısı)
- `collab/skills-incubator/efloud-smc-concepts/` ve `efloud-smc-setup-rules/` (SKILL.md + REVIEW.md)

## Beklenen çıktı
- [ ] İki SKILL.md'yi v2'ye güncelle (veya tek skill'de birleştir): gerçek motor referansları (dosya:satır), LuxAlgo modu, frekans ağırlıklı kurallar, hipotezler ayrı başlıkta.
- [ ] REVIEW.md'ye `## hermes — tarih — v2 değişiklikleri` bölümü; status `in-review`.
- [ ] Branch `collab/hermes/T-20261104-06-skill-v2` → PR; `collab/log/hermes.md` girişi (`- VPS: N/A`).

## Kısıtlar
- Sayı (risk %, limit) önermez; kaynak canlı config.
- `skills/`'e taşıma YOK (promote = T-20261104-03).

## Log
- 2026-11-04 claude-code: blocked — T-20261104-01 bekleniyor.

## Review
