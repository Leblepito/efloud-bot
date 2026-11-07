---
id: T-20261107-15
title: ADR backfill + CONTEXT.md alan dili (backlog madde 5)
from: operator
to: claude-code
status: in-review
claimed_by: claude-code
reviewer: abacus
parent: T-20261106-04
created: 2026-11-07
touches_live: false
---

## Amaç
Geri dönmesi zor kararların gerekçesini (neden VPS, neden LLM veto yok, neden indicator-only…)
ve sık karışan terimleri (V2 bot ↔ SMC v2, breaker OPEN, orphan ↔ bare) kalıcı tek yere yazmak
(skill: architecture-decision-records, context-and-decisions).

## Beklenen çıktı (Definition of Done)
- [x] `docs/adr/` — README index + template + 10 ADR (0001–0009 backfill, orijinal karar tarihleriyle; 0010 yeni).
- [x] `CONTEXT.md` — yalnız tanımlar; her terim kod/config kanıtına bağlı; çözülen 3 belirsizlik + 1 onay bekleyen.
- [x] `AGENTS.md`'den bağlantı.
- [ ] Operatör: "V2/V3 durdurulmuşken canlı sayılır mı" sorusu (CONTEXT.md → Needs confirmation).

## Kısıtlar
- Yalnız doküman. Kod/config değişmedi (stale compose yorumları CONTEXT.md'de not edildi, düzeltilmedi).
