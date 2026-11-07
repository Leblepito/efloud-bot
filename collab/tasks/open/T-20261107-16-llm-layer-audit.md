---
id: T-20261107-16
title: LLM ajan katmanı denetimi — veto yolu (backlog madde 6)
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
LLM çıktısının bir işlem kararına, operatör uyarısına veya dashboard'a ulaştığı her yeri bulmak
(skill: llm-trading-agent-security). Yalnız rapor.

## Beklenen çıktı (Definition of Done)
- [x] Rapor: `collab/outputs/claude-code/2026-11-07-llm-agent-layer-audit.md` (A1–A5 + geçen kontroller).
- [ ] A3/A4 düzeltmesi: T-20261107-17 (alerter; trading koduna dokunmaz).
- [ ] A1/A2: operatör kararı — (a) sentiment yalnız telemetri (önerilen) / (b) ±5 kalsın + NET-cost backtest + onay.
